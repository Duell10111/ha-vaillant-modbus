"""Select entities for writable Vaillant enum registers."""

from __future__ import annotations

from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VaillantConfigEntry, VaillantCoordinator
from .entity import VaillantEntity
from .register import (
    RegisterDefinition,
    RegisterPlatform,
    definitions_for_platform,
)


class VaillantSelect(VaillantEntity, SelectEntity):
    """A writable enum parameter."""

    def __init__(
        self, coordinator: VaillantCoordinator, definition: RegisterDefinition
    ) -> None:
        """Initialize a select entity."""
        super().__init__(coordinator, definition)
        self._attr_options = list((definition.enum or {}).values())

    @property
    def current_option(self) -> str | None:
        """Return the decoded enum option key."""
        value = self._value
        return value if isinstance(value, str) and value in self.options else None

    @override
    async def async_select_option(self, option: str) -> None:
        """Validate, encode, write, and refresh."""
        await self.coordinator.async_write_value(self.definition, option)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VaillantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up declarative select entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        VaillantSelect(coordinator, definition)
        for definition in definitions_for_platform(RegisterPlatform.SELECT)
        if coordinator.definition_is_supported(definition)
    )
