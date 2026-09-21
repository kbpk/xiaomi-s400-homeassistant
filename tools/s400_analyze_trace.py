#!/usr/bin/env python3
"""Summarize one pairing session per JSONL file, without Bluetooth or secrets."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class IncomingParcels:
    """Reassemble notifications in the legacy and negotiated inline formats."""

    def __init__(self) -> None:
        self.kind: int | None = None
        self.remaining = 0
        self.next_number = 1
        self.payload = bytearray()

    def feed(self, data: bytes) -> tuple[int, bytes] | None:
        if len(data) >= 4 and data[:3] == b"\0\0\2":
            self.remaining = 0
            return data[3], data[4:]
        if len(data) == 6 and data[:3] == b"\0\0\0":
            count = int.from_bytes(data[4:], "little")
            if not 1 <= count <= 16:
                raise ValueError("invalid incoming parcel count")
            self.kind = data[3]
            self.remaining = count
            self.next_number = 1
            self.payload.clear()
        elif self.remaining and len(data) >= 2:
            if int.from_bytes(data[:2], "little") != self.next_number:
                raise ValueError("missing or reordered incoming parcel fragment")
            self.payload.extend(data[2:])
            self.next_number += 1
            self.remaining -= 1
            if not self.remaining and self.kind is not None:
                return self.kind, bytes(self.payload)
        return None


def summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return metadata and ordering evidence; never include raw payloads."""
    result: dict[str, Any] = {
        "auth_version": None,
        "io_capability": None,
        "has_did": None,
        "device_public_key_bytes": None,
        "registration_payload_started": False,
        "auth_13_before_registration_payload": None,
        "registration_confirmed": False,
        "login_verified": False,
    }
    incoming = IncomingParcels()
    phase = "unknown"
    auth_seen = False
    sessions = 0
    for row in rows:
        event = row.get("event")
        if event == "connect_start":
            sessions += 1
            if sessions > 1:
                raise ValueError("expected one connection session per file")
        if event in ("registration_confirmed", "login_verified"):
            result[event] = True
        elif event == "registration_result":
            result["registration_confirmed"] = row.get("value") == "11000000"
        if event not in ("write", "notify"):
            continue
        uuid = str(row.get("uuid", "")).lower()
        data = bytes.fromhex(row.get("value", ""))
        if uuid == "00000010-0000-1000-8000-00805f9b34fb" and event == "write":
            if data == bytes.fromhex("a2000000"):
                phase = "info"
                incoming = IncomingParcels()
            elif data[:1] == b"\x15":
                phase = "keys"
                auth_seen = False
            elif data == bytes.fromhex("13000000"):
                auth_seen = True
        if uuid != "00000019-0000-1000-8000-00805f9b34fb":
            continue
        if event == "notify":
            parcel = incoming.feed(data)
            if parcel is None:
                continue
            kind, payload = parcel
            if phase == "info" and kind == 0:
                if len(payload) not in (4, 24):
                    raise ValueError("invalid GET_INFO length")
                result.update(
                    auth_version=int.from_bytes(payload[:2], "little"),
                    io_capability=int.from_bytes(payload[2:4], "little"),
                    has_did=len(payload) == 24,
                )
                phase = "info_received"
            elif phase == "keys" and kind == 3:
                result["device_public_key_bytes"] = len(payload)
                phase = "after_keys"
        elif phase == "after_keys" and data[:4] in (b"\0\0\0\0", b"\0\0\2\0"):
            result["registration_payload_started"] = True
            result["auth_13_before_registration_payload"] = auth_seen
            phase = "registration"

    result["incomplete_incoming_parcel"] = bool(incoming.remaining)
    if (
        result["auth_version"] == 2
        and result["device_public_key_bytes"] == 64
        and result["auth_13_before_registration_payload"] is False
    ):
        result["finding"] = "legacy_order_conflicts_with_public_auth_v2_sdk"
    else:
        result["finding"] = "no_v2_ordering_conflict_demonstrated"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.traces:
        try:
            with path.open(encoding="utf-8") as handle:
                report = summarize(json.loads(line) for line in handle if line.strip())
        except (OSError, ValueError, TypeError, AttributeError):
            # JSON errors can contain trace fragments; do not echo the exception.
            parser.exit(2, "Cannot analyze trace: invalid file or session structure.\n")
        print(json.dumps({"file": path.name, **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
