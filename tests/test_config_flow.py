"""Tests for the config and reconfigure flows."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_s400_local.const import (
    DOMAIN,
    SETUP_KEYS,
    SETUP_LOCAL,
)

ADDRESS = "04:AE:47:5C:FC:29"


async def test_user_existing_keys_creates_entry(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"address": ADDRESS, "setup_method": SETUP_KEYS},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "keys"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"bindkey": "aa" * 16, "token": "bb" * 12},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["bindkey"] == "aa" * 16
        assert result["data"]["token"] == "bb" * 12


async def test_user_invalid_key_shows_error(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"address": ADDRESS, "setup_method": SETUP_KEYS},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"bindkey": "nothex", "token": ""},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_key"}


async def test_user_invalid_address_shows_error(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"address": "zz", "setup_method": SETUP_KEYS},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"address": "invalid_address"}


async def test_duplicate_entry_aborts(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"address": ADDRESS, "setup_method": SETUP_KEYS},
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


async def test_local_pairing_no_device(hass: HomeAssistant) -> None:
    with (
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
            return_value=[],
        ),
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_ble_device_from_address",
            return_value=None,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"address": ADDRESS, "setup_method": SETUP_LOCAL},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "pair"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["errors"] == {"base": "device_not_found"}


async def test_local_pairing_success(hass: HomeAssistant) -> None:
    from unittest.mock import AsyncMock

    from custom_components.xiaomi_s400_local import pairing

    result_pair = pairing.PairingResult(
        mac=ADDRESS,
        product_id="0x30D9",
        did="blt.3.1abc",
        did_hex="00" * 20,
        bindkey="aa" * 16,
        token="bb" * 12,
    )
    with (
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
            return_value=[],
        ),
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_ble_device_from_address",
            return_value=object(),
        ),
        patch(
            "custom_components.xiaomi_s400_local.config_flow.pair_device",
            new=AsyncMock(return_value=result_pair),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": ADDRESS, "setup_method": SETUP_LOCAL}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["bindkey"] == "aa" * 16


async def test_local_pairing_failure(hass: HomeAssistant) -> None:
    from unittest.mock import AsyncMock

    from custom_components.xiaomi_s400_local import pairing

    with (
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
            return_value=[],
        ),
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_ble_device_from_address",
            return_value=object(),
        ),
        patch(
            "custom_components.xiaomi_s400_local.config_flow.pair_device",
            new=AsyncMock(side_effect=pairing.PairingError("nope")),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": ADDRESS, "setup_method": SETUP_LOCAL}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["errors"] == {"base": "pairing_failed"}


async def test_discovery_confirm_step(hass: HomeAssistant) -> None:
    from types import SimpleNamespace

    from custom_components.xiaomi_s400_local.const import MIBEACON_UUID

    info = SimpleNamespace(
        address=ADDRESS,
        name="Xiaomi Scale S400",
        service_data={MIBEACON_UUID: bytes.fromhex("0000d930")},
    )
    with patch(
        "custom_components.xiaomi_s400_local.config_flow.product_id_from_service_data",
        return_value=0x30D9,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "bluetooth"}, data=info
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"


async def test_discovery_unsupported(hass: HomeAssistant) -> None:
    from types import SimpleNamespace

    from custom_components.xiaomi_s400_local.const import MIBEACON_UUID

    info = SimpleNamespace(
        address=ADDRESS,
        name="Something else",
        service_data={MIBEACON_UUID: bytes.fromhex("0000ffff")},
    )
    with patch(
        "custom_components.xiaomi_s400_local.config_flow.product_id_from_service_data",
        return_value=0xFFFF,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "bluetooth"}, data=info
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_reconfigure_updates_credentials(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Xiaomi S400 FC:29",
        unique_id=ADDRESS,
        data={"address": ADDRESS, "bindkey": "00" * 16, "token": ""},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"bindkey": "cc" * 16, "token": "dd" * 12},
    )
    assert result["type"] == FlowResultType.ABORT
    assert entry.data["bindkey"] == "cc" * 16
    assert entry.data["token"] == "dd" * 12


async def test_reconfigure_invalid_key(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Xiaomi S400 FC:29",
        unique_id=ADDRESS,
        data={"address": ADDRESS, "bindkey": "00" * 16, "token": ""},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bindkey": "nope", "token": ""}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_key"}


async def test_local_pairing_registration_unsupported(hass: HomeAssistant) -> None:
    from unittest.mock import AsyncMock

    from custom_components.xiaomi_s400_local import pairing

    with (
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_discovered_service_info",
            return_value=[],
        ),
        patch(
            "custom_components.xiaomi_s400_local.config_flow.bluetooth.async_ble_device_from_address",
            return_value=object(),
        ),
        patch(
            "custom_components.xiaomi_s400_local.config_flow.pair_device",
            new=AsyncMock(side_effect=pairing.RegistrationUnsupported("v2")),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"address": ADDRESS, "setup_method": SETUP_LOCAL}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["errors"] == {"base": "registration_unsupported"}
