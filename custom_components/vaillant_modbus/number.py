"""Number entities for safe writable Vaillant parameters."""

from __future__ import annotations

from typing import override

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VaillantConfigEntry, VaillantCoordinator
from .entity import VaillantEntity
from .register import (
    RegisterDefinition,
    RegisterPlatform,
    definitions_for_platform,
)


class VaillantNumber(VaillantEntity, NumberEntity):
    """A validated writable scalar parameter."""

    def __init__(
        self, coordinator: VaillantCoordinator, definition: RegisterDefinition
    ) -> None:
        """Initialize a number entity."""
        super().__init__(coordinator, definition)
        self._attr_native_min_value = definition.minimum
        self._attr_native_max_value = definition.maximum
        self._attr_native_step = definition.step
        self._attr_native_unit_of_measurement = definition.unit
        if definition.device_class is not None:
            self._attr_device_class = NumberDeviceClass(definition.device_class)

    @property
    def native_value(self) -> float | None:
        """Return the decoded number."""
        value = self._value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Validate, encode, write, and refresh."""
        await self.coordinator.async_write_value(self.definition, value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VaillantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up declarative number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        VaillantNumber(coordinator, definition)
        for definition in definitions_for_platform(RegisterPlatform.NUMBER)
        if coordinator.definition_is_supported(definition)
    )
