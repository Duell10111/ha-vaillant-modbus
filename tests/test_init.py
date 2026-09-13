"""End-to-end config-entry setup and unload tests."""

from unittest.mock import patch

import pytest
from custom_components import vaillant_modbus
from custom_components.vaillant_modbus.const import (
    ACCESS_MODE_READ_WRITE,
    CONF_ACCESS_MODE,
    CONF_CONNECTION,
    CONF_HEATING_CIRCUIT_2,
    CONF_HEATING_CIRCUIT_3,
    CONF_UNIT_ID,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_coordinator import MockUnit, _active_responses, _vr71_responses


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


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_disabling_a_circuit_cleans_up_its_registry_entries(
    hass: HomeAssistant,
) -> None:
    """Switching a circuit off removes its entities and device, not circuit 3's."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vaillant Modbus Gateway",
        unique_id="bus-entry:1",
        data={CONF_CONNECTION: "bus-entry", CONF_UNIT_ID: 1},
        options={CONF_HEATING_CIRCUIT_2: True, CONF_HEATING_CIRCUIT_3: True},
    )
    entry.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    with patch(
        "custom_components.vaillant_modbus.async_get_unit_handle",
        return_value=MockUnit(_vr71_responses()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get("select.vaillant_heating_circuit_2_mode") is not None
        device_identifiers = {
            (DOMAIN, f"{entry.entry_id}/1/heating_circuit_2"),
        }
        assert device_registry.async_get_device(device_identifiers) is not None

        hass.config_entries.async_update_entry(
            entry,
            options={CONF_HEATING_CIRCUIT_2: False, CONF_HEATING_CIRCUIT_3: True},
        )
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("select.vaillant_heating_circuit_2_mode") is None
    assert device_registry.async_get_device(device_identifiers) is None
    assert (
        entity_registry.async_get_entity_id(
            "select", DOMAIN, f"{entry.entry_id}/1/heating_circuit_2_mode"
        )
        is None
    )
    # The circuit that stays enabled keeps its entity and its history.
    assert hass.states.get("select.vaillant_heating_circuit_3_mode") is not None
    assert (
        entity_registry.async_get_entity_id(
            "select", DOMAIN, f"{entry.entry_id}/1/heating_circuit_3_mode"
        )
        is not None
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
