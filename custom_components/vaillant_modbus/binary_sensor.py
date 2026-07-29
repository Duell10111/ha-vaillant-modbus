"""Binary sensor entities for Vaillant Modbus Gateway."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VaillantConfigEntry, VaillantCoordinator
from .entity import VaillantEntity
from .register import (
    RegisterDefinition,
    RegisterPlatform,
    definitions_for_platform,
)


class VaillantBinarySensor(VaillantEntity, BinarySensorEntity):
    """A boolean status decoded from a shared register block."""

    def __init__(
        self, coordinator: VaillantCoordinator, definition: RegisterDefinition
    ) -> None:
        """Initialize a binary sensor."""
        super().__init__(coordinator, definition)
        if definition.device_class is not None:
            self._attr_device_class = BinarySensorDeviceClass(definition.device_class)

    @property
    def is_on(self) -> bool | None:
        """Return the current boolean status."""
        value = self._value
        return value if isinstance(value, bool) else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VaillantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up declarative binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        VaillantBinarySensor(coordinator, definition)
        for definition in definitions_for_platform(RegisterPlatform.BINARY_SENSOR)
        if coordinator.definition_is_supported(definition)
    )
