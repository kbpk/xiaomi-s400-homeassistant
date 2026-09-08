"""Bluetooth listener and state holder for Xiaomi S400 Local."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .const import MIBEACON_UUID
from .parser import AdvertisementError, parse_mibeacon

_LOGGER = logging.getLogger(__name__)


class S400Coordinator:
    """Convert advertisements into stable entity values."""

    def __init__(self, hass: HomeAssistant, address: str, bindkey: bytes) -> None:
        self.hass = hass
        self.address = address.upper()
        self.bindkey = bindkey
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

    def stop(self) -> None:
        """Remove the Bluetooth callback."""
        if self._cancel:
            self._cancel()
            self._cancel = None

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
