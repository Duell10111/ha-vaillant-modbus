"""Tests for pooled polling and partial failure behavior."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from custom_components.vaillant_modbus.const import (
    ACCESS_MODE_READ_ONLY,
    ACCESS_MODE_READ_WRITE,
    CONF_ACCESS_MODE,
    CONF_CONNECTION,
    CONF_UNIT_ID,
    DOMAIN,
)
from custom_components.vaillant_modbus.coordinator import VaillantCoordinator
from custom_components.vaillant_modbus.register import REGISTER_BY_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry


class MockUnit:
    """Small in-memory per-unit Modbus handle."""

    def __init__(
        self,
        responses: dict[int, list[int]] | None = None,
        failing: set[int] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.failing = failing or set()
        self.calls: list[tuple[int, int]] = []
        self.writes: list[tuple[int, int]] = []

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        self.calls.append((address, count))
        if address in self.failing:
            raise TimeoutError(f"timeout at {address}")
        return self.responses.get(address, [0] * count)

    async def write_register(self, address: int, value: int) -> None:
        self.writes.append((address, value))

    def set_message_spacing(self, seconds: float) -> None:
        return None

    def on_connection_lost(self, callback: Callable[[], None]) -> Callable[[], None]:
        return lambda: None


def _entry(
    hass: HomeAssistant, options: dict[str, Any] | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CONNECTION: "bus", CONF_UNIT_ID: 1},
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


def _active_responses() -> dict[int, list[int]]:
    return {
        3000: [1, 20, 0, 1, 1, 0],
        1: [500, 450, 0, 50, 100, 60, 30, 1],
        100: [350, 340, 120, 150, 700, 1, 210, 180, 1, 0, 200],
        500: [500, 0xFF9C, 0xFFCE, 0, 180, 1, 0xFF2E, 1],
        550: [0xFFCE, 720, 0, 8, 1],
        560: [0, 1, 0, 2, 0, 3, 0, 4],
        1000: [0, 0, 0, 0, 0, 45, 2, 50, 1, 1, 0, 50, 35],
        1050: list(range(1, 17)),
        1200: [0] * 13,
        1250: [0] * 16,
    }


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_successful_poll(hass: HomeAssistant) -> None:
    """Poll pooled blocks and decode coherent values."""
    unit = MockUnit(_active_responses())
    coordinator = VaillantCoordinator(hass, _entry(hass), unit, 1)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data.values["gateway_version"] == "1.20.0"
    assert coordinator.data.values["outdoor_temperature"] == -5.0
    assert coordinator.data.values["system_gas_energy_heating"] == 1
    assert coordinator.data.capabilities.has_heat_pump
    assert all(count <= 16 for _, count in unit.calls)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_timeout_on_required_gateway(hass: HomeAssistant) -> None:
    """A gateway timeout fails the coordinator update."""
    coordinator = VaillantCoordinator(hass, _entry(hass), MockUnit(failing={3000}), 1)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert "Unable to read Vaillant gateway" in str(coordinator.last_exception)


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_partial_optional_block_failure(hass: HomeAssistant) -> None:
    """One optional block is recorded without failing the whole update."""
    unit = MockUnit(_active_responses(), failing={500})
    coordinator = VaillantCoordinator(hass, _entry(hass), unit, 1)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert "heat_pump" in coordinator.data.failed_optional_blocks
    assert "gateway_version" in coordinator.data.values


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_gateway_offline(hass: HomeAssistant) -> None:
    """An unreachable gateway is distinct from optional component loss."""
    coordinator = VaillantCoordinator(hass, _entry(hass), MockUnit(failing={3000}), 1)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.data is None


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_ebus_inactive(hass: HomeAssistant) -> None:
    """eBUS inactivity keeps gateway diagnostics but skips subsystem traffic."""
    unit = MockUnit({3000: [1, 20, 0, 0, 1, 0]})
    coordinator = VaillantCoordinator(hass, _entry(hass), unit, 1)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.data.values["ebus_active"] is False
    assert unit.calls == [(3000, 6)]
    assert coordinator.data.available_blocks == frozenset({"gateway"})


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_write_rejected_in_read_only_mode(hass: HomeAssistant) -> None:
    """Read-only mode rejects the write before any bus traffic can happen."""
    unit = MockUnit(_active_responses())
    entry = _entry(hass, {CONF_ACCESS_MODE: ACCESS_MODE_READ_ONLY})
    coordinator = VaillantCoordinator(hass, entry, unit, 1)
    await coordinator.async_refresh()

    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_write_value(
            REGISTER_BY_KEY["hot_water_target_temperature"], 50.0
        )

    assert err.value.translation_key == "read_only_mode"
    assert unit.writes == []


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_write_allowed_in_read_write_mode(hass: HomeAssistant) -> None:
    """Read-write mode keeps the existing encode-and-write behavior."""
    unit = MockUnit(_active_responses())
    entry = _entry(hass, {CONF_ACCESS_MODE: ACCESS_MODE_READ_WRITE})
    coordinator = VaillantCoordinator(hass, entry, unit, 1)
    await coordinator.async_refresh()

    await coordinator.async_write_value(
        REGISTER_BY_KEY["hot_water_target_temperature"], 50.0
    )

    assert unit.writes == [(1, 500)]
    await coordinator.async_shutdown()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_missing_access_mode_option_writes(hass: HomeAssistant) -> None:
    """An entry without a stored access mode keeps writing as it did before."""
    unit = MockUnit(_active_responses())
    coordinator = VaillantCoordinator(hass, _entry(hass), unit, 1)
    await coordinator.async_refresh()

    assert coordinator.access_mode == ACCESS_MODE_READ_WRITE
    assert coordinator.read_only is False
    await coordinator.async_write_value(
        REGISTER_BY_KEY["hot_water_target_temperature"], 50.0
    )
    assert unit.writes == [(1, 500)]
    await coordinator.async_shutdown()
