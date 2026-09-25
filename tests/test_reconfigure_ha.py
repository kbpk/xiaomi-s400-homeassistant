"""Exercise credential reconfiguration through Home Assistant's flow manager."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_s400_local.const import DOMAIN


async def test_reconfigure_prefills_and_updates_credentials(
    hass: HomeAssistant,
) -> None:
    address = "04:AE:47:5C:FC:29"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Xiaomi S400 FC:29",
        unique_id=address,
        data={"address": address, "bindkey": "aa" * 16, "token": "bb" * 12},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    defaults = {
        marker.schema: marker.default() for marker in result["data_schema"].schema
    }
    assert defaults == {"bindkey": "aa" * 16, "token": "bb" * 12}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bindkey": "cc" * 16, "token": "dd" * 12}
    )
    assert result["type"] == FlowResultType.ABORT
    assert entry.data["bindkey"] == "cc" * 16
    assert entry.data["token"] == "dd" * 12
