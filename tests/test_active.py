from __future__ import annotations

import sys
from importlib import import_module

from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from test_crypto_parser import PACKAGE

sys.modules[PACKAGE.__name__] = PACKAGE
active = import_module("s400_test_core.active")
crypto = import_module("s400_test_core.crypto")


def test_reassembles_numbered_cmtp_frames() -> None:
    frames = active.CmtpFrames()
    frames.start(bytes.fromhex("000000000200"))
    assert frames.add(bytes.fromhex("0100616263")) is None
    assert frames.add(bytes.fromhex("0200646566")) == b"abcdef"


def test_decodes_authenticated_live_measurement() -> None:
    keys = crypto.SessionKeys(
        device_key=bytes.fromhex("00112233445566778899aabbccddeeff"),
        app_key=bytes(16),
        device_iv=bytes.fromhex("01020304"),
        app_iv=bytes(4),
    )
    plaintext = bytes.fromhex("0c20000007080000010000") + b"\xa0" + b"736,1"
    counter = bytes.fromhex("1700")
    nonce = keys.device_iv + bytes(4) + counter + bytes(2)
    encrypted = AESCCM(keys.device_key, tag_length=4).encrypt(nonce, plaintext, None)
    measurement = active.decode_cmtp(keys, counter + encrypted)
    assert measurement is not None
    assert measurement.weight == 73.6
    assert measurement.stabilized is True


def test_parses_final_measurement() -> None:
    plaintext = b"\x01\x02\xa00,0,3,812,1,2,1700000000,0,0,0,4891,5112"
    measurement = active.parse_cmtp_plaintext(plaintext)
    assert measurement is not None
    assert measurement.weight == 81.2
    assert measurement.profile_id == 3
    assert measurement.timestamp == 1700000000
    assert measurement.impedance_low == 489.1
    assert measurement.impedance_high == 511.2
