#!/usr/bin/env python3
"""Export Bluetooth ATT packets from an Android HCI snoop log with tshark.

The tool has no Python dependencies. It deliberately keeps every ATT handle:
the missing S400 setup step may be sent outside the known FE95 auth channels.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FIELDS = (
    "frame.number",
    "frame.time_relative",
    "hci_h4.direction",
    "bthci_acl.connection_handle",
    "btatt.opcode",
    "btatt.handle",
    "btatt.value",
)


def find_tshark(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("tshark") or shutil.which("tshark.exe")
    if found:
        return found
    if os.name == "nt":
        candidate = (
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Wireshark"
            / "tshark.exe"
        )
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "Nie znaleziono tshark. Zainstaluj Wireshark z TShark albo podaj --tshark PATH."
    )


def export_rows(tshark: str, source: Path, display_filter: str) -> list[dict[str, str]]:
    command = [
        tshark,
        "-r",
        str(source),
        "-Y",
        display_filter,
        "-T",
        "fields",
        "-E",
        "header=y",
        "-E",
        "separator=\t",
        "-E",
        "quote=n",
        "-E",
        "occurrence=a",
    ]
    for field in FIELDS:
        command.extend(("-e", field))

    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        message = (
            result.stderr.strip() or f"tshark zakończył się kodem {result.returncode}"
        )
        raise RuntimeError(message)

    reader = csv.DictReader(result.stdout.splitlines(), delimiter="\t")
    return [{key: value or "" for key, value in row.items()} for row in reader]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Eksportuje wszystkie ramki ATT z Android Bluetooth HCI snoop do JSONL."
        )
    )
    parser.add_argument("capture", type=Path, help="btsnoop_hci.log lub plik .btsnoop")
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="docelowy plik JSONL"
    )
    parser.add_argument("--tshark", help="pełna ścieżka do tshark/tshark.exe")
    parser.add_argument(
        "--display-filter",
        default="btatt",
        help="filtr Wireshark; domyślnie zachowuje całe ATT",
    )
    args = parser.parse_args()

    if not args.capture.is_file():
        parser.error(f"capture nie istnieje: {args.capture}")

    try:
        rows = export_rows(find_tshark(args.tshark), args.capture, args.display_filter)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    print(f"Zapisano {len(rows)} ramek ATT do {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
