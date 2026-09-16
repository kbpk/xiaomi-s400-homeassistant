"""Offline model of the public SDK's v2 registration credential.

This verifies the two signatures, not the complete firmware certificate parser
or S400 compatibility. It neither obtains nor issues Xiaomi credentials.
Evidence and field offsets: research/AUTH_V2.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

from .protocol import DID_ASSOCIATED_DATA, DID_NONCE

# Public trust anchor extracted from the cited SDK, NOT from S400 firmware.
SDK_ROOT_PUBLIC_XY = bytes.fromhex(
    "bef58b02dae3fff8541aa0448fbac44db7c69a2fa8f0b1b6ff7ad951db6628fa"
    "d7f020ea39a2ee867fdd783fdc2fb086095cc2850413a2802c627dbdc715f4f9"
)


@dataclass(frozen=True, slots=True, repr=False)
class RegistrationCredentialV2:
    """Decrypted type-0 contents and the separately transferred type-7 DER."""

    did: bytes
    signature: bytes  # P-256 r || s, each a 32-byte big-endian integer
    utc: bytes  # Preserve the exact four wire bytes covered by the signature.
    certificate_der: bytes

    def __post_init__(self) -> None:
        if len(self.did) != 20 or len(self.signature) != 64 or len(self.utc) != 4:
            raise ValueError("v2 credential requires DID[20], signature[64], UTC[4]")
        if not 0 < len(self.certificate_der) <= 512:
            raise ValueError("SDK certificate buffer accepts 1..512 bytes")

    def signed_message(self, bindkey: bytes) -> bytes:
        """Return the forty bytes whose SHA-256 digest the SDK verifies."""
        if len(bindkey) != 16:
            raise ValueError("bindkey must contain exactly 16 bytes")
        return self.did + bindkey + self.utc

    def verify_signatures(
        self, bindkey: bytes, *, root_public_xy: bytes = SDK_ROOT_PUBLIC_XY
    ) -> None:
        """Check root -> server and server -> registration signatures.

        A custom root is for isolated tests. It does not replace the root in
        device firmware. No claim is made about certificate validity policy.
        """
        if len(root_public_xy) != 64:
            raise ValueError("root public key must contain 64 bytes")
        root = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), b"\x04" + root_public_xy
        )
        certificate = x509.load_der_x509_certificate(self.certificate_der)
        root.verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            ec.ECDSA(hashes.SHA256()),
        )
        server = certificate.public_key()
        if not isinstance(server, ec.EllipticCurvePublicKey) or not isinstance(
            server.curve, ec.SECP256R1
        ):
            raise ValueError("server certificate must contain a P-256 key")
        signature_der = utils.encode_dss_signature(
            int.from_bytes(self.signature[:32], "big"),
            int.from_bytes(self.signature[32:], "big"),
        )
        server.verify(
            signature_der, self.signed_message(bindkey), ec.ECDSA(hashes.SHA256())
        )

    def encrypt(self, did_key: bytes) -> bytes:
        """Encode 88 plaintext bytes plus a four-byte CCM tag (92 total)."""
        if len(did_key) != 16:
            raise ValueError("DID key must contain exactly 16 bytes")
        return AESCCM(did_key, tag_length=4).encrypt(
            DID_NONCE, self.did + self.signature + self.utc, DID_ASSOCIATED_DATA
        )
