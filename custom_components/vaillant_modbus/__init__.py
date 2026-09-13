"""Vaillant Modbus Gateway integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ACCESS_MODE,
    CONF_CONNECTION,
    CONF_UNIT_ID,
    DOMAIN,
    HEATING_CIRCUIT_OPTIONS,
    LEGACY_ACCESS_MODE,
    MESSAGE_SPACING_SECONDS,
    PLATFORMS,
)
from .coordinator import VaillantConfigEntry, VaillantCoordinator
from .modbus_api import async_get_unit_handle
from .register import REGISTER_DEFINITIONS


@callback
def _async_remove_disabled_heating_circuits(
    hass: HomeAssistant, entry: VaillantConfigEntry, coordinator: VaillantCoordinator
) -> None:
    """Drop registry leftovers of heating circuits that are switched off.

    A disabled circuit follows from the configuration alone and never from a
    register read, so a temporary eBUS or controller outage can never remove
    entities here. Without this, entities of a circuit that is switched off
    would linger unavailable forever, because a reload simply stops recreating
    them.
    """
    enabled = coordinator.data.capabilities.heating_circuits
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    prefix = f"{entry.entry_id}/{coordinator.unit_id}/"

    for number, component in HEATING_CIRCUIT_OPTIONS.items():
        if number in enabled:
            continue
        keys = {
            definition.key
            for definition in REGISTER_DEFINITIONS
            if definition.component == component
        }
        for registry_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            unique_id = registry_entry.unique_id
            if unique_id.startswith(prefix) and unique_id[len(prefix) :] in keys:
                entity_registry.async_remove(registry_entry.entity_id)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"{prefix}{component}")}
        )
        if device is not None:
            device_registry.async_update_device(
                device.id, remove_config_entry_id=entry.entry_id
            )


async def async_setup_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    """Set up a Vaillant gateway using an existing shared Modbus connection."""
    # Entries created before the access mode existed keep writing as before.
    if CONF_ACCESS_MODE not in entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_ACCESS_MODE: LEGACY_ACCESS_MODE},
        )

    unit_id = int(entry.data[CONF_UNIT_ID])
    unit = async_get_unit_handle(hass, str(entry.data[CONF_CONNECTION]), unit_id)
    unit.set_message_spacing(MESSAGE_SPACING_SECONDS)

    coordinator = VaillantCoordinator(hass, entry, unit, unit_id)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _async_remove_disabled_heating_circuits(hass, entry, coordinator)

    entry.async_on_unload(
        unit.on_connection_lost(
            lambda: hass.config_entries.async_schedule_reload(entry.entry_id)
        )
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    """Unload a config entry without closing the shared connection."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
