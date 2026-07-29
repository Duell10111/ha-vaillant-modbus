"""Vaillant Modbus Gateway integration."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import CONF_CONNECTION, CONF_UNIT_ID, MESSAGE_SPACING_SECONDS, PLATFORMS
from .coordinator import VaillantConfigEntry, VaillantCoordinator
from .modbus_api import async_get_unit_handle


async def async_setup_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    """Set up a Vaillant gateway using an existing shared Modbus connection."""
    unit_id = int(entry.data[CONF_UNIT_ID])
    unit = async_get_unit_handle(hass, str(entry.data[CONF_CONNECTION]), unit_id)
    unit.set_message_spacing(MESSAGE_SPACING_SECONDS)

    coordinator = VaillantCoordinator(hass, entry, unit, unit_id)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

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
