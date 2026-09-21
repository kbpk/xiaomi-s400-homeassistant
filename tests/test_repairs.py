"""Tests for the invalid bindkey repair flow."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.xiaomi_s400_local import repairs


async def test_invalid_bindkey_repair_flow(hass: HomeAssistant) -> None:
    flow = await repairs.async_create_fix_flow(
        hass, "invalid_bindkey_04ae475cfc29", {"entry_id": "abc"}
    )
    assert isinstance(flow, repairs.InvalidBindkeyRepairFlow)

    result = await flow.async_step_init()
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"

    result = await flow.async_step_confirm({"confirm": True})
    assert result["type"] == "create_entry"
