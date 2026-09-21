"""Binary sensors exposed by Xiaomi S400 Local."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import S400ConfigEntry
from .coordinator import S400Coordinator
from .entity import S400Entity

# One entity per decoded field; updates are pushed by the coordinator.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: S400ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: S400Coordinator = entry.runtime_data
    async_add_entities([S400Stabilized(entry, coordinator)])


class S400Stabilized(S400Entity, BinarySensorEntity):
    """Whether the latest weighing cycle is complete."""

    _attr_translation_key = "stabilized"

    def __init__(self, entry: S400ConfigEntry, coordinator: S400Coordinator) -> None:
        super().__init__(entry, coordinator, "stabilized")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.values["stabilized"])
