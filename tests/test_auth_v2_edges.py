"""Validation tests for the auth v2 credential model."""

from __future__ import annotations

import pytest

from custom_components.xiaomi_s400_local import auth_v2


def _credential(**overrides):
    fields = {
        "did": bytes(20),
        "signature": bytes(64),
        "utc": bytes(4),
        "certificate_der": b"\x01",
    }
    fields.update(overrides)
    return auth_v2.RegistrationCredentialV2(**fields)


def test_credential_field_validation() -> None:
    with pytest.raises(ValueError):
        _credential(did=bytes(19))
    with pytest.raises(ValueError):
        _credential(signature=bytes(63))
    with pytest.raises(ValueError):
        _credential(utc=bytes(3))
    with pytest.raises(ValueError):
        _credential(certificate_der=b"")
    with pytest.raises(ValueError):
        _credential(certificate_der=bytes(513))


def test_credential_method_validation() -> None:
    credential = _credential()
    with pytest.raises(ValueError):
        credential.signed_message(bytes(8))
    with pytest.raises(ValueError):
        credential.verify_certificate_signature(root_public_xy=bytes(10))
    with pytest.raises(ValueError):
        credential.encrypt(bytes(8))
