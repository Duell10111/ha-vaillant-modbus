"""Tests for register encoding, decoding, and map invariants."""

from dataclasses import replace

import pytest
from custom_components.vaillant_modbus.const import MAX_REGISTERS_PER_REQUEST
from custom_components.vaillant_modbus.register import (
    POLL_BLOCKS,
    REGISTER_BY_KEY,
    RegisterAccessError,
    RegisterDataType,
    RegisterValueError,
    decode_registers,
    encode_register,
)


@pytest.mark.parametrize(
    ("key", "words", "expected"),
    [
        ("hydraulic_scheme", [42], 42),
        ("outdoor_temperature", [123], 12.3),
        ("outdoor_temperature", [0xFF9C], -10.0),
        ("system_gas_energy_heating", [0x1234, 0x5678], 0x12345678),
        (
            "heater_1_gas_energy_heating",
            [0x0001, 0x0002, 0x0003, 0x0004],
            0x0001000200030004,
        ),
        ("heating_circuit_1_heating_curve", [215], 2.15),
    ],
)
def test_decode_register_types(
    key: str, words: list[int], expected: int | float
) -> None:
    """Decode unsigned, signed, wide, and scaled values."""
    assert decode_registers(REGISTER_BY_KEY[key], words) == expected


def test_decode_scale_001() -> None:
    """Decode a 0.01-scaled integer exactly enough for HA state."""
    definition = replace(
        REGISTER_BY_KEY["hydraulic_scheme"],
        scale=0.01,
        data_type=RegisterDataType.UINT16,
    )
    assert decode_registers(definition, [215]) == 2.15


def test_encode_temperature() -> None:
    """Encode 21.5 degrees to the raw scaled value."""
    definition = replace(
        REGISTER_BY_KEY["hot_water_target_temperature"],
        minimum=0,
        maximum=100,
        step=0.1,
    )
    assert encode_register(definition, 21.5) == 215


def test_encode_negative_temperature() -> None:
    """Encode signed negative temperature using two's complement."""
    definition = REGISTER_BY_KEY["heat_pump_heating_bivalence_point"]
    assert encode_register(definition, -10.0) == 0xFF9C


@pytest.mark.parametrize("value", [34, 66])
def test_encode_minimum_maximum(value: float) -> None:
    """Reject values outside the documented safe range."""
    with pytest.raises(RegisterValueError):
        encode_register(REGISTER_BY_KEY["hot_water_target_temperature"], value)


def test_encode_invalid_enum() -> None:
    """Reject an unknown translated enum key."""
    with pytest.raises(RegisterValueError):
        encode_register(REGISTER_BY_KEY["heating_circuit_1_mode"], "vacation")


def test_encode_read_only() -> None:
    """Never permit writes to read-only definitions."""
    with pytest.raises(RegisterAccessError):
        encode_register(REGISTER_BY_KEY["outdoor_temperature"], 20)


def test_all_poll_blocks_are_safe() -> None:
    """Keep protocol hard limits and reserved register zero invariant."""
    assert all(1 <= block.count <= MAX_REGISTERS_PER_REQUEST for block in POLL_BLOCKS)
    assert all(block.address > 0 for block in POLL_BLOCKS)
