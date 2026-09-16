#!/usr/bin/env python3
"""Passively capture Xiaomi S400 advertisements without opening GATT."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from bleak import BleakScanner
except ImportError:
    print("Missing dependency: install bleak", file=sys.stderr)
    raise SystemExit(2) from None

MIBEACON_UUID = "0000fe95-0000-1000-8000-00805f9b34fb"
S400_PRODUCT_IDS = {0x30D9, 0x3BD5, 0x48CF}


def product_id(data: bytes | None) -> int | None:
    return int.from_bytes(data[2:4], "little") if data and len(data) >= 4 else None


async def run(args: argparse.Namespace) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    started = time.monotonic()
    count = 0

    with os.fdopen(fd, "w", encoding="utf-8") as handle:

        def callback(device: Any, advertisement: Any) -> None:
            nonlocal count
            data = advertisement.service_data.get(MIBEACON_UUID)
            pid = product_id(data)
            name = advertisement.local_name or device.name or ""
            if pid not in S400_PRODUCT_IDS and "s400" not in name.lower():
                return
            count += 1
            row = {
                "t": round(time.monotonic() - started, 6),
                "event": "advertisement",
                "address": device.address,
                "name": name or None,
                "rssi": advertisement.rssi,
                "service_data": {
                    key: value.hex()
                    for key, value in advertisement.service_data.items()
                },
                "manufacturer_data": {
                    str(key): value.hex()
                    for key, value in advertisement.manufacturer_data.items()
                },
            }
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            handle.flush()
            print(
                f"{row['t']:8.3f}s RSSI={advertisement.rssi:4d} "
                f"PID=0x{pid:04X} FE95={data.hex() if data else '-'}"
            )

        print(f"Scanning for S400 advertisements for {args.duration:g}s…")
        async with BleakScanner(detection_callback=callback):
            await asyncio.sleep(args.duration)

    print(f"Captured {count} advertisements: {args.output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument(
        "--output", type=Path, default=Path("captures/s400-advertisements.jsonl")
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        print(f"s400_scan: {error}", file=sys.stderr)
        raise SystemExit(1) from None
