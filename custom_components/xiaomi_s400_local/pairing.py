"""Local Mi Home BLE standard-auth registration for Xiaomi S400.

The routine only reports success after the scale confirms registration and a
fresh login using the derived token succeeds. Long-lived secrets are never
written to the trace recorder.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import string
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bleak import BleakClient, BleakScanner

from .const import MIBEACON_UUID, S400_PRODUCT_IDS
from .crypto import (
    SessionKeys,
    derive_login_keys,
    derive_setup_secrets,
    encrypt_did,
    generate_keypair,
    login_hmac,
)
from .protocol import (
    AUTH_AUX,
    AVCTP,
    AVDTP,
    CMD_AUTH,
    CMD_GET_INFO,
    CMD_LOGIN,
    CMD_SET_KEY,
    CMD_TRANSPORT_INIT,
    CMTP,
    DEVICE_INFO_QUERIES,
    DEVICE_VERSION,
    LOGIN_ERROR,
    LOGIN_OK,
    RCV_ACK,
    RCV_OK,
    RCV_RDY,
    REGISTER_ERROR,
    REGISTER_OK,
    TRANSPORT_ACCEPT,
    TRANSPORT_OFFER,
    TRANSPORT_PROBE,
    TRANSPORT_PROBE_REPLY,
    UPNP,
    VEND1A,
    VEND1C,
    parse_registration_info,
)


class PairingError(RuntimeError):
    """Pairing stopped because the device sent an unexpected response."""


class RegistrationUnsupported(PairingError):
    """The advertised registration variant has no implemented provisioner."""


def check_registration_support(version: int, io_capability: int) -> None:
    """Avoid applying the legacy registration exchange to a different protocol."""
    if version == 2:
        raise RegistrationUnsupported(
            "GET_INFO reports auth version 2. The matching public SDK expects "
            "0x13 BEFORE registration data, then a signed 92-byte payload and "
            "a server certificate (parcel type 0x07). Local v2 registration "
            "is not implemented; see research/AUTH_V2.md. "
            "No registration keys have been sent or saved."
        )
    if version != 1:
        raise RegistrationUnsupported(f"unsupported GET_INFO auth version: {version}")
    if io_capability:
        raise RegistrationUnsupported(
            "registration with OOB capabilities is not implemented"
        )


@dataclass(frozen=True, slots=True)
class PairingResult:
    """Credentials verified with a post-registration login."""

    mac: str
    product_id: str | None
    did: str
    did_hex: str
    bindkey: str
    token: str
    auth_protocol: str = "Mi Home BLE standard-auth (GET_INFO version 1)"


class TraceRecorder:
    """Append structured GATT events to JSONL without derived secrets."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._started = time.monotonic()
        self._handle = None

    def __enter__(self) -> TraceRecorder:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            self._handle = os.fdopen(fd, "w", encoding="utf-8")
        return self

    def __exit__(self, exc_type: object, exc: object, _: object) -> None:
        if exc is not None:
            self.record(
                "pairing_error",
                error_type=getattr(exc_type, "__name__", str(exc_type)),
                error=str(exc),
            )
        if self._handle:
            self._handle.close()
            self._handle = None

    def record(self, event: str, **values: Any) -> None:
        if not self._handle or self._handle.closed:
            return
        row = {
            "t": round(time.monotonic() - self._started, 6),
            "event": event,
            **values,
        }
        self._handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        self._handle.flush()


class _GattTransport:
    def __init__(
        self, client: BleakClient, trace: TraceRecorder, timeout: float
    ) -> None:
        self.client = client
        self.trace = trace
        self.timeout = timeout
        self.parcel_chunk_size = 18
        self.queues: dict[str, asyncio.Queue[bytes]] = {
            uuid: asyncio.Queue()
            for uuid in (UPNP, AVDTP, AVCTP, AUTH_AUX, VEND1A, CMTP, VEND1C)
        }

        self._subscribed: set[str] = set()

    async def subscribe(self, uuid: str) -> None:
        if uuid in self._subscribed:
            return

        def callback(_: Any, data: bytearray, notify_uuid: str = uuid) -> None:
            raw = bytes(data)
            self.trace.record("notify", uuid=notify_uuid, value=raw.hex())
            self.queues[notify_uuid].put_nowait(raw)

        await self.client.start_notify(uuid, callback)
        self._subscribed.add(uuid)
        self.trace.record("subscribe", uuid=uuid)

    async def start_official_order(self) -> None:
        """Subscribe channels in the order observed in newer Xiaomi scale captures."""
        for uuid in (CMTP, VEND1A, VEND1C, AVDTP):
            await self.subscribe(uuid)

    async def finish_subscriptions(self) -> None:
        for uuid in (UPNP, AVCTP, AUTH_AUX):
            await self.subscribe(uuid)

    async def write(self, uuid: str, value: bytes) -> None:
        self.trace.record("write", uuid=uuid, value=value.hex())
        try:
            await self.client.write_gatt_char(uuid, value, response=False)
        except Exception as err:
            self.trace.record(
                "write_failed",
                uuid=uuid,
                error_type=type(err).__name__,
                error=str(err),
            )
            raise
        self.trace.record("write_complete", uuid=uuid)

    async def receive(self, uuid: str, timeout: float | None = None) -> bytes:
        try:
            return await asyncio.wait_for(
                self.queues[uuid].get(), self.timeout if timeout is None else timeout
            )
        except TimeoutError as err:
            raise PairingError(f"timeout waiting for notification on {uuid}") from err

    async def expect(self, uuid: str, expected: bytes, context: str) -> None:
        actual = await self.receive(uuid)
        if actual != expected:
            raise PairingError(
                f"{context}: expected {expected.hex()}, received {actual.hex()}"
            )

    async def send_parcel(
        self,
        value: bytes,
        *,
        chunk_size: int | None = None,
        inter_frame_delay: float = 0.03,
    ) -> None:
        actual_chunk_size = chunk_size or self.parcel_chunk_size
        for frame_number, offset in enumerate(
            range(0, len(value), actual_chunk_size), start=1
        ):
            await self.write(
                AVDTP,
                frame_number.to_bytes(2, "little")
                + value[offset : offset + actual_chunk_size],
            )
            await asyncio.sleep(inter_frame_delay)

    def parcel_command(
        self,
        parcel_type: int,
        value: bytes,
        *,
        chunk_size: int | None = None,
    ) -> bytes:
        """Build a parcel header using the currently negotiated fragment size."""
        actual_chunk_size = chunk_size or self.parcel_chunk_size
        frame_count = (len(value) + actual_chunk_size - 1) // actual_chunk_size
        if not 0 <= parcel_type <= 0xFF or not 1 <= frame_count <= 0xFFFF:
            raise PairingError("invalid outgoing parcel parameters")
        return (
            b"\x00\x00\x00" + bytes((parcel_type,)) + frame_count.to_bytes(2, "little")
        )

    async def receive_parcel(self, expected_type: int | None = None) -> bytes:
        header = await self.receive(AVDTP)
        if (
            expected_type is not None
            and len(header) >= 4
            and header[3] != expected_type
        ):
            raise PairingError(
                f"expected parcel type {expected_type:#04x}, received {header[3]:#04x}"
            )
        # With the transport greeting and a large negotiated ATT payload,
        # Xiaomi scales can put the complete parcel in one notification:
        # 00 00 02 <type> <payload>. It uses a different acknowledgement.
        if len(header) >= 4 and header[:3] == b"\x00\x00\x02":
            await self.write(AVDTP, RCV_ACK)
            self.trace.record(
                "single_frame_parcel",
                parcel_type=header[3],
                payload_length=len(header) - 4,
            )
            return header[4:]
        if len(header) < 6 or header[:3] != b"\x00\x00\x00":
            raise PairingError(f"invalid parcel header: {header.hex()}")
        frame_count = int.from_bytes(header[4:6], "little")
        if not 1 <= frame_count <= 16:
            raise PairingError(f"unreasonable parcel frame count: {frame_count}")
        await self.write(AVDTP, RCV_RDY)
        result = bytearray()
        for expected_number in range(1, frame_count + 1):
            frame = await self.receive(AVDTP)
            if len(frame) < 2 or int.from_bytes(frame[:2], "little") != expected_number:
                raise PairingError(
                    f"expected parcel frame {expected_number}, received {frame.hex()}"
                )
            result.extend(frame[2:])
        await self.write(AVDTP, RCV_OK)
        return bytes(result)

    async def official_init(self) -> None:
        """Run the device-info and transport greeting observed in Mi Home traces."""
        for command in DEVICE_INFO_QUERIES:
            await self.write(VEND1C, command)
            try:
                response = await self.receive(VEND1C, timeout=2.0)
            except PairingError:
                self.trace.record("device_info_timeout", command=command.hex())
            else:
                self.trace.record(
                    "device_info_response",
                    command=command.hex(),
                    value=response.hex(),
                )

        await self.write(UPNP, CMD_TRANSPORT_INIT)
        offer = await self.receive(AVDTP, timeout=3.0)
        if not offer.startswith(TRANSPORT_OFFER) or len(offer) < 6:
            raise PairingError(f"invalid transport offer: {offer.hex()}")
        await self.write(AVDTP, TRANSPORT_ACCEPT + offer[4:])

        probe = await self.receive(AVDTP, timeout=3.0)
        if not probe.startswith(TRANSPORT_PROBE) or len(probe) < 4:
            raise PairingError(f"invalid transport probe: {probe.hex()}")
        await self.write(AVDTP, TRANSPORT_PROBE_REPLY + probe[4:])
        # Mi Home's channel layer derives the data MTU by adding the two-byte
        # sequence field to the probe payload.  For the S400 this is 240 + 2
        # = 242 data bytes, producing a full 244-byte GATT write.  Every
        # non-final frame must contain the complete negotiated data MTU.
        device_data_mtu = offer[5]
        negotiated_data_mtu = len(probe) - 2
        if negotiated_data_mtu != device_data_mtu or any(
            byte != device_data_mtu for byte in probe[4:]
        ):
            raise PairingError(
                "transport probe does not confirm the offered data MTU: "
                f"offered {device_data_mtu}, probed {negotiated_data_mtu}"
            )
        self.parcel_chunk_size = negotiated_data_mtu
        self.trace.record(
            "official_init_complete", parcel_chunk_size=self.parcel_chunk_size
        )


def _new_did() -> bytes:
    alphabet = string.ascii_letters + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(6)).encode("ascii")
    return b"\x00blt.3.129v" + suffix + b"ATC"


async def _login(transport: _GattTransport, token: bytes) -> SessionKeys:
    app_random = secrets.token_bytes(16)
    await transport.write(UPNP, CMD_LOGIN)
    await transport.write(AVDTP, transport.parcel_command(0x0B, app_random))
    await transport.expect(AVDTP, RCV_RDY, "login random readiness")
    await transport.send_parcel(app_random)
    await transport.expect(AVDTP, RCV_OK, "login random acknowledgement")

    device_random = await transport.receive_parcel(expected_type=0x0D)
    if len(device_random) != 16:
        raise PairingError(f"device login random has {len(device_random)} bytes")
    device_info = await transport.receive_parcel(expected_type=0x0C)
    keys = derive_login_keys(token, app_random, device_random)
    expected_device_info = login_hmac(keys.device_key, device_random + app_random)
    if not secrets.compare_digest(device_info, expected_device_info):
        raise PairingError("device HMAC does not match the locally derived token")

    app_info = login_hmac(keys.app_key, app_random + device_random)
    await transport.write(AVDTP, transport.parcel_command(0x0A, app_info))
    await transport.expect(AVDTP, RCV_RDY, "login HMAC readiness")
    await transport.send_parcel(app_info)
    await transport.expect(AVDTP, RCV_OK, "login HMAC acknowledgement")
    result = await transport.receive(UPNP)
    if result == LOGIN_ERROR:
        raise PairingError("scale rejected login")
    if result != LOGIN_OK:
        raise PairingError(f"unexpected login result: {result.hex()}")
    return keys


def product_id_from_service_data(service_data: bytes | None) -> int | None:
    """Read the little-endian product id from a MiBeacon frame."""
    if service_data is None or len(service_data) < 4:
        return None
    return int.from_bytes(service_data[2:4], "little")


async def find_s400(
    timeout: float = 20.0, address: str | None = None
) -> tuple[Any, int | None]:
    """Find an advertising S400 and return its BLEDevice and product id."""
    found_product_id: int | None = None

    def matcher(device: Any, advertisement: Any) -> bool:
        nonlocal found_product_id
        data = advertisement.service_data.get(MIBEACON_UUID)
        product_id = product_id_from_service_data(data)
        if address and device.address.upper() != address.upper():
            return False
        name = (advertisement.local_name or device.name or "").lower()
        if address or product_id in S400_PRODUCT_IDS or "s400" in name:
            found_product_id = product_id
            return True
        return False

    device = await BleakScanner.find_device_by_filter(matcher, timeout=timeout)
    if device is None:
        raise PairingError("S400 was not found; wake the scale and retry")
    return device, found_product_id


async def pair_device(
    address: str | None = None,
    *,
    ble_device: Any | None = None,
    product_id: int | None = None,
    did: bytes | None = None,
    timeout: float = 8.0,
    inter_stage_delay: float = 0.0,
    did_chunk_size: int | None = None,
    official_init: bool = True,
    trace_path: str | Path | None = None,
) -> PairingResult:
    """Register locally and verify the resulting token with a fresh login."""
    if ble_device is None:
        if address:
            ble_device, product_id = await find_s400(address=address)
        else:
            ble_device, product_id = await find_s400()
    address = ble_device.address

    with TraceRecorder(trace_path) as trace:
        trace.record(
            "connect_start",
            address=address,
            product_id=(f"0x{product_id:04X}" if product_id is not None else None),
            inter_stage_delay=inter_stage_delay,
            did_chunk_size=did_chunk_size,
            official_init=official_init,
        )

        def disconnected(_: BleakClient) -> None:
            trace.record("disconnected", address=address)

        async with BleakClient(
            ble_device,
            timeout=20.0,
            disconnected_callback=disconnected,
        ) as client:
            trace.record("connected", address=address)
            transport = _GattTransport(client, trace, timeout)
            await transport.start_official_order()
            if official_init:
                await transport.official_init()
            await transport.finish_subscriptions()
            try:
                version = bytes(await client.read_gatt_char(DEVICE_VERSION))
                trace.record("read", uuid=DEVICE_VERSION, value=version.hex())
            except Exception as err:
                trace.record(
                    "read_failed",
                    uuid=DEVICE_VERSION,
                    error_type=type(err).__name__,
                    error=str(err),
                )
            await asyncio.sleep(0.2)

            await transport.write(UPNP, CMD_GET_INFO)
            registration_info = parse_registration_info(
                await transport.receive_parcel(expected_type=0x00)
            )
            trace.record(
                "registration_info",
                auth_version=registration_info.version,
                io_capability=registration_info.io_capability,
                has_did=registration_info.did is not None,
            )
            check_registration_support(
                registration_info.version, registration_info.io_capability
            )
            selected_did = registration_info.did or did or _new_did()
            if len(selected_did) != 20:
                raise PairingError("selected DID is not 20 bytes")

            private_key, public_xy = generate_keypair()
            await transport.write(UPNP, CMD_SET_KEY)
            await transport.write(AVDTP, transport.parcel_command(0x03, public_xy))
            await transport.expect(AVDTP, RCV_RDY, "public key readiness")
            await transport.send_parcel(public_xy)
            await transport.expect(AVDTP, RCV_OK, "public key acknowledgement")

            device_public_xy = await transport.receive_parcel(expected_type=0x03)
            setup = derive_setup_secrets(private_key, device_public_xy)
            encrypted_did = encrypt_did(selected_did, setup.did_key)
            if inter_stage_delay > 0:
                trace.record(
                    "stage_pause", before="send_did", seconds=inter_stage_delay
                )
                await asyncio.sleep(inter_stage_delay)
            await transport.write(
                AVDTP,
                transport.parcel_command(
                    0x00,
                    encrypted_did,
                    chunk_size=did_chunk_size,
                ),
            )
            await transport.expect(AVDTP, RCV_RDY, "DID readiness")
            await transport.send_parcel(encrypted_did, chunk_size=did_chunk_size)
            await transport.expect(AVDTP, RCV_OK, "DID acknowledgement")
            await transport.write(UPNP, CMD_AUTH)

            register_result = await transport.receive(UPNP)
            if register_result == REGISTER_ERROR:
                raise PairingError("scale rejected standard-auth registration")
            if register_result != REGISTER_OK:
                raise PairingError(
                    f"unexpected registration result: {register_result.hex()}"
                )

            trace.record("registration_confirmed")
            await _login(transport, setup.token)
            trace.record("login_verified")

    try:
        did_text = selected_did.lstrip(b"\x00").decode("ascii")
    except UnicodeDecodeError:
        did_text = selected_did.hex()
    return PairingResult(
        mac=address.upper(),
        product_id=f"0x{product_id:04X}" if product_id is not None else None,
        did=did_text,
        did_hex=selected_did.hex(),
        bindkey=setup.bindkey.hex(),
        token=setup.token.hex(),
    )


def save_credentials(path: str | Path, result: PairingResult) -> None:
    """Save credentials as an owner-readable JSON file (mode 0600)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(asdict(result), handle, indent=2)
        handle.write("\n")
