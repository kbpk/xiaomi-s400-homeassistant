#!/usr/bin/env python3
"""Verify FE95 decoding and token-authenticated GATT without Xiaomi services.

Only decoded measurements and protocol stage names are printed. The secrets
file is read locally and neither credentials nor raw GATT packets are logged.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from importlib import import_module
from pathlib import Path
from types import ModuleType

from bleak import BleakClient, BleakScanner
from cryptography.exceptions import InvalidTag


def load_core() -> ModuleType:
    """Load reusable protocol code without importing Home Assistant."""
    package = ModuleType("s400_verify_core")
    package.__path__ = [
        str(Path(__file__).resolve().parents[1] / "custom_components/xiaomi_s400_local")
    ]
    sys.modules[package.__name__] = package
    return package


class _NoTrace:
    def record(self, event: str, **values: object) -> None:
        """Drop raw protocol data and long-lived credentials."""


async def run(args: argparse.Namespace) -> int:
    load_core()
    active = import_module("s400_verify_core.active")
    constants = import_module("s400_verify_core.const")
    pairing = import_module("s400_verify_core.pairing")
    parser = import_module("s400_verify_core.parser")
    protocol = import_module("s400_verify_core.protocol")

    config = json.loads(args.secrets.read_text(encoding="utf-8"))
    address = config["mac"].upper()
    bindkey = bytes.fromhex(config["bindkey"])
    token = bytes.fromhex(config["token"])
    if len(bindkey) != 16 or len(token) != 12:
        raise ValueError(
            "secrets file must contain a 16-byte bindkey and 12-byte token"
        )

    found = None
    advertisements = 0
    measurements = 0

    def on_advertisement(device, advertisement) -> None:
        nonlocal found, advertisements, measurements
        if device.address.upper() != address:
            return
        raw = advertisement.service_data.get(constants.MIBEACON_UUID)
        if raw is None:
            return
        found = device
        advertisements += 1
        try:
            decoded = parser.parse_mibeacon(address, raw, bindkey)
        except parser.AdvertisementError:
            return
        if any(
            value is not None
            for value in (
                decoded.weight,
                decoded.heart_rate,
                decoded.impedance_low,
                decoded.impedance_high,
            )
        ):
            measurements += 1
            print("FE95", json.dumps(asdict(decoded), sort_keys=True))

    print(f"Scanning for {address} for {args.scan_duration:g} seconds...", flush=True)
    async with BleakScanner(detection_callback=on_advertisement):
        await asyncio.sleep(args.scan_duration)
    print(f"FE95: {advertisements} advertisements, {measurements} measurements")
    if found is None:
        print("Scale not seen. Wake it and retry.")
        return 1

    async with BleakClient(found, timeout=20.0) as client:
        transport = pairing._GattTransport(client, _NoTrace(), timeout=12.0)
        await transport.start_official_order()
        await transport.official_init()
        await transport.finish_subscriptions()
        keys = await pairing._login(transport, token)
        print("Local token login: OK", flush=True)
        frames = active.CmtpFrames()
        decoded_count = 0
        deadline = asyncio.get_running_loop().time() + args.duration
        queue = transport.queues[protocol.CMTP]
        while client.is_connected and asyncio.get_running_loop().time() < deadline:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=2.0)
            except TimeoutError:
                continue
            if len(data) >= 6 and data[:3] == b"\x00\x00\x00":
                try:
                    frames.start(data)
                except ValueError:
                    frames = active.CmtpFrames()
                    continue
                await transport.write(protocol.CMTP, protocol.RCV_RDY)
                continue
            if not frames.expected:
                continue
            try:
                complete = frames.add(data)
            except ValueError:
                frames = active.CmtpFrames()
                continue
            if complete is None:
                continue
            await transport.write(protocol.CMTP, protocol.RCV_OK)
            try:
                measurement = active.decode_cmtp(keys, complete)
            except (InvalidTag, ValueError):
                continue
            if measurement is not None:
                decoded_count += 1
                print("GATT", json.dumps(asdict(measurement), sort_keys=True))
        print(f"GATT: {decoded_count} decoded measurements")
    return 0


def parse_args() -> argparse.Namespace:
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument(
        "--secrets",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "private/s400-secrets.json",
    )
    arguments.add_argument("--scan-duration", type=float, default=8.0)
    arguments.add_argument("--duration", type=float, default=60.0)
    args = arguments.parse_args()
    if args.scan_duration <= 0 or args.duration <= 0:
        arguments.error("durations must be positive")
    return args


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        print(f"s400_verify_local: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
