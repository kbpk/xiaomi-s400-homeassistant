"""Strict parser for encrypted S400 MiBeacon v4/v5 advertisements."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from .const import S400_PRODUCT_IDS


@dataclass(frozen=True, slots=True)
class S400Advertisement:
    product_id: int
    frame_version: int
    frame_counter: int
    registered: bool
    encrypted: bool
    timestamp: int | None = None
    profile_id: int | None = None
    weight: float | None = None
    heart_rate: int | None = None
    impedance_low: float | None = None
    impedance_high: float | None = None
    stabilized: bool | None = None


class AdvertisementError(ValueError):
    """MiBeacon payload is malformed or cannot be authenticated."""


def _mac_bytes(address: str) -> bytes:
    try:
        value = bytes.fromhex(address.replace(":", ""))
    except ValueError as err:
        raise AdvertisementError("invalid Bluetooth address") from err
    if len(value) != 6:
        raise AdvertisementError("Bluetooth address must contain six bytes")
    return value


def parse_mibeacon(address: str, data: bytes, bindkey: bytes) -> S400Advertisement:
    """Authenticate, decrypt and decode an S400 object 0x6E16."""
    if len(bindkey) != 16:
        raise AdvertisementError("MiBeacon v4/v5 bindkey must contain 16 bytes")
    if len(data) < 5:
        raise AdvertisementError("MiBeacon frame is too short")
    frame_control = int.from_bytes(data[:2], "little")
    version = frame_control >> 12
    product_id = int.from_bytes(data[2:4], "little")
    if product_id not in S400_PRODUCT_IDS:
        raise AdvertisementError(f"unsupported product id 0x{product_id:04x}")
    if version not in (4, 5):
        raise AdvertisementError(f"unsupported MiBeacon version {version}")

    has_object = bool(frame_control & (1 << 6))
    has_capability = bool(frame_control & (1 << 5))
    has_mac = bool(frame_control & (1 << 4))
    encrypted = bool(frame_control & (1 << 3))
    registered = bool(frame_control & (1 << 8))
    index = 5
    source_mac = _mac_bytes(address)
    packet_mac = source_mac
    if has_mac:
        if len(data) < index + 6:
            raise AdvertisementError("MiBeacon MAC field is truncated")
        packet_mac = data[index : index + 6][::-1]
        index += 6
        if packet_mac != source_mac:
            raise AdvertisementError("MiBeacon embedded MAC differs from source")
    if has_capability:
        if len(data) <= index:
            raise AdvertisementError("MiBeacon capability field is truncated")
        capability = data[index]
        index += 1
        if capability & 0x20:
            index += 1
    base = S400Advertisement(product_id, version, data[4], registered, encrypted)
    if not has_object:
        return base
    if not encrypted:
        payload = data[index:]
    else:
        if len(data) < index + 9:
            raise AdvertisementError("encrypted MiBeacon payload is too short")
        nonce = packet_mac[::-1] + data[2:5] + data[-7:-4]
        try:
            payload = AESCCM(bindkey, tag_length=4).decrypt(
                nonce, data[index:-7] + data[-4:], b"\x11"
            )
        except InvalidTag as err:
            raise AdvertisementError("MiBeacon authentication tag is invalid") from err

    offset = 0
    result = base
    while offset + 3 <= len(payload):
        object_id = int.from_bytes(payload[offset : offset + 2], "little")
        length = payload[offset + 2]
        value = payload[offset + 3 : offset + 3 + length]
        if len(value) != length:
            raise AdvertisementError("MiBeacon object is truncated")
        offset += 3 + length
        if object_id != 0x6E16:
            continue
        if length != 9:
            raise AdvertisementError("S400 object 0x6E16 must contain nine bytes")
        profile_id, packed, timestamp = struct.unpack("<BII", value)
        mass = packed & 0x7FF
        heart = (packed >> 11) & 0x7F
        impedance = packed >> 18
        low = impedance / 10 if impedance and mass else None
        high = impedance / 10 if impedance and not mass and not heart else None
        stabilized = bool(high is not None or (mass and not impedance))
        result = S400Advertisement(
            product_id=product_id,
            frame_version=version,
            frame_counter=data[4],
            registered=registered,
            encrypted=encrypted,
            timestamp=timestamp or None,
            profile_id=profile_id,
            weight=mass / 10 if mass else None,
            heart_rate=heart + 50 if 0 < heart < 127 else None,
            impedance_low=low,
            impedance_high=high,
            stabilized=stabilized,
        )
    return result
