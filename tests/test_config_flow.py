"""Tests for Vaillant Modbus config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from custom_components.vaillant_modbus.const import (
    CONF_CONNECTION,
    CONF_UNIT_ID,
    DOMAIN,
    MODBUS_CONNECTION_DOMAIN,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def connection_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Add a selectable modern shared connection entry."""
    entry = MockConfigEntry(
        domain=MODBUS_CONNECTION_DOMAIN,
        title="Heating bus",
        entry_id="bus-entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_successful_setup(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """Validate gateway registers and create a config entry."""
    with patch(
        "custom_components.vaillant_modbus.config_flow._async_validate_input",
        AsyncMock(return_value="1.20.0"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_CONNECTION: connection_entry.entry_id, CONF_UNIT_ID: 1},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UNIT_ID] == 1


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_connection_not_reachable(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """Show a meaningful connection error."""
    with patch(
        "custom_components.vaillant_modbus.config_flow._async_validate_input",
        AsyncMock(side_effect=TimeoutError),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_CONNECTION: connection_entry.entry_id, CONF_UNIT_ID: 1},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_invalid_unit_id(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """Reject an out-of-range unit even when called with raw input."""
    with patch(
        "custom_components.vaillant_modbus.config_flow._async_validate_input",
        AsyncMock(),
    ) as validate:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_CONNECTION: connection_entry.entry_id, CONF_UNIT_ID: 248},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_unit_id"}
    validate.assert_not_awaited()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_duplicate_entry(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """Prevent duplicate connection and Unit ID pairs."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"{connection_entry.entry_id}:1",
        data={CONF_CONNECTION: connection_entry.entry_id, CONF_UNIT_ID: 1},
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_CONNECTION: connection_entry.entry_id, CONF_UNIT_ID: 1},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
