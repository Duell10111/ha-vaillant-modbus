"""Representative entity tests for every platform."""

from unittest.mock import AsyncMock, patch

import pytest
from custom_components.vaillant_modbus.binary_sensor import VaillantBinarySensor
from custom_components.vaillant_modbus.const import (
    ACCESS_MODE_READ_ONLY,
    ACCESS_MODE_READ_WRITE,
    CONF_ACCESS_MODE,
    CONF_CONNECTION,
    CONF_UNIT_ID,
    DOMAIN,
)
from custom_components.vaillant_modbus.coordinator import (
    VaillantCapabilities,
    VaillantCoordinator,
    VaillantData,
)
from custom_components.vaillant_modbus.number import VaillantNumber
from custom_components.vaillant_modbus.register import REGISTER_BY_KEY
from custom_components.vaillant_modbus.select import VaillantSelect
from custom_components.vaillant_modbus.sensor import VaillantSensor
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_coordinator import MockUnit, _active_responses


def _coordinator(hass: HomeAssistant) -> VaillantCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vaillant Modbus Gateway",
        data={CONF_CONNECTION: "bus", CONF_UNIT_ID: 1},
    )
    entry.add_to_hass(hass)
    coordinator = VaillantCoordinator(hass, entry, MockUnit(), 1)
    coordinator.async_set_updated_data(
        VaillantData(
            values={
                "gateway_version": "1.20.0",
                "ebus_active": True,
                "controller_active": True,
                "outdoor_temperature": -5.0,
                "system_gas_energy_heating": 1234,
                "hot_water_circulation_pump": True,
                "hot_water_target_temperature": 50.0,
                "heating_circuit_1_mode": "auto",
            },
            available_blocks=frozenset(
                {"gateway", "system_status", "system_energy", "hot_water", "hc1"}
            ),
            capabilities=VaillantCapabilities(),
        )
    )
    return coordinator


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_temperature_sensor(hass: HomeAssistant) -> None:
    """Expose native temperature and metadata."""
    entity = VaillantSensor(_coordinator(hass), REGISTER_BY_KEY["outdoor_temperature"])
    assert entity.native_value == -5.0
    assert entity.native_unit_of_measurement == "°C"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_energy_sensor(hass: HomeAssistant) -> None:
    """Expose total-increasing energy."""
    entity = VaillantSensor(
        _coordinator(hass), REGISTER_BY_KEY["system_gas_energy_heating"]
    )
    assert entity.native_value == 1234
    assert entity.state_class == "total_increasing"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_binary_sensor(hass: HomeAssistant) -> None:
    """Expose boolean status."""
    entity = VaillantBinarySensor(
        _coordinator(hass), REGISTER_BY_KEY["hot_water_circulation_pump"]
    )
    assert entity.is_on is True


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_number_entity(hass: HomeAssistant) -> None:
    """Number delegates its validated write to the central coordinator."""
    coordinator = _coordinator(hass)
    coordinator.async_write_value = AsyncMock()
    entity = VaillantNumber(
        coordinator, REGISTER_BY_KEY["hot_water_target_temperature"]
    )
    assert entity.native_value == 50.0
    await entity.async_set_native_value(55.0)
    coordinator.async_write_value.assert_awaited_once_with(entity.definition, 55.0)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_select_entity(hass: HomeAssistant) -> None:
    """Select exposes translated option keys and delegates writes."""
    coordinator = _coordinator(hass)
    coordinator.async_write_value = AsyncMock()
    entity = VaillantSelect(coordinator, REGISTER_BY_KEY["heating_circuit_1_mode"])
    assert entity.current_option == "auto"
    await entity.async_select_option("night")
    coordinator.async_write_value.assert_awaited_once_with(entity.definition, "night")


def _loaded_entry(access_mode: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Vaillant Modbus Gateway",
        unique_id="bus-entry:1",
        data={CONF_CONNECTION: "bus-entry", CONF_UNIT_ID: 1},
        options={CONF_ACCESS_MODE: access_mode},
    )


def _entity_inventory(hass: HomeAssistant) -> dict[str, list[str]]:
    return {
        platform: sorted(hass.states.async_entity_ids(platform))
        for platform in ("binary_sensor", "number", "select", "sensor", "switch")
    }


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entity_inventory_is_identical_in_both_modes(
    hass: HomeAssistant,
) -> None:
    """Switching the access mode must not add, remove, or rename an entity."""
    entry = _loaded_entry(ACCESS_MODE_READ_ONLY)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.vaillant_modbus.async_get_unit_handle",
        return_value=MockUnit(_active_responses()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        read_only_inventory = _entity_inventory(hass)

        hass.config_entries.async_update_entry(
            entry, options={CONF_ACCESS_MODE: ACCESS_MODE_READ_WRITE}
        )
        # The options flow reloads the entry; the inventory must survive that.
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        read_write_inventory = _entity_inventory(hass)

    assert entry.runtime_data.read_only is False
    assert read_only_inventory == read_write_inventory
    assert read_only_inventory["number"]
    assert read_only_inventory["select"]
    assert read_only_inventory["switch"]


@pytest.mark.parametrize(
    ("service_domain", "service", "data", "entity_id"),
    [
        (
            "number",
            "set_value",
            {"value": 55},
            "number.vaillant_hot_water_hot_water_target_temperature",
        ),
        (
            "select",
            "select_option",
            {"option": "night"},
            "select.vaillant_heating_circuit_1_mode",
        ),
        (
            "switch",
            "turn_on",
            {},
            "switch.vaillant_heating_circuit_1_ventilation_boost",
        ),
    ],
)
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_service_write_rejected_in_read_only_mode(
    hass: HomeAssistant,
    service_domain: str,
    service: str,
    data: dict[str, object],
    entity_id: str,
) -> None:
    """A real service call fails loudly and leaves the polled state untouched."""
    entry = _loaded_entry(ACCESS_MODE_READ_ONLY)
    entry.add_to_hass(hass)
    unit = MockUnit(_active_responses())

    with patch(
        "custom_components.vaillant_modbus.async_get_unit_handle",
        return_value=unit,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        before = hass.states.get(entity_id).state
        with pytest.raises(HomeAssistantError) as err:
            await hass.services.async_call(
                service_domain,
                service,
                {"entity_id": entity_id, **data},
                blocking=True,
            )
        await hass.async_block_till_done()

    assert err.value.translation_key == "read_only_mode"
    assert unit.writes == []
    assert hass.states.get(entity_id).state == before
