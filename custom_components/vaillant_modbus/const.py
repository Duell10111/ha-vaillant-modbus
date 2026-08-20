"""Constants for the Vaillant Modbus Gateway integration."""

from datetime import timedelta
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
