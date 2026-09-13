"""Constants for the Vaillant Modbus Gateway integration."""

from datetime import timedelta
from types import MappingProxyType
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "vaillant_modbus"
NAME: Final = "Vaillant Modbus Gateway"
VERSION: Final = "0.1.0"
MANUFACTURER: Final = "Vaillant"
MODEL: Final = "Gateway eBUS/Modbus SV2"

CONF_CONNECTION: Final = "connection"
CONF_UNIT_ID: Final = "unit_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_ACCESS_MODE: Final = "access_mode"

ACCESS_MODE_READ_ONLY: Final = "read_only"
ACCESS_MODE_READ_WRITE: Final = "read_write"
ACCESS_MODES: Final = (ACCESS_MODE_READ_ONLY, ACCESS_MODE_READ_WRITE)

# Safe default for new entries: no write ever reaches the heating system.
DEFAULT_ACCESS_MODE: Final = ACCESS_MODE_READ_ONLY
# Entries created before this option existed keep their previous behavior.
LEGACY_ACCESS_MODE: Final = ACCESS_MODE_READ_WRITE

CONF_HEATING_CIRCUIT_2: Final = "heating_circuit_2"
CONF_HEATING_CIRCUIT_3: Final = "heating_circuit_3"

# Heating circuits 2 and 3 require a VR71 extension. They are opt-in so that a
# single-circuit system is never cluttered with entities it can never serve.
DEFAULT_HEATING_CIRCUIT_ENABLED: Final = False
# Circuit number to option key. The key is also the component name used by the
# register map, the device identifier, and the poll-block capability.
HEATING_CIRCUIT_OPTIONS: Final = MappingProxyType(
    {2: CONF_HEATING_CIRCUIT_2, 3: CONF_HEATING_CIRCUIT_3}
)

DEFAULT_UNIT_ID: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 10
MIN_SCAN_INTERVAL: Final = 1
MAX_UNIT_ID: Final = 247
MAX_REGISTERS_PER_REQUEST: Final = 16
MESSAGE_SPACING_SECONDS: Final = 1.0

SCAN_INTERVAL_OPTIONS: Final = (5, 10, 30, 60)
DEFAULT_UPDATE_INTERVAL: Final = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

PLATFORMS: Final = (
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
)

MODBUS_CONNECTION_DOMAIN: Final = "modbus_connection"
