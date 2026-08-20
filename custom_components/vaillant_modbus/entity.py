"""Shared entity base for Vaillant Modbus entities."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import VaillantCoordinator
from .register import RegisterDefinition

_COMPONENT_NAMES = {
    "system": "Vaillant System",
    "hot_water": "Vaillant Hot Water",
    "heating_circuit_1": "Vaillant Heating Circuit 1",
    "heating_circuit_2": "Vaillant Heating Circuit 2",
    "heating_circuit_3": "Vaillant Heating Circuit 3",
    "heat_pump": "Vaillant Heat Pump",
    "heater_1": "Vaillant Heater 1",
    "heater_2": "Vaillant Heater 2",
}


class VaillantEntity(CoordinatorEntity[VaillantCoordinator]):
    """Common coordinator, identity, translation, and device metadata."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: VaillantCoordinator, definition: RegisterDefinition
    ) -> None:
        """Initialize an entity from its declarative definition."""
        super().__init__(coordinator)
        self.definition = definition
        entry = coordinator.config_entry
        self._attr_unique_id = (
            f"{entry.entry_id}/{coordinator.unit_id}/{definition.key}"
        )
        self._attr_translation_key = definition.key
        self._attr_icon = definition.icon
        if definition.entity_category is not None:
            self._attr_entity_category = EntityCategory(definition.entity_category)

        gateway_identifier = (DOMAIN, f"{entry.entry_id}/{coordinator.unit_id}")
        gateway_version = coordinator.data.values.get("gateway_version")
        if definition.component == "gateway":
            self._attr_device_info = DeviceInfo(
                identifiers={gateway_identifier},
                manufacturer=MANUFACTURER,
                model=MODEL,
                name=entry.title,
                sw_version=(
                    str(gateway_version) if gateway_version is not None else None
                ),
            )
        else:
            component = definition.component
            self._attr_device_info = DeviceInfo(
                identifiers={
                    (
                        DOMAIN,
                        f"{entry.entry_id}/{coordinator.unit_id}/{component}",
                    )
                },
                manufacturer=MANUFACTURER,
                name=_COMPONENT_NAMES[component],
                translation_key=component,
                via_device=gateway_identifier,
            )

    @property
    def available(self) -> bool:
        """Return true only for fresh data from an actually available block."""
        return super().available and self.coordinator.definition_is_available(
            self.definition
        )

    @property
    def _value(self) -> Any:
        """Return the latest decoded value."""
        return self.coordinator.data.values.get(self.definition.key)
