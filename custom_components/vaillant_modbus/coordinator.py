"""Coordinator and shared Modbus I/O for the Vaillant SV2 gateway."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .modbus_api import ModbusUnitHandle
from .register import (
    POLL_BLOCK_BY_KEY,
    POLL_BLOCKS,
    REGISTER_BY_KEY,
    REGISTER_DEFINITIONS,
    RegisterBlock,
    RegisterDefinition,
    decode_registers,
    encode_register,
)

_LOGGER = logging.getLogger(__name__)

# Re-probe conservative optional capabilities every 30 minutes at the default
# interval. This permits hardware added later to be discovered after a reload
# without hammering a gateway that does not have that component.
_OPTIONAL_PROBE_INTERVAL = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class VaillantCapabilities:
    """Capabilities conservatively inferred from gateway status and valid reads."""

    has_vr71: bool = False
    heating_circuits: int = 1
    has_heat_pump: bool = False
    has_heater_1: bool = False
    has_heater_2: bool = False


@dataclass(frozen=True, slots=True)
class VaillantData:
    """One coherent coordinator snapshot."""

    values: dict[str, Any] = field(default_factory=dict)
    raw_registers: dict[int, int] = field(default_factory=dict)
    available_blocks: frozenset[str] = frozenset()
    failed_optional_blocks: dict[str, str] = field(default_factory=dict)
    capabilities: VaillantCapabilities = VaillantCapabilities()
    last_successful_poll: datetime | None = None


type VaillantConfigEntry = ConfigEntry["VaillantCoordinator"]


class VaillantCoordinator(DataUpdateCoordinator[VaillantData]):
    """Poll all logical values through one shared per-unit Modbus handle."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VaillantConfigEntry,
        unit: ModbusUnitHandle,
        unit_id: int,
    ) -> None:
        """Initialize the coordinator."""
        scan_interval = max(
            MIN_SCAN_INTERVAL,
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )
        self.unit = unit
        self.unit_id = unit_id
        self._write_lock = asyncio.Lock()
        self._last_optional_probe: datetime | None = None
        self._reported_failed_blocks: set[str] = set()

    async def _async_read_block(self, block: RegisterBlock) -> list[int]:
        """Read and validate a single contiguous holding-register block."""
        words = await self.unit.read_holding_registers(block.address, block.count)
        if len(words) != block.count:
            raise ValueError(
                f"block {block.key} returned {len(words)} registers, "
                f"expected {block.count}"
            )
        if any(not isinstance(word, int) or not 0 <= word <= 0xFFFF for word in words):
            raise ValueError(f"block {block.key} returned invalid register data")
        return words

    @staticmethod
    def _decode_values(
        raw_registers: dict[int, int], available_blocks: set[str]
    ) -> dict[str, Any]:
        """Decode all definitions whose complete source block is available."""
        values: dict[str, Any] = {}
        for definition in REGISTER_DEFINITIONS:
            if definition.block not in available_blocks:
                continue
            words = [
                raw_registers[address]
                for address in range(
                    definition.address, definition.address + definition.width
                )
            ]
            values[definition.key] = decode_registers(definition, words)
        return values

    @staticmethod
    def _infer_capabilities(
        values: dict[str, Any],
        raw_registers: dict[int, int],
        available_blocks: set[str],
        previous: VaillantCapabilities,
    ) -> VaillantCapabilities:
        """Infer only capabilities backed by explicit or meaningful evidence."""
        has_vr71 = values.get("vr71_available") is True
        has_heat_pump = previous.has_heat_pump or (
            "heat_pump" in available_blocks
            and any(raw_registers.get(address, 0) != 0 for address in range(500, 508))
        )
        has_heater_1 = previous.has_heater_1 or bool(
            {"heater1_status", "heater1_energy"} & available_blocks
        )
        # There is no presence register for VR32. A successful all-zero read is
        # not sufficient evidence because the gateway may return placeholders.
        has_heater_2 = previous.has_heater_2 or (
            (
                "heater2_status" in available_blocks
                and any(
                    raw_registers.get(address, 0) != 0 for address in range(1200, 1213)
                )
            )
            or (
                "heater2_energy" in available_blocks
                and any(
                    raw_registers.get(address, 0) != 0 for address in range(1250, 1266)
                )
            )
        )
        return VaillantCapabilities(
            has_vr71=has_vr71,
            heating_circuits=3 if has_vr71 else 1,
            has_heat_pump=has_heat_pump,
            has_heater_1=has_heater_1,
            has_heater_2=has_heater_2,
        )

    def _optional_probe_due(self, now: datetime) -> bool:
        return (
            self._last_optional_probe is None
            or now - self._last_optional_probe >= _OPTIONAL_PROBE_INTERVAL
        )

    @staticmethod
    def _should_read_block(
        block: RegisterBlock,
        capabilities: VaillantCapabilities,
        probe_optional: bool,
    ) -> bool:
        if block.capability is None:
            return True
        if block.capability == "vr71":
            return capabilities.has_vr71
        if block.capability == "heat_pump":
            return capabilities.has_heat_pump or probe_optional
        if block.capability == "heater_2":
            return capabilities.has_heater_2 or probe_optional
        return False

    async def _async_update_data(self) -> VaillantData:
        """Poll the gateway in blocks of no more than sixteen registers."""
        now = dt_util.utcnow()
        raw_registers: dict[int, int] = {}
        available_blocks: set[str] = set()
        failed_optional_blocks: dict[str, str] = {}

        gateway_block = POLL_BLOCK_BY_KEY["gateway"]
        try:
            gateway_words = await self._async_read_block(gateway_block)
        except (OSError, TimeoutError, ValueError) as err:
            raise UpdateFailed(
                f"Unable to read Vaillant gateway unit {self.unit_id}: {err}"
            ) from err

        raw_registers.update(
            {
                gateway_block.address + offset: word
                for offset, word in enumerate(gateway_words)
            }
        )
        available_blocks.add(gateway_block.key)
        gateway_values = self._decode_values(raw_registers, available_blocks)

        # The gateway explicitly reports eBUS and controller liveness. Do not
        # surface stale subsystem data or waste bus traffic while either is down.
        if not gateway_values["ebus_active"] or not gateway_values["controller_active"]:
            previous = (
                self.data.capabilities
                if self.data is not None
                else VaillantCapabilities()
            )
            return VaillantData(
                values=gateway_values,
                raw_registers=raw_registers,
                available_blocks=frozenset(available_blocks),
                capabilities=VaillantCapabilities(
                    has_vr71=gateway_values["vr71_available"],
                    heating_circuits=(3 if gateway_values["vr71_available"] else 1),
                    has_heat_pump=previous.has_heat_pump,
                    has_heater_1=previous.has_heater_1,
                    has_heater_2=previous.has_heater_2,
                ),
                last_successful_poll=now,
            )

        initial_capabilities = VaillantCapabilities(
            has_vr71=gateway_values["vr71_available"],
            heating_circuits=3 if gateway_values["vr71_available"] else 1,
            has_heat_pump=(
                self.data.capabilities.has_heat_pump if self.data is not None else False
            ),
            has_heater_1=(
                self.data.capabilities.has_heater_1 if self.data is not None else False
            ),
            has_heater_2=(
                self.data.capabilities.has_heater_2 if self.data is not None else False
            ),
        )
        probe_optional = self._optional_probe_due(now)
        if probe_optional:
            self._last_optional_probe = now

        for block in POLL_BLOCKS:
            if block.key == gateway_block.key or not self._should_read_block(
                block, initial_capabilities, probe_optional
            ):
                continue
            try:
                words = await self._async_read_block(block)
            except (OSError, TimeoutError, ValueError) as err:
                if not block.optional:
                    raise UpdateFailed(
                        f"Required block {block.key} failed: {err}"
                    ) from err
                failed_optional_blocks[block.key] = str(err)
                continue
            raw_registers.update(
                {block.address + offset: word for offset, word in enumerate(words)}
            )
            available_blocks.add(block.key)

        values = self._decode_values(raw_registers, available_blocks)
        failed_keys = set(failed_optional_blocks)
        for block_key in failed_keys - self._reported_failed_blocks:
            block = POLL_BLOCK_BY_KEY[block_key]
            _LOGGER.debug(
                "Optional Modbus block %s (%s-%s) unavailable: %s",
                block.key,
                block.address,
                block.end,
                failed_optional_blocks[block_key],
            )
        for block_key in self._reported_failed_blocks - failed_keys:
            _LOGGER.debug("Optional Modbus block %s is available again", block_key)
        self._reported_failed_blocks = failed_keys

        capabilities = self._infer_capabilities(
            values, raw_registers, available_blocks, initial_capabilities
        )
        return VaillantData(
            values=values,
            raw_registers=raw_registers,
            available_blocks=frozenset(available_blocks),
            failed_optional_blocks=failed_optional_blocks,
            capabilities=capabilities,
            last_successful_poll=now,
        )

    def definition_is_supported(self, definition: RegisterDefinition) -> bool:
        """Return whether an entity should be created for the detected system."""
        component = definition.component
        capabilities = self.data.capabilities
        if component in {"gateway", "system", "hot_water", "heating_circuit_1"}:
            return True
        if component in {"heating_circuit_2", "heating_circuit_3"}:
            return capabilities.has_vr71
        if component == "heat_pump":
            return capabilities.has_heat_pump
        if component == "heater_1":
            return capabilities.has_heater_1
        if component == "heater_2":
            return capabilities.has_heater_2
        return False

    def definition_is_available(self, definition: RegisterDefinition) -> bool:
        """Return whether the definition has fresh, valid source data."""
        if definition.block not in self.data.available_blocks:
            return False
        if definition.component != "gateway" and (
            self.data.values.get("ebus_active") is not True
            or self.data.values.get("controller_active") is not True
        ):
            return False
        return definition.key in self.data.values

    async def async_write_value(
        self, definition: RegisterDefinition, value: object
    ) -> None:
        """Safely encode, write with function 0x06, and refresh shared state."""
        raw = encode_register(definition, value)
        if not self.definition_is_available(definition):
            raise HomeAssistantError(
                f"{definition.key} is unavailable and cannot be written"
            )

        async with self._write_lock:
            try:
                await self.unit.write_register(definition.address, raw)
            except (OSError, TimeoutError, ValueError) as err:
                raise HomeAssistantError(
                    f"Unable to write {definition.key}: {err}"
                ) from err
        await self.async_request_refresh()


async def async_validate_gateway(unit: ModbusUnitHandle) -> str:
    """Validate a unit by reading the complete gateway identification block."""
    words = await unit.read_holding_registers(3000, 6)
    if len(words) != 6 or any(
        not isinstance(word, int) or not 0 <= word <= 0xFFFF for word in words
    ):
        raise ValueError("Invalid response for gateway registers 3000-3005")
    return str(decode_registers(REGISTER_BY_KEY["gateway_version"], words[:3]))
