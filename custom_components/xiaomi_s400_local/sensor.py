"""Sensors exposed by Xiaomi S400 Local."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfMass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import S400Coordinator
from .entity import S400Entity


@dataclass(frozen=True, kw_only=True)
class S400SensorDescription(SensorEntityDescription):
    """S400 sensor metadata."""


SENSORS = (
    S400SensorDescription(
        key="weight",
        translation_key="weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    S400SensorDescription(
        key="heart_rate",
        translation_key="heart_rate",
        icon="mdi:heart-pulse",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    S400SensorDescription(
        key="impedance_low",
        translation_key="impedance_low",
        icon="mdi:omega",
        native_unit_of_measurement="Ω",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    S400SensorDescription(
        key="impedance_high",
        translation_key="impedance_high",
        icon="mdi:omega",
        native_unit_of_measurement="Ω",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    S400SensorDescription(
        key="profile_id",
        translation_key="profile_id",
        icon="mdi:account",
    ),
    S400SensorDescription(
        key="rssi",
        translation_key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator: S400Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        S400Sensor(entry, coordinator, description) for description in SENSORS
    )


class S400Sensor(S400Entity, SensorEntity):
    """One decoded measurement field."""

    entity_description: S400SensorDescription

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: S400Coordinator,
        description: S400SensorDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.coordinator.values[self._key]
