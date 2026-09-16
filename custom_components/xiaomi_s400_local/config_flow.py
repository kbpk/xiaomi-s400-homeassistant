"""UI configuration and optional local provisioning for Xiaomi S400."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BINDKEY,
    CONF_DID,
    CONF_PRODUCT_ID,
    CONF_SETUP_METHOD,
    CONF_TOKEN,
    DOMAIN,
    MIBEACON_UUID,
    S400_PRODUCT_IDS,
    SETUP_KEYS,
    SETUP_LOCAL,
)
from .pairing import (
    PairingError,
    RegistrationUnsupported,
    pair_device,
    product_id_from_service_data,
)


def _normalise_hex(value: str, byte_length: int) -> str:
    cleaned = value.strip().lower()
    raw = bytes.fromhex(cleaned)
    if len(raw) != byte_length:
        raise ValueError
    return raw.hex()


def _normalise_address(value: str) -> str:
    raw = bytes.fromhex(value.strip().replace(":", "").replace("-", ""))
    if len(raw) != 6:
        raise ValueError
    return ":".join(f"{part:02X}" for part in raw)


def _discovered(hass: HomeAssistant) -> dict[str, str]:
    choices: dict[str, str] = {}
    for info in bluetooth.async_discovered_service_info(hass, connectable=True):
        pid = product_id_from_service_data(info.service_data.get(MIBEACON_UUID))
        if pid in S400_PRODUCT_IDS or "s400" in (info.name or "").lower():
            choices[info.address] = f"{info.name or 'Xiaomi S400'} ({info.address})"
    return choices


def _product_id_for_address(hass: HomeAssistant, address: str) -> int | None:
    for info in bluetooth.async_discovered_service_info(hass, connectable=True):
        if info.address.upper() == address.upper():
            return product_id_from_service_data(info.service_data.get(MIBEACON_UUID))
    return None


class S400ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure an S400 without Xiaomi account credentials."""

    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        choices = _discovered(self.hass)
        if user_input is not None:
            try:
                address = _normalise_address(user_input[CONF_ADDRESS])
            except ValueError:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                self._address = address
                if user_input[CONF_SETUP_METHOD] == SETUP_LOCAL:
                    return await self.async_step_pair()
                return await self.async_step_keys()
        address_schema: Any = vol.In(choices) if choices else str
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): address_schema,
                    vol.Required(CONF_SETUP_METHOD, default=SETUP_LOCAL): vol.In(
                        {SETUP_LOCAL: "Local provisioning", SETUP_KEYS: "Existing keys"}
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._address is not None
            device = bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            if device is None:
                errors["base"] = "device_not_found"
            else:
                try:
                    result = await pair_device(
                        self._address,
                        ble_device=device,
                        product_id=_product_id_for_address(self.hass, self._address),
                    )
                except RegistrationUnsupported:
                    errors["base"] = "registration_unsupported"
                except (PairingError, BleakError, TimeoutError, OSError, ValueError):
                    errors["base"] = "pairing_failed"
                else:
                    return self.async_create_entry(
                        title=f"Xiaomi S400 {self._address[-5:]}",
                        data={
                            CONF_ADDRESS: result.mac,
                            CONF_BINDKEY: result.bindkey,
                            CONF_TOKEN: result.token,
                            CONF_PRODUCT_ID: result.product_id,
                            CONF_DID: result.did,
                        },
                    )
        return self.async_show_form(
            step_id="pair", data_schema=vol.Schema({}), errors=errors
        )

    async def async_step_keys(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                bindkey = _normalise_hex(user_input[CONF_BINDKEY], 16)
                token_input = user_input.get(CONF_TOKEN, "")
                token = _normalise_hex(token_input, 12) if token_input else ""
            except ValueError:
                errors["base"] = "invalid_key"
            else:
                assert self._address is not None
                return self.async_create_entry(
                    title=f"Xiaomi S400 {self._address[-5:]}",
                    data={
                        CONF_ADDRESS: self._address,
                        CONF_BINDKEY: bindkey,
                        CONF_TOKEN: token,
                    },
                )
        return self.async_show_form(
            step_id="keys",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BINDKEY): str,
                    vol.Optional(CONF_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_bluetooth(self, discovery_info) -> ConfigFlowResult:
        pid = product_id_from_service_data(
            discovery_info.service_data.get(MIBEACON_UUID)
        )
        if pid not in S400_PRODUCT_IDS:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address.upper()
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_pair()
        self._set_confirm_only()
        return self.async_show_form(step_id="discovery_confirm")
