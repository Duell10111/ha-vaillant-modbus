"""End-to-end config-entry setup and unload tests."""

from unittest.mock import patch

import pytest
from custom_components import vaillant_modbus
from custom_components.vaillant_modbus.const import (
    ACCESS_MODE_READ_WRITE,
    CONF_ACCESS_MODE,
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


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_existing_entry_keeps_write_access(hass: HomeAssistant) -> None:
    """An entry without a stored access mode is migrated to read-write once."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vaillant Modbus Gateway",
        unique_id="bus-entry:1",
        data={CONF_CONNECTION: "bus-entry", CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)
    unit = MockUnit(_active_responses())
    setups = 0

    original_setup = vaillant_modbus.async_setup_entry

    async def counting_setup(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
        nonlocal setups
        setups += 1
        return await original_setup(hass, entry)

    with (
        patch(
            "custom_components.vaillant_modbus.async_get_unit_handle",
            return_value=unit,
        ),
        patch.object(vaillant_modbus, "async_setup_entry", counting_setup),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.options[CONF_ACCESS_MODE] == ACCESS_MODE_READ_WRITE
    assert entry.runtime_data.read_only is False
    # Writing the missing option must not trigger a reload loop.
    assert setups == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
