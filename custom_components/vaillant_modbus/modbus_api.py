"""Use Home Assistant-owned shared Modbus connections without opening a link.

The documented device API is ``modbus_connection``. Core versions from the
2026.7 transition can still expose only the existing YAML ``modbus`` hubs.
Both paths below borrow Home Assistant's connection and never construct,
configure, close, or reconnect a transport.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from importlib import import_module
from time import monotonic
from typing import Any, Protocol

from homeassistant.core import HomeAssistant

from .const import MODBUS_CONNECTION_DOMAIN

LEGACY_PREFIX = "legacy:"


class ModbusUnitHandle(Protocol):
    """Subset of the per-unit Modbus API used by this integration."""

    async def read_holding_registers(self, address: int, count: int) -> list[int]: ...

    async def write_register(self, address: int, value: int) -> None: ...

    def set_message_spacing(self, seconds: float) -> None: ...

    def on_connection_lost(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]: ...


class LegacyModbusUnit:
    """Adapt one Home Assistant-owned legacy ModbusHub to a unit handle."""

    def __init__(self, hub: Any, unit_id: int) -> None:
        self._hub = hub
        self._unit_id = unit_id
        self._spacing = 0.0
        self._last_request = 0.0
        self._spacing_lock = asyncio.Lock()

    def set_message_spacing(self, seconds: float) -> None:
        """Set minimum request spacing for this consumer."""
        self._spacing = max(0.0, seconds)

    async def _wait_for_spacing(self) -> None:
        async with self._spacing_lock:
            remaining = self._spacing - (monotonic() - self._last_request)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request = monotonic()

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        """Read through the existing serialized Home Assistant hub."""
        modbus_const = import_module("homeassistant.components.modbus.const")
        await self._wait_for_spacing()
        result = await self._hub.async_pb_call(
            self._unit_id,
            address,
            count,
            modbus_const.CALL_TYPE_REGISTER_HOLDING,
        )
        if result is None or not hasattr(result, "registers"):
            raise ConnectionError(
                f"legacy Modbus hub returned no registers for {address}:{count}"
            )
        return list(result.registers)

    async def write_register(self, address: int, value: int) -> None:
        """Write one holding register via function 0x06 on the existing hub."""
        modbus_const = import_module("homeassistant.components.modbus.const")
        await self._wait_for_spacing()
        result = await self._hub.async_pb_call(
            self._unit_id,
            address,
            value,
            modbus_const.CALL_TYPE_WRITE_REGISTER,
        )
        if result is None:
            raise ConnectionError(
                f"legacy Modbus hub rejected write to register {address}"
            )

    def on_connection_lost(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Return a no-op unsubscribe; the legacy hub reconnects itself."""

        def _unsubscribe() -> None:
            return None

        return _unsubscribe


class ModernModbusUnit:
    """Normalize errors from the official backend-neutral unit handle."""

    def __init__(self, unit: Any) -> None:
        self._unit = unit

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        """Read holding registers and normalize backend exceptions."""
        try:
            return list(await self._unit.read_holding_registers(address, count))
        except Exception as err:
            raise ConnectionError(str(err)) from err

    async def write_register(self, address: int, value: int) -> None:
        """Write a register and normalize backend exceptions."""
        try:
            await self._unit.write_register(address, value)
        except Exception as err:
            raise ConnectionError(str(err)) from err

    def set_message_spacing(self, seconds: float) -> None:
        """Delegate minimum request spacing."""
        self._unit.set_message_spacing(seconds)

    def on_connection_lost(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Delegate the connection-lost subscription."""
        return self._unit.on_connection_lost(callback)


def async_get_unit_handle(
    hass: HomeAssistant, connection_identifier: str, unit_id: int
) -> ModbusUnitHandle:
    """Borrow a modern unit or adapt an existing legacy Home Assistant hub."""
    if connection_identifier.startswith(LEGACY_PREFIX):
        hub_name = connection_identifier.removeprefix(LEGACY_PREFIX)
        modbus = import_module("homeassistant.components.modbus")
        return LegacyModbusUnit(modbus.get_hub(hass, hub_name), unit_id)

    component = import_module("homeassistant.components.modbus_connection")
    return ModernModbusUnit(
        component.async_get_unit(hass, connection_identifier, unit_id)
    )


def connection_options(hass: HomeAssistant) -> list[dict[str, str]]:
    """Return enabled modern entries and loaded legacy hubs for selection."""
    options = [
        {"value": entry.entry_id, "label": entry.title or entry.entry_id}
        for entry in sorted(
            hass.config_entries.async_entries(MODBUS_CONNECTION_DOMAIN),
            key=lambda item: item.title.casefold(),
        )
        if entry.disabled_by is None
    ]
    try:
        modbus_mod = import_module("homeassistant.components.modbus.modbus")
        hubs = hass.data.get(modbus_mod.DATA_MODBUS_HUBS, {})
    except (ImportError, AttributeError):
        hubs = {}
    options.extend(
        {
            "value": f"{LEGACY_PREFIX}{name}",
            "label": f"{name} (Home Assistant Modbus)",
        }
        for name in sorted(hubs)
    )
    return options
