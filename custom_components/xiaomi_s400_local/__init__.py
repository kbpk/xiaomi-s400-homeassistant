"""Xiaomi S400 Local integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_BINDKEY, DOMAIN
from .coordinator import S400Coordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start passive local reception for one S400."""
    coordinator = S400Coordinator(
        hass,
        entry.data["address"],
        bytes.fromhex(entry.data[CONF_BINDKEY]),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    coordinator.start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an S400 and its Bluetooth listener."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    coordinator: S400Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    coordinator.stop()
    return True
