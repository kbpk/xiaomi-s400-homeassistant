#!/usr/bin/env python3
"""Provision a factory-reset Xiaomi S400 entirely over local BLE."""

from __future__ import annotations

import argparse
import asyncio
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType


def load_core():
    """Load reusable modules without importing Home Assistant integration setup."""
    root = Path(__file__).resolve().parents[1]
    package_path = root / "custom_components" / "xiaomi_s400_local"
    package = ModuleType("s400_pair_core")
    package.__path__ = [str(package_path)]
    sys.modules[package.__name__] = package
    return import_module("s400_pair_core.pairing")


async def run(args: argparse.Namespace) -> None:
    try:
        core = load_core()
    except ImportError as error:
        print(
            f"Missing dependency ({error.name}). "
            "Install: python3 -m pip install bleak cryptography",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    did = args.did.encode("ascii") if args.did else None
    result = await core.pair_device(
        args.address,
        did=did,
        timeout=args.protocol_timeout,
        inter_stage_delay=args.stage_delay,
        did_chunk_size=args.did_chunk_size,
        official_init=not args.skip_official_init,
        trace_path=args.trace,
    )
    core.save_credentials(args.output, result)
    print(f"Pairing and post-pair login verified for {result.mac}.")
    print(f"Credentials saved with mode 0600: {args.output}")
    print(f"Protocol trace (contains no derived secrets): {args.trace}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--address", help="BLE MAC; omit to discover by S400 product id"
    )
    parser.add_argument("--output", type=Path, default=Path("s400-secrets.json"))
    parser.add_argument("--trace", type=Path, default=Path("s400-pair-trace.jsonl"))
    parser.add_argument("--protocol-timeout", type=float, default=8.0)
    parser.add_argument(
        "--stage-delay",
        type=float,
        default=0.0,
        help="seconds to wait after the device public key before SEND_DID",
    )
    parser.add_argument(
        "--did-chunk-size",
        type=int,
        help=(
            "experimental DID fragment size; use 18 to reproduce the legacy "
            "two-frame DID exchange"
        ),
    )
    parser.add_argument(
        "--skip-official-init",
        action="store_true",
        help="skip the Mi Home device-info and transport initialization sequence",
    )
    parser.add_argument(
        "--did",
        help="advanced: exactly 20 ASCII bytes; normally a local DID is generated",
    )
    args = parser.parse_args()
    if args.did and len(args.did.encode("ascii")) != 20:
        parser.error("--did must encode to exactly 20 ASCII bytes")
    if args.stage_delay < 0:
        parser.error("--stage-delay cannot be negative")
    if args.did_chunk_size is not None and args.did_chunk_size < 1:
        parser.error("--did-chunk-size must be positive")
    return args


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        print(f"s400_pair: {error}", file=sys.stderr)
        raise SystemExit(1) from None
