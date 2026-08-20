"""End-to-end config-entry setup and unload tests."""

from unittest.mock import patch

import pytest
from custom_components.vaillant_modbus.const import (
    CONF_CONNECTION,
    CONF_UNIT_ID,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_coordinator import MockUnit, _active_responses


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Load all platforms and cleanly unregister them on unload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vaillant Modbus Gateway",
        unique_id="bus-entry:1",
        data={CONF_CONNECTION: "bus-entry", CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)
    unit = MockUnit(_active_responses())

    with patch(
        "custom_components.vaillant_modbus.async_get_unit_handle",
        return_value=unit,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.vaillant_system_outdoor_temperature") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
