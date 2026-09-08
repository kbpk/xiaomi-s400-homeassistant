"""Binary sensors exposed by Xiaomi S400 Local."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import S400Coordinator
from .entity import S400Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: S400Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([S400Stabilized(entry, coordinator)])


class S400Stabilized(S400Entity, BinarySensorEntity):
    """Whether the latest weighing cycle is complete."""

    _attr_translation_key = "stabilized"
    _attr_icon = "mdi:scale-bathroom"

    def __init__(self, entry: ConfigEntry, coordinator: S400Coordinator) -> None:
        super().__init__(entry, coordinator, "stabilized")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.values["stabilized"])
