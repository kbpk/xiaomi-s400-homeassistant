"""Exercise the Home Assistant state transitions without a running HA instance."""

from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType, SimpleNamespace

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from test_crypto_parser import PACKAGE


@pytest.fixture
def coordinator_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Provide the small HA Bluetooth API used by the coordinator."""
    ha = ModuleType("homeassistant")
    components = ModuleType("homeassistant.components")
    bluetooth = ModuleType("homeassistant.components.bluetooth")
    core = ModuleType("homeassistant.core")
    connector = ModuleType("bleak_retry_connector")
    bluetooth.BluetoothCallbackMatcher = lambda **kwargs: kwargs
    bluetooth.BluetoothChange = object
    bluetooth.BluetoothScanningMode = SimpleNamespace(PASSIVE="passive")
    bluetooth.BluetoothServiceInfoBleak = object
    core.CALLBACK_TYPE = object
    core.HomeAssistant = object
    core.callback = lambda function: function
    connector.establish_connection = None
    components.bluetooth = bluetooth
    ha.components = components
    for name, module in (
        ("homeassistant", ha),
        ("homeassistant.components", components),
        ("homeassistant.components.bluetooth", bluetooth),
        ("homeassistant.core", core),
        ("bleak_retry_connector", connector),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(sys.modules, PACKAGE.__name__, PACKAGE)
    sys.modules.pop("s400_test_core.coordinator", None)
    yield import_module("s400_test_core.coordinator")
    sys.modules.pop("s400_test_core.coordinator", None)


def _advertisement(weight: int | None, impedance: int | None) -> bytes:
    """Build one authenticated FE95 object with a predictable test bindkey."""
    address = bytes.fromhex("0a0720934684")
    mass = weight or 0
    z = impedance or 0
    packed = mass | (z << 18)
    payload = bytes.fromhex("166e09") + bytes([2]) + packed.to_bytes(4, "little")
    payload += (1_700_000_000).to_bytes(4, "little")
    prefix = (0x5858).to_bytes(2, "little") + bytes.fromhex("d9302a")
    counter = bytes.fromhex("010203")
    cipher = AESCCM(bytes.fromhex("00112233445566778899aabbccddeeff"), tag_length=4)
    encrypted = cipher.encrypt(address + prefix[2:5] + counter, payload, b"\x11")
    return prefix + address + encrypted[:-4] + counter + encrypted[-4:]


def test_new_weighing_discards_previous_persons_metrics(
    coordinator_module: ModuleType,
) -> None:
    coordinator = coordinator_module.S400Coordinator(
        object(),
        "84:46:93:20:07:0A",
        bytes.fromhex("00112233445566778899aabbccddeeff"),
    )

    def send(raw: bytes) -> None:
        info = SimpleNamespace(
            service_data={coordinator_module.MIBEACON_UUID: raw}, rssi=-55
        )
        coordinator._advertisement(info, None)

    send(_advertisement(736, None))
    coordinator.values["heart_rate"] = 90
    coordinator.values["impedance_high"] = 470.0
    assert coordinator.values["stabilized"] is True

    send((0x5100).to_bytes(2, "little") + bytes.fromhex("d9302a"))
    assert coordinator.values["stabilized"] is True

    send(_advertisement(742, 5106))
    assert coordinator.values["weight"] == 74.2
    assert coordinator.values["impedance_low"] == 510.6
    assert coordinator.values["heart_rate"] is None
    assert coordinator.values["impedance_high"] is None
    assert coordinator.values["stabilized"] is False


def test_active_final_records_timestamp_and_next_live_resets_metrics(
    coordinator_module: ModuleType,
) -> None:
    active = import_module("s400_test_core.active")
    coordinator = coordinator_module.S400Coordinator(
        object(), "84:46:93:20:07:0A", bytes(16)
    )
    coordinator._apply_active_measurement(
        active.ActiveMeasurement(
            weight=81.2,
            stabilized=True,
            profile_id=3,
            timestamp=1_700_000_000,
            impedance_low=511.2,
            impedance_high=489.1,
        )
    )
    assert coordinator.values["measurement_time"].timestamp() == 1_700_000_000
    assert coordinator.values["impedance_low"] == 511.2

    coordinator._apply_active_measurement(
        active.ActiveMeasurement(weight=73.6, stabilized=False)
    )
    assert coordinator.values["weight"] == 73.6
    assert coordinator.values["profile_id"] is None
    assert coordinator.values["impedance_low"] is None
    assert coordinator.values["measurement_time"] is None
