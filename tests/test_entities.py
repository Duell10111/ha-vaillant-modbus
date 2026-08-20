"""Representative entity tests for every platform."""

from unittest.mock import AsyncMock

import pytest
from custom_components.vaillant_modbus.binary_sensor import VaillantBinarySensor
from custom_components.vaillant_modbus.const import (
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
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_coordinator import MockUnit


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
