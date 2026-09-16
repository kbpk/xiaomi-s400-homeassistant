"""Mi Home BLE standard-auth protocol constants used by the S400."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistrationInfo:
    """GET_INFO payload, distinct from the MiBeacon version and auth mode."""

    version: int
    io_capability: int
    did: bytes | None


def parse_registration_info(payload: bytes) -> RegistrationInfo:
    """Decode the SDK's four-byte header and optional twenty-byte DID."""
    if len(payload) not in (4, 24):
        raise ValueError("GET_INFO must contain 4 or 24 bytes")
    return RegistrationInfo(
        version=int.from_bytes(payload[:2], "little"),
        io_capability=int.from_bytes(payload[2:4], "little"),
        did=payload[4:] if len(payload) == 24 else None,
    )


UPNP = "00000010-0000-1000-8000-00805f9b34fb"
AVCTP = "00000017-0000-1000-8000-00805f9b34fb"
AUTH_AUX = "00000018-0000-1000-8000-00805f9b34fb"
AVDTP = "00000019-0000-1000-8000-00805f9b34fb"
VEND1A = "0000001a-0000-1000-8000-00805f9b34fb"
CMTP = "0000001b-0000-1000-8000-00805f9b34fb"
VEND1C = "0000001c-0000-1000-8000-00805f9b34fb"
DEVICE_VERSION = "00000004-0000-1000-8000-00805f9b34fb"

CMD_GET_INFO = bytes.fromhex("a2000000")
CMD_TRANSPORT_INIT = bytes.fromhex("a4")
CMD_SET_KEY = bytes.fromhex("15000000")
CMD_LOGIN = bytes.fromhex("24000000")
CMD_AUTH = bytes.fromhex("13000000")

CMD_SEND_PUBLIC_KEY = bytes.fromhex("000000030400")
CMD_SEND_DID = bytes.fromhex("000000000200")
CMD_SEND_LOGIN_RANDOM = bytes.fromhex("0000000b0100")
CMD_SEND_LOGIN_INFO = bytes.fromhex("0000000a0200")

RCV_RDY = bytes.fromhex("00000101")
RCV_OK = bytes.fromhex("00000100")
RCV_ACK = bytes.fromhex("00000300")
RCV_LOST_PREFIX = bytes.fromhex("00000105")

TRANSPORT_OFFER = bytes.fromhex("00000400")
TRANSPORT_ACCEPT = bytes.fromhex("00000500")
TRANSPORT_PROBE = bytes.fromhex("00000401")
TRANSPORT_PROBE_REPLY = bytes.fromhex("00000501")
DEVICE_INFO_QUERIES = (
    bytes.fromhex("00"),
    bytes.fromhex("01"),
    bytes.fromhex("080100"),
    bytes.fromhex("03"),
)

REGISTER_OK = bytes.fromhex("11000000")
REGISTER_ERROR = bytes.fromhex("12000000")
LOGIN_OK = bytes.fromhex("21000000")
LOGIN_ERROR = bytes.fromhex("23000000")

SETUP_INFO = b"mible-setup-info"
LOGIN_INFO = b"mible-login-info"
DID_NONCE = bytes.fromhex("101112131415161718191a1b")
DID_ASSOCIATED_DATA = b"devID"
