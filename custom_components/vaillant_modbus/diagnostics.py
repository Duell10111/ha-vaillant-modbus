"""Diagnostics for Vaillant Modbus Gateway."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_CONNECTION, CONF_UNIT_ID, VERSION
from .coordinator import VaillantConfigEntry
from .modbus_api import LEGACY_PREFIX


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VaillantConfigEntry
) -> dict[str, Any]:
    """Return safe diagnostics without transport addresses or credentials."""
    coordinator = entry.runtime_data
    values = coordinator.data.values
    connection = str(entry.data[CONF_CONNECTION])
    connection_kind = (
        "home_assistant_modbus_hub"
        if connection.startswith(LEGACY_PREFIX)
        else "modbus_connection"
    )
    return {
        "integration_version": VERSION,
        "connection": {
            "kind": connection_kind,
            "identifier": "**REDACTED**",
        },
        "unit_id": int(entry.data[CONF_UNIT_ID]),
        "gateway_version": values.get("gateway_version"),
        "controller_version": values.get("controller_version"),
        "ebus_active": values.get("ebus_active"),
        "controller_active": values.get("controller_active"),
        "vr71_available": values.get("vr71_available"),
        "capabilities": asdict(coordinator.data.capabilities),
        "last_successful_poll": coordinator.data.last_successful_poll,
        "failed_optional_blocks": coordinator.data.failed_optional_blocks,
    }
