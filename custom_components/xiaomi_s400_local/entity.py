"""Base entity for Xiaomi S400 Local."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import S400Coordinator


class S400Entity(Entity):
    """Entity updated by the S400 Bluetooth coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self, entry: ConfigEntry, coordinator: S400Coordinator, key: str
    ) -> None:
        self.coordinator = coordinator
        self._key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Xiaomi",
            model="Body Composition Scale S400 (MJTZC01YM)",
            name=entry.title,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_error is None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.add_listener(self.async_write_ha_state))
