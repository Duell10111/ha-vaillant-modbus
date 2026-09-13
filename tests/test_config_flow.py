"""Tests for Vaillant Modbus config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from custom_components.vaillant_modbus.const import (
    ACCESS_MODE_READ_ONLY,
    ACCESS_MODE_READ_WRITE,
    CONF_ACCESS_MODE,
    CONF_CONNECTION,
    CONF_HEATING_CIRCUIT_2,
    CONF_HEATING_CIRCUIT_3,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DOMAIN,
    MODBUS_CONNECTION_DOMAIN,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_coordinator import MockUnit, _active_responses


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


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_defaults_to_read_only(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """A new entry never writes until the user opts in."""
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
    assert result["options"] == {
        CONF_ACCESS_MODE: ACCESS_MODE_READ_ONLY,
        CONF_HEATING_CIRCUIT_2: False,
        CONF_HEATING_CIRCUIT_3: False,
    }


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_with_write_access(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """The chosen access mode is stored as an option, not as entry data."""
    with patch(
        "custom_components.vaillant_modbus.config_flow._async_validate_input",
        AsyncMock(return_value="1.20.0"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_CONNECTION: connection_entry.entry_id,
                CONF_UNIT_ID: 1,
                CONF_ACCESS_MODE: ACCESS_MODE_READ_WRITE,
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_ACCESS_MODE: ACCESS_MODE_READ_WRITE,
        CONF_HEATING_CIRCUIT_2: False,
        CONF_HEATING_CIRCUIT_3: False,
    }
    assert CONF_ACCESS_MODE not in result["data"]


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_can_enable_one_heating_circuit(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """Optional circuits are opt-in and can be enabled one at a time."""
    with patch(
        "custom_components.vaillant_modbus.config_flow._async_validate_input",
        AsyncMock(return_value="1.20.0"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_CONNECTION: connection_entry.entry_id,
                CONF_UNIT_ID: 1,
                CONF_HEATING_CIRCUIT_2: True,
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_HEATING_CIRCUIT_2] is True
    assert result["options"][CONF_HEATING_CIRCUIT_3] is False


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_rejects_unknown_access_mode(
    hass: HomeAssistant, connection_entry: MockConfigEntry
) -> None:
    """An unknown access mode is rejected before any gateway traffic."""
    with patch(
        "custom_components.vaillant_modbus.config_flow._async_validate_input",
        AsyncMock(),
    ) as validate:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_CONNECTION: connection_entry.entry_id,
                CONF_UNIT_ID: 1,
                CONF_ACCESS_MODE: "write_only",
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_access_mode"}
    validate.assert_not_awaited()


async def _change_access_mode(
    hass: HomeAssistant, options: dict[str, object], new_mode: str
) -> MockConfigEntry:
    """Load an entry, run the options flow, and return the updated entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vaillant Modbus Gateway",
        unique_id="bus-entry:1",
        data={CONF_CONNECTION: "bus-entry", CONF_UNIT_ID: 1},
        options=options,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.vaillant_modbus.async_get_unit_handle",
        return_value=MockUnit(_active_responses()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_SCAN_INTERVAL: str(options[CONF_SCAN_INTERVAL]),
                CONF_ACCESS_MODE: new_mode,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

    return entry


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_enable_single_heating_circuit(hass: HomeAssistant) -> None:
    """Enabling circuit 3 alone must leave circuit 2 and the other options alone."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vaillant Modbus Gateway",
        unique_id="bus-entry:1",
        data={CONF_CONNECTION: "bus-entry", CONF_UNIT_ID: 1},
        options={
            CONF_SCAN_INTERVAL: 30,
            CONF_ACCESS_MODE: ACCESS_MODE_READ_ONLY,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.vaillant_modbus.async_get_unit_handle",
        return_value=MockUnit(_active_responses()),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.data.capabilities.heating_circuits == (1,)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={
                CONF_SCAN_INTERVAL: "30",
                CONF_ACCESS_MODE: ACCESS_MODE_READ_ONLY,
                CONF_HEATING_CIRCUIT_2: False,
                CONF_HEATING_CIRCUIT_3: True,
            },
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

    assert entry.options[CONF_HEATING_CIRCUIT_2] is False
    assert entry.options[CONF_HEATING_CIRCUIT_3] is True
    assert entry.options[CONF_ACCESS_MODE] == ACCESS_MODE_READ_ONLY
    assert int(entry.options[CONF_SCAN_INTERVAL]) == 30
    assert entry.runtime_data.data.capabilities.heating_circuits == (1, 3)
    assert hass.states.get("select.vaillant_heating_circuit_3_mode") is not None
    assert hass.states.get("select.vaillant_heating_circuit_2_mode") is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_switch_to_read_only_keeps_scan_interval(
    hass: HomeAssistant,
) -> None:
    """Changing the access mode must not drop the polling interval."""
    entry = await _change_access_mode(
        hass,
        {CONF_SCAN_INTERVAL: 30, CONF_ACCESS_MODE: ACCESS_MODE_READ_WRITE},
        ACCESS_MODE_READ_ONLY,
    )
    assert entry.options[CONF_ACCESS_MODE] == ACCESS_MODE_READ_ONLY
    assert int(entry.options[CONF_SCAN_INTERVAL]) == 30
    assert entry.runtime_data.read_only is True


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_options_switch_back_to_read_write(hass: HomeAssistant) -> None:
    """The way back to writing is a single options change."""
    entry = await _change_access_mode(
        hass,
        {CONF_SCAN_INTERVAL: 10, CONF_ACCESS_MODE: ACCESS_MODE_READ_ONLY},
        ACCESS_MODE_READ_WRITE,
    )
    assert entry.options[CONF_ACCESS_MODE] == ACCESS_MODE_READ_WRITE
    assert int(entry.options[CONF_SCAN_INTERVAL]) == 10
    assert entry.runtime_data.read_only is False
