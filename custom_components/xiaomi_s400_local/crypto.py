"""Cryptographic operations for Mi Home BLE standard-auth."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from hashlib import sha256

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .protocol import DID_ASSOCIATED_DATA, DID_NONCE, LOGIN_INFO, SETUP_INFO


@dataclass(frozen=True, slots=True)
class SetupSecrets:
    """Long-lived secrets produced by standard-auth registration."""

    token: bytes
    bindkey: bytes
    did_key: bytes


@dataclass(frozen=True, slots=True)
class SessionKeys:
    """Keys valid for one authenticated GATT connection."""

    device_key: bytes
    app_key: bytes
    device_iv: bytes
    app_iv: bytes


def generate_keypair() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    """Generate a P-256 key and return its 64-byte X || Y public value."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    encoded = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return private_key, encoded[1:]


def derive_setup_secrets(
    private_key: ec.EllipticCurvePrivateKey, device_public_xy: bytes
) -> SetupSecrets:
    """Derive token, beacon bindkey and DID encryption key from ECDH."""
    if len(device_public_xy) != 64:
        raise ValueError("device public key must contain 64 bytes (X || Y)")
    device_public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b"\x04" + device_public_xy
    )
    shared_secret = private_key.exchange(ec.ECDH(), device_public)
    derived = HKDF(
        algorithm=hashes.SHA256(), length=64, salt=None, info=SETUP_INFO
    ).derive(shared_secret)
    return SetupSecrets(derived[:12], derived[12:28], derived[28:44])


def encrypt_did(did: bytes, did_key: bytes) -> bytes:
    """Encrypt the 20-byte device identifier sent during registration."""
    if len(did) != 20:
        raise ValueError("DID must contain exactly 20 bytes")
    if len(did_key) != 16:
        raise ValueError("DID key must contain exactly 16 bytes")
    return AESCCM(did_key, tag_length=4).encrypt(DID_NONCE, did, DID_ASSOCIATED_DATA)


def derive_login_keys(
    token: bytes, app_random: bytes, device_random: bytes
) -> SessionKeys:
    """Derive connection keys from the 12-byte token and two nonces."""
    if len(token) != 12:
        raise ValueError("token must contain exactly 12 bytes")
    if len(app_random) != 16 or len(device_random) != 16:
        raise ValueError("login random values must contain exactly 16 bytes")
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=app_random + device_random,
        info=LOGIN_INFO,
    ).derive(token)
    return SessionKeys(
        device_key=derived[:16],
        app_key=derived[16:32],
        device_iv=derived[32:36],
        app_iv=derived[36:40],
    )


def login_hmac(key: bytes, data: bytes) -> bytes:
    """Return the SHA-256 HMAC used by the login challenge."""
    return hmac.new(key, data, sha256).digest()
