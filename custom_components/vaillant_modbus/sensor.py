"""Sensor entities for Vaillant Modbus Gateway."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VaillantConfigEntry, VaillantCoordinator
from .entity import VaillantEntity
from .register import (
    RegisterDataType,
    RegisterDefinition,
    RegisterPlatform,
    definitions_for_platform,
)


class VaillantSensor(VaillantEntity, SensorEntity):
    """A read-only value decoded from the coordinator snapshot."""

    def __init__(
        self, coordinator: VaillantCoordinator, definition: RegisterDefinition
    ) -> None:
        """Initialize a sensor."""
        super().__init__(coordinator, definition)
        self._attr_native_unit_of_measurement = definition.unit
        if definition.device_class is not None:
            self._attr_device_class = SensorDeviceClass(definition.device_class)
        if definition.state_class is not None:
            self._attr_state_class = SensorStateClass(definition.state_class)
        if definition.data_type is RegisterDataType.ENUM:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list((definition.enum or {}).values())

    @property
    def native_value(self) -> int | float | str | None:
        """Return the decoded value."""
        value = self._value
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float, str)):
            if isinstance(value, str) and value.startswith("unknown_"):
                return None
            return value
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VaillantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up declarative sensor entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        VaillantSensor(coordinator, definition)
        for definition in definitions_for_platform(RegisterPlatform.SENSOR)
        if coordinator.definition_is_supported(definition)
    )
