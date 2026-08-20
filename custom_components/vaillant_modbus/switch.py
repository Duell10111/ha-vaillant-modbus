"""Switch entities for safe writable Vaillant boolean registers."""

from __future__ import annotations

from typing import override

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import VaillantConfigEntry
from .entity import VaillantEntity
from .register import (
    RegisterPlatform,
    definitions_for_platform,
)


class VaillantSwitch(VaillantEntity, SwitchEntity):
    """A writable binary parameter."""

    @property
    def is_on(self) -> bool | None:
        """Return the decoded state."""
        value = self._value
        return value if isinstance(value, bool) else None

    @override
    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the parameter on."""
        await self.coordinator.async_write_value(self.definition, True)

    @override
    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the parameter off."""
        await self.coordinator.async_write_value(self.definition, False)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VaillantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up declarative switch entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        VaillantSwitch(coordinator, definition)
        for definition in definitions_for_platform(RegisterPlatform.SWITCH)
        if coordinator.definition_is_supported(definition)
    )
