"""Bluetooth listener and state holder for Xiaomi S400 Local."""

from __future__ import annotations

import logging
import time
from asyncio import CancelledError, Task, wait_for
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .active import CmtpFrames, decode_cmtp
from .const import MIBEACON_UUID
from .pairing import _GattTransport, _login
from .parser import AdvertisementError, parse_mibeacon
from .protocol import CMTP, RCV_OK, RCV_RDY

_LOGGER = logging.getLogger(__name__)


class S400Coordinator:
    """Convert advertisements into stable entity values."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        bindkey: bytes,
        token: bytes | None = None,
    ) -> None:
        self.hass = hass
        self.address = address.upper()
        self.bindkey = bindkey
        self.token = token
        self.values: dict[str, Any] = {
            "weight": None,
            "heart_rate": None,
            "impedance_low": None,
            "impedance_high": None,
            "profile_id": None,
            "stabilized": False,
            "rssi": None,
            "last_seen": None,
            "product_id": None,
            "mibeacon_version": None,
        }
        self._listeners: set[Callable[[], None]] = set()
        self._cancel: CALLBACK_TYPE | None = None
        self._active_task: Task[None] | None = None
        self._last_active_attempt = 0.0
        self.last_error: str | None = None

    def start(self) -> None:
        """Register a passive Bluetooth callback."""
        self._cancel = bluetooth.async_register_callback(
            self.hass,
            self._advertisement,
            BluetoothCallbackMatcher(
                address=self.address, service_data_uuid=MIBEACON_UUID
            ),
            BluetoothScanningMode.PASSIVE,
        )

    async def stop(self) -> None:
        """Remove the Bluetooth callback."""
        if self._cancel:
            self._cancel()
            self._cancel = None
        if self._active_task:
            self._active_task.cancel()
            with suppress(CancelledError):
                await self._active_task
            self._active_task = None

    @callback
    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.add(listener)

        @callback
        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    @callback
    def _advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        self._start_active_session()
        raw = service_info.service_data.get(MIBEACON_UUID)
        if raw is None:
            return
        try:
            update = parse_mibeacon(self.address, raw, self.bindkey)
        except AdvertisementError as err:
            self.last_error = str(err)
            _LOGGER.debug("Discarding S400 advertisement: %s", err)
            return
        self.last_error = None
        parsed = asdict(update)
        for key in (
            "weight",
            "heart_rate",
            "impedance_low",
            "impedance_high",
            "profile_id",
            "stabilized",
        ):
            if parsed[key] is not None:
                self.values[key] = parsed[key]
        self.values.update(
            rssi=service_info.rssi,
            last_seen=datetime.now(UTC),
            product_id=f"0x{update.product_id:04X}",
            mibeacon_version=update.frame_version,
        )
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _start_active_session(self) -> None:
        """Connect after an advertisement shows that the scale is awake."""
        if not self.token or (self._active_task and not self._active_task.done()):
            return
        now = time.monotonic()
        if now - self._last_active_attempt < 15:
            return
        self._last_active_attempt = now
        self._active_task = self.hass.async_create_task(
            self._active_session(), f"S400 active measurement {self.address}"
        )

    async def _active_session(self) -> None:
        """Log in and consume automatic measurements until disconnection."""
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None or self.token is None:
            return
        client: BleakClient | None = None
        try:
            client = await establish_connection(
                BleakClient,
                device,
                f"Xiaomi S400 {self.address}",
            )
            transport = _GattTransport(client, _NoTrace(), timeout=8.0)
            await transport.start_official_order()
            await transport.official_init()
            await transport.finish_subscriptions()
            keys = await _login(transport, self.token)
            self.last_error = None
            frames = CmtpFrames()
            queue = transport.queues[CMTP]
            while client.is_connected:
                try:
                    data = await wait_for(queue.get(), timeout=5.0)
                except TimeoutError:
                    continue
                if len(data) >= 6 and data[:3] == b"\x00\x00\x00":
                    frames.start(data)
                    await transport.write(CMTP, RCV_RDY)
                    continue
                if not frames.expected:
                    continue
                complete = frames.add(data)
                if complete is None:
                    continue
                await transport.write(CMTP, RCV_OK)
                measurement = decode_cmtp(keys, complete)
                if measurement is not None:
                    self._apply_active_measurement(measurement)
        except CancelledError:
            raise
        except Exception as err:
            self.last_error = f"active GATT: {type(err).__name__}: {err}"
            _LOGGER.debug("S400 active session ended: %s", err)
            self._notify_listeners()
        finally:
            if client and client.is_connected:
                with suppress(Exception):
                    await client.disconnect()

    @callback
    def _apply_active_measurement(self, measurement: Any) -> None:
        for key in (
            "weight",
            "impedance_low",
            "impedance_high",
            "profile_id",
        ):
            value = getattr(measurement, key)
            if value is not None:
                self.values[key] = value
        self.values["stabilized"] = measurement.stabilized
        self.values["last_seen"] = datetime.now(UTC)
        self.last_error = None
        self._notify_listeners()

    @callback
    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()


class _NoTrace:
    """Drop protocol trace events during normal Home Assistant operation."""

    def record(self, event: str, **values: Any) -> None:
        """Intentionally avoid logging protocol payloads or secrets."""
