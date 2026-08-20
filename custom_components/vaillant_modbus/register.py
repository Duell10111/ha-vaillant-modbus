"""Declarative register map and safe codecs for the Vaillant SV2 gateway.

Register 600-613 (time programs) are deliberately not represented here. The
manual specifies a transactional workflow: select day/system (601/602), wait
for busy (603), edit time slots, then trigger synchronization with register
600. Registers 605-613 are also overwritten from eBUS every four hours, and
register 604 can queue a manual synchronization. Treating these registers as
independent number entities would be unsafe and racy. A future implementation
must model the complete transaction as one operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from .const import MAX_REGISTERS_PER_REQUEST


class RegisterDataType(StrEnum):
    """Supported register encodings."""

    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    BOOL = "bool"
    ENUM = "enum"
    VERSION = "version"


class RegisterPlatform(StrEnum):
    """Home Assistant platform used for a definition."""

    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"
    SELECT = "select"
    SWITCH = "switch"


class RegisterAccessError(ValueError):
    """Raised when attempting to write a read-only register."""


class RegisterValueError(ValueError):
    """Raised when a value cannot safely be encoded."""


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
    """Describe one logical value backed by one or more holding registers."""

    key: str
    address: int
    platform: RegisterPlatform
    data_type: RegisterDataType = RegisterDataType.UINT16
    scale: float = 1.0
    unit: str | None = None
    writable: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    enum: MappingProxyType[int, str] | None = None
    device_class: str | None = None
    state_class: str | None = None
    entity_category: str | None = None
    component: str = "gateway"
    block: str = ""
    icon: str | None = None

    @property
    def width(self) -> int:
        """Return the number of 16-bit registers used by this definition."""
        return {
            RegisterDataType.UINT32: 2,
            RegisterDataType.UINT64: 4,
            RegisterDataType.VERSION: 3,
        }.get(self.data_type, 1)


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    """A contiguous read request."""

    key: str
    address: int
    count: int
    optional: bool = True
    capability: str | None = None

    def __post_init__(self) -> None:
        if self.address == 0:
            raise ValueError("Modbus register 0 is reserved")
        if not 1 <= self.count <= MAX_REGISTERS_PER_REQUEST:
            raise ValueError(
                f"Block {self.key} has invalid count {self.count}; "
                f"maximum is {MAX_REGISTERS_PER_REQUEST}"
            )

    @property
    def end(self) -> int:
        """Return the inclusive final register address."""
        return self.address + self.count - 1


def _enum(**values: int) -> MappingProxyType[int, str]:
    """Build an immutable raw-value to translation-option mapping."""
    return MappingProxyType({raw: key for key, raw in values.items()})


HC_MODE: Final = _enum(off=0, auto=1, day_manual=2, night=3)
SPECIAL_MODE: Final = _enum(
    none=0,
    ventilation=1,
    manual_cooling=2,
    party=3,
    quick_veto=4,
    holiday_day=5,
    bank_holiday=6,
    away_days=7,
    holidays=8,
    one_time_cylinder_charge=9,
    system_off=10,
)
CONTROLLER_VERSION: Final = _enum(vrc_700=700, vrc_720=720)
ENERGY_PROVIDER: Final = _enum(
    heat_pump_off=0,
    auxiliary_heater_off=1,
    heat_pump_and_auxiliary_heater_off=2,
    heating_off=3,
    cooling_off=4,
    heating_and_cooling_off=5,
)
HYBRID_MANAGER: Final = _enum(trivalent=0, bivalence_point=1)
AUXILIARY_HEATER_MODE: Final = _enum(
    off=0, heating=1, hot_water=2, heating_and_hot_water=3
)


def _r(
    key: str,
    address: int,
    platform: RegisterPlatform,
    *,
    data_type: RegisterDataType = RegisterDataType.UINT16,
    scale: float = 1.0,
    unit: str | None = None,
    writable: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    enum: MappingProxyType[int, str] | None = None,
    device_class: str | None = None,
    state_class: str | None = None,
    entity_category: str | None = None,
    component: str = "gateway",
    block: str,
    icon: str | None = None,
) -> RegisterDefinition:
    return RegisterDefinition(
        key=key,
        address=address,
        platform=platform,
        data_type=data_type,
        scale=scale,
        unit=unit,
        writable=writable,
        minimum=minimum,
        maximum=maximum,
        step=step,
        enum=enum,
        device_class=device_class,
        state_class=state_class,
        entity_category=entity_category,
        component=component,
        block=block,
        icon=icon,
    )


def _heating_circuit(number: int, base: int) -> tuple[RegisterDefinition, ...]:
    component = f"heating_circuit_{number}"
    prefix = component
    block = f"hc{number}"
    return (
        _r(
            f"{prefix}_target_flow_temperature",
            base,
            RegisterPlatform.SENSOR,
            scale=0.1,
            unit="°C",
            device_class="temperature",
            state_class="measurement",
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_flow_temperature",
            base + 1,
            RegisterPlatform.SENSOR,
            scale=0.1,
            unit="°C",
            device_class="temperature",
            state_class="measurement",
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_heating_curve",
            base + 2,
            RegisterPlatform.NUMBER,
            scale=0.01,
            writable=True,
            minimum=0.4,
            maximum=4.0,
            step=0.05,
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_minimum_flow_temperature",
            base + 3,
            RegisterPlatform.NUMBER,
            scale=0.1,
            unit="°C",
            writable=True,
            minimum=15,
            maximum=90,
            step=1,
            device_class="temperature",
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_maximum_flow_temperature",
            base + 4,
            RegisterPlatform.NUMBER,
            scale=0.1,
            unit="°C",
            writable=True,
            minimum=15,
            maximum=90,
            step=1,
            device_class="temperature",
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_mode",
            base + 5,
            RegisterPlatform.SELECT,
            data_type=RegisterDataType.ENUM,
            writable=True,
            enum=HC_MODE,
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_day_temperature",
            base + 6,
            RegisterPlatform.SENSOR,
            scale=0.1,
            unit="°C",
            device_class="temperature",
            state_class="measurement",
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_night_temperature",
            base + 7,
            RegisterPlatform.NUMBER,
            scale=0.1,
            unit="°C",
            writable=True,
            minimum=5,
            maximum=30,
            step=0.5,
            device_class="temperature",
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_pump",
            base + 8,
            RegisterPlatform.BINARY_SENSOR,
            data_type=RegisterDataType.BOOL,
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_special_mode",
            base + 9,
            RegisterPlatform.SWITCH,
            data_type=RegisterDataType.BOOL,
            writable=True,
            component=component,
            block=block,
        ),
        _r(
            f"{prefix}_outdoor_shutdown_temperature",
            base + 10,
            RegisterPlatform.NUMBER,
            scale=0.1,
            unit="°C",
            writable=True,
            minimum=10,
            maximum=99,
            step=0.1,
            device_class="temperature",
            component=component,
            block=block,
        ),
    )


def _heater(number: int, base: int) -> tuple[RegisterDefinition, ...]:
    component = f"heater_{number}"
    prefix = component
    status_block = f"heater{number}_status"
    energy_block = f"heater{number}_energy"
    definitions: list[RegisterDefinition] = []
    for index in range(5):
        definitions.append(
            _r(
                f"{prefix}_error_code_{index + 1}",
                base + index,
                RegisterPlatform.SENSOR,
                entity_category="diagnostic",
                component=component,
                block=status_block,
                icon="mdi:alert-circle-outline",
            )
        )
    definitions.extend(
        (
            _r(
                f"{prefix}_flow_temperature",
                base + 5,
                RegisterPlatform.SENSOR,
                unit="°C",
                device_class="temperature",
                state_class="measurement",
                component=component,
                block=status_block,
            ),
            _r(
                f"{prefix}_water_pressure",
                base + 6,
                RegisterPlatform.SENSOR,
                unit="bar",
                device_class="pressure",
                state_class="measurement",
                component=component,
                block=status_block,
            ),
            _r(
                f"{prefix}_modulation",
                base + 7,
                RegisterPlatform.SENSOR,
                unit="%",
                state_class="measurement",
                component=component,
                block=status_block,
            ),
            _r(
                f"{prefix}_flame",
                base + 8,
                RegisterPlatform.BINARY_SENSOR,
                data_type=RegisterDataType.BOOL,
                device_class="heat",
                component=component,
                block=status_block,
            ),
            _r(
                f"{prefix}_heating_pump",
                base + 9,
                RegisterPlatform.BINARY_SENSOR,
                data_type=RegisterDataType.BOOL,
                component=component,
                block=status_block,
            ),
            _r(
                f"{prefix}_charging_pump",
                base + 10,
                RegisterPlatform.BINARY_SENSOR,
                data_type=RegisterDataType.BOOL,
                component=component,
                block=status_block,
            ),
            _r(
                f"{prefix}_target_flow_temperature",
                base + 11,
                RegisterPlatform.SENSOR,
                unit="°C",
                device_class="temperature",
                state_class="measurement",
                component=component,
                block=status_block,
            ),
            _r(
                f"{prefix}_return_temperature",
                base + 12,
                RegisterPlatform.SENSOR,
                unit="°C",
                device_class="temperature",
                state_class="measurement",
                component=component,
                block=status_block,
            ),
        )
    )
    for offset, suffix in (
        (50, "gas_energy_heating"),
        (54, "gas_energy_hot_water"),
        (58, "electrical_energy_heating"),
        (62, "electrical_energy_hot_water"),
    ):
        definitions.append(
            _r(
                f"{prefix}_{suffix}",
                base + offset,
                RegisterPlatform.SENSOR,
                data_type=RegisterDataType.UINT64,
                unit="Wh",
                device_class="energy",
                state_class="total_increasing",
                component=component,
                block=energy_block,
            )
        )
    return tuple(definitions)


REGISTER_DEFINITIONS: Final = (
    # Gateway 3000-3005
    _r(
        "gateway_version",
        3000,
        RegisterPlatform.SENSOR,
        data_type=RegisterDataType.VERSION,
        entity_category="diagnostic",
        block="gateway",
        icon="mdi:chip",
    ),
    _r(
        "ebus_active",
        3003,
        RegisterPlatform.BINARY_SENSOR,
        data_type=RegisterDataType.BOOL,
        entity_category="diagnostic",
        block="gateway",
    ),
    _r(
        "controller_active",
        3004,
        RegisterPlatform.BINARY_SENSOR,
        data_type=RegisterDataType.BOOL,
        entity_category="diagnostic",
        block="gateway",
    ),
    _r(
        "vr71_available",
        3005,
        RegisterPlatform.BINARY_SENSOR,
        data_type=RegisterDataType.BOOL,
        entity_category="diagnostic",
        block="gateway",
    ),
    # System 550-567
    _r(
        "outdoor_temperature",
        550,
        RegisterPlatform.SENSOR,
        data_type=RegisterDataType.INT16,
        scale=0.1,
        unit="°C",
        device_class="temperature",
        state_class="measurement",
        component="system",
        block="system_status",
    ),
    _r(
        "controller_version",
        551,
        RegisterPlatform.SENSOR,
        data_type=RegisterDataType.ENUM,
        enum=CONTROLLER_VERSION,
        entity_category="diagnostic",
        component="system",
        block="system_status",
    ),
    _r(
        "system_special_mode",
        552,
        RegisterPlatform.SENSOR,
        data_type=RegisterDataType.ENUM,
        enum=SPECIAL_MODE,
        component="system",
        block="system_status",
    ),
    _r(
        "hydraulic_scheme",
        553,
        RegisterPlatform.SENSOR,
        entity_category="diagnostic",
        component="system",
        block="system_status",
    ),
    _r(
        "vr71_configuration",
        554,
        RegisterPlatform.SENSOR,
        entity_category="diagnostic",
        component="system",
        block="system_status",
    ),
    *(
        _r(
            key,
            address,
            RegisterPlatform.SENSOR,
            data_type=RegisterDataType.UINT32,
            unit="kWh",
            device_class="energy",
            state_class="total_increasing",
            component="system",
            block="system_energy",
        )
        for key, address in (
            ("system_gas_energy_heating", 560),
            ("system_electrical_energy_heating", 562),
            ("system_gas_energy_hot_water", 564),
            ("system_electrical_energy_hot_water", 566),
        )
    ),
    # Domestic hot water 1-8
    _r(
        "hot_water_target_temperature",
        1,
        RegisterPlatform.NUMBER,
        scale=0.1,
        unit="°C",
        writable=True,
        minimum=35,
        maximum=65,
        step=1,
        device_class="temperature",
        component="hot_water",
        block="hot_water",
    ),
    _r(
        "hot_water_temperature",
        2,
        RegisterPlatform.SENSOR,
        scale=0.1,
        unit="°C",
        device_class="temperature",
        state_class="measurement",
        component="hot_water",
        block="hot_water",
    ),
    _r(
        "hot_water_charging_hysteresis",
        4,
        RegisterPlatform.NUMBER,
        scale=0.1,
        unit="K",
        writable=True,
        minimum=3,
        maximum=20,
        step=0.5,
        component="hot_water",
        block="hot_water",
    ),
    _r(
        "hot_water_charging_offset",
        5,
        RegisterPlatform.NUMBER,
        scale=0.1,
        unit="K",
        writable=True,
        minimum=0,
        maximum=40,
        step=1,
        component="hot_water",
        block="hot_water",
    ),
    _r(
        "hot_water_maximum_charging_time",
        6,
        RegisterPlatform.NUMBER,
        unit="min",
        writable=True,
        minimum=15,
        maximum=120,
        step=5,
        device_class="duration",
        component="hot_water",
        block="hot_water",
    ),
    _r(
        "hot_water_heat_pump_blocking_time",
        7,
        RegisterPlatform.NUMBER,
        unit="min",
        writable=True,
        minimum=0,
        maximum=120,
        step=5,
        device_class="duration",
        component="hot_water",
        block="hot_water",
    ),
    _r(
        "hot_water_circulation_pump",
        8,
        RegisterPlatform.BINARY_SENSOR,
        data_type=RegisterDataType.BOOL,
        component="hot_water",
        block="hot_water",
    ),
    *_heating_circuit(1, 100),
    *_heating_circuit(2, 150),
    *_heating_circuit(3, 200),
    # Heat pump 500-507
    _r(
        "heat_pump_emergency_temperature",
        500,
        RegisterPlatform.NUMBER,
        scale=0.1,
        unit="°C",
        writable=True,
        minimum=20,
        maximum=80,
        step=0.1,
        device_class="temperature",
        component="heat_pump",
        block="heat_pump",
    ),
    _r(
        "heat_pump_heating_bivalence_point",
        501,
        RegisterPlatform.NUMBER,
        data_type=RegisterDataType.INT16,
        scale=0.1,
        unit="°C",
        writable=True,
        minimum=-30,
        maximum=20,
        step=0.1,
        device_class="temperature",
        component="heat_pump",
        block="heat_pump",
    ),
    _r(
        "heat_pump_hot_water_bivalence_point",
        502,
        RegisterPlatform.NUMBER,
        data_type=RegisterDataType.INT16,
        scale=0.1,
        unit="°C",
        writable=True,
        minimum=-20,
        maximum=20,
        step=0.1,
        device_class="temperature",
        component="heat_pump",
        block="heat_pump",
    ),
    _r(
        "heat_pump_energy_provider",
        503,
        RegisterPlatform.SELECT,
        data_type=RegisterDataType.ENUM,
        writable=True,
        enum=ENERGY_PROVIDER,
        component="heat_pump",
        block="heat_pump",
    ),
    _r(
        "heat_pump_cooling_start_temperature",
        504,
        RegisterPlatform.NUMBER,
        scale=0.1,
        unit="°C",
        writable=True,
        minimum=10,
        maximum=30,
        step=0.1,
        device_class="temperature",
        component="heat_pump",
        block="heat_pump",
    ),
    _r(
        "heat_pump_hybrid_manager",
        505,
        RegisterPlatform.SELECT,
        data_type=RegisterDataType.ENUM,
        writable=True,
        enum=HYBRID_MANAGER,
        component="heat_pump",
        block="heat_pump",
    ),
    _r(
        "heat_pump_heating_alternative_point",
        506,
        RegisterPlatform.NUMBER,
        data_type=RegisterDataType.INT16,
        scale=0.1,
        unit="°C",
        writable=True,
        minimum=-21,
        maximum=40,
        step=1,
        device_class="temperature",
        component="heat_pump",
        block="heat_pump",
    ),
    _r(
        "heat_pump_auxiliary_heater_mode",
        507,
        RegisterPlatform.SELECT,
        data_type=RegisterDataType.ENUM,
        writable=True,
        enum=AUXILIARY_HEATER_MODE,
        component="heat_pump",
        block="heat_pump",
    ),
    *_heater(1, 1000),
    *_heater(2, 1200),
)

REGISTER_BY_KEY: Final = MappingProxyType(
    {definition.key: definition for definition in REGISTER_DEFINITIONS}
)

POLL_BLOCKS: Final = (
    RegisterBlock("gateway", 3000, 6, optional=False),
    RegisterBlock("hot_water", 1, 8),
    RegisterBlock("hc1", 100, 11),
    RegisterBlock("hc2", 150, 11, capability="vr71"),
    RegisterBlock("hc3", 200, 11, capability="vr71"),
    RegisterBlock("heat_pump", 500, 8, capability="heat_pump"),
    RegisterBlock("system_status", 550, 5),
    RegisterBlock("system_energy", 560, 8),
    RegisterBlock("heater1_status", 1000, 13),
    RegisterBlock("heater1_energy", 1050, 16),
    RegisterBlock("heater2_status", 1200, 13, capability="heater_2"),
    RegisterBlock("heater2_energy", 1250, 16, capability="heater_2"),
)
POLL_BLOCK_BY_KEY: Final = MappingProxyType({block.key: block for block in POLL_BLOCKS})


def decode_registers(
    definition: RegisterDefinition, words: list[int] | tuple[int, ...]
) -> int | float | bool | str:
    """Decode big-endian 16-bit words according to a register definition."""
    if len(words) != definition.width:
        raise RegisterValueError(
            f"{definition.key} needs {definition.width} registers, got {len(words)}"
        )
    if any(not 0 <= word <= 0xFFFF for word in words):
        raise RegisterValueError(f"{definition.key} contains an invalid 16-bit word")

    if definition.data_type is RegisterDataType.VERSION:
        return ".".join(str(word) for word in words)

    raw = 0
    for word in words:
        raw = (raw << 16) | word

    if definition.data_type is RegisterDataType.INT16 and raw & 0x8000:
        raw -= 0x10000
    elif definition.data_type is RegisterDataType.BOOL:
        return bool(raw)
    elif definition.data_type is RegisterDataType.ENUM:
        if definition.enum is None:
            raise RegisterValueError(f"{definition.key} has no enum mapping")
        return definition.enum.get(raw, f"unknown_{raw}")

    scaled = raw * definition.scale
    if definition.scale == 1.0:
        return raw
    return float(scaled)


def encode_register(definition: RegisterDefinition, value: object) -> int:
    """Validate and encode one writable value for function 0x06."""
    if not definition.writable:
        raise RegisterAccessError(f"{definition.key} is read-only")
    if definition.width != 1:
        raise RegisterAccessError(
            f"{definition.key} is not a single-register writable value"
        )

    if definition.data_type is RegisterDataType.ENUM:
        if definition.enum is None or not isinstance(value, str):
            raise RegisterValueError(f"{definition.key} requires an enum option")
        reverse = {option: raw for raw, option in definition.enum.items()}
        if value not in reverse:
            raise RegisterValueError(
                f"{value!r} is not a valid option for {definition.key}"
            )
        return reverse[value]

    if definition.data_type is RegisterDataType.BOOL:
        if not isinstance(value, bool):
            raise RegisterValueError(f"{definition.key} requires a boolean")
        return int(value)

    try:
        numeric = Decimal(str(value))
        scale = Decimal(str(definition.scale))
    except (InvalidOperation, ValueError) as err:
        raise RegisterValueError(f"{definition.key} requires a number") from err
    if not numeric.is_finite():
        raise RegisterValueError(f"{definition.key} requires a finite number")

    if definition.minimum is not None and numeric < Decimal(str(definition.minimum)):
        raise RegisterValueError(
            f"{definition.key} must be at least {definition.minimum}"
        )
    if definition.maximum is not None and numeric > Decimal(str(definition.maximum)):
        raise RegisterValueError(
            f"{definition.key} must be at most {definition.maximum}"
        )
    if definition.step is not None:
        origin = Decimal(str(definition.minimum or 0))
        quotient = (numeric - origin) / Decimal(str(definition.step))
        if quotient != quotient.to_integral_value():
            raise RegisterValueError(
                f"{definition.key} must use step {definition.step}"
            )

    raw_decimal = numeric / scale
    if raw_decimal != raw_decimal.to_integral_value():
        raise RegisterValueError(f"{value!r} cannot be represented by {definition.key}")
    raw = int(raw_decimal)

    if definition.data_type is RegisterDataType.INT16:
        if not -0x8000 <= raw <= 0x7FFF:
            raise RegisterValueError(f"{definition.key} exceeds int16")
        return raw & 0xFFFF
    if not 0 <= raw <= 0xFFFF:
        raise RegisterValueError(f"{definition.key} exceeds uint16")
    return raw


def definitions_for_platform(
    platform: RegisterPlatform,
) -> tuple[RegisterDefinition, ...]:
    """Return all definitions belonging to a platform."""
    return tuple(
        definition
        for definition in REGISTER_DEFINITIONS
        if definition.platform is platform
    )


def validate_register_map() -> None:
    """Validate invariants in the declarative map."""
    if len(REGISTER_BY_KEY) != len(REGISTER_DEFINITIONS):
        raise ValueError("Register keys must be unique")
    for definition in REGISTER_DEFINITIONS:
        if definition.address == 0:
            raise ValueError(f"{definition.key} uses reserved register 0")
        block = POLL_BLOCK_BY_KEY[definition.block]
        if not (
            block.address <= definition.address
            and definition.address + definition.width - 1 <= block.end
        ):
            raise ValueError(f"{definition.key} is split or outside block {block.key}")
        if definition.writable and definition.width != 1:
            raise ValueError(f"{definition.key} would require a multi-register write")


validate_register_map()
