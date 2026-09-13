"""Config and options flows for Vaillant Modbus Gateway."""

from __future__ import annotations

import logging
from typing import Any, override

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    ACCESS_MODES,
    CONF_ACCESS_MODE,
    CONF_CONNECTION,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_ACCESS_MODE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    LEGACY_ACCESS_MODE,
    MAX_UNIT_ID,
    NAME,
    SCAN_INTERVAL_OPTIONS,
)
from .coordinator import async_validate_gateway
from .modbus_api import async_get_unit_handle, connection_options

_LOGGER = logging.getLogger(__name__)


def _user_schema(hass: HomeAssistant) -> vol.Schema:
    """Return the setup form schema."""
    return vol.Schema(
        {
            vol.Required(CONF_CONNECTION): SelectSelector(
                SelectSelectorConfig(
                    options=connection_options(hass),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=MAX_UNIT_ID,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_ACCESS_MODE, default=DEFAULT_ACCESS_MODE
            ): _access_mode_selector(),
        }
    )


def _access_mode_selector() -> SelectSelector:
    """Return the shared access-mode selector used by both flows."""
    return SelectSelector(
        SelectSelectorConfig(
            options=list(ACCESS_MODES),
            mode=SelectSelectorMode.LIST,
            translation_key="access_mode",
        )
    )


async def _async_validate_input(
    hass: HomeAssistant, connection_entry_id: str, unit_id: int
) -> str:
    """Validate the selected shared connection and SV2 gateway registers."""
    unit = async_get_unit_handle(hass, connection_entry_id, unit_id)
    return await async_validate_gateway(unit)


class VaillantOptionsFlow(OptionsFlowWithReload):
    """Manage polling options and reload the entry after changes."""

    @override
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the coordinator polling interval and the access mode."""
        if user_input is not None:
            scan_interval = int(user_input[CONF_SCAN_INTERVAL])
            access_mode = str(user_input[CONF_ACCESS_MODE])
            # Options are replaced wholesale, so always write both keys.
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: scan_interval,
                    CONF_ACCESS_MODE: access_mode,
                },
            )

        current = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        current_access_mode = str(
            self.config_entry.options.get(CONF_ACCESS_MODE, LEGACY_ACCESS_MODE)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=str(current)
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                str(interval) for interval in SCAN_INTERVAL_OPTIONS
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="scan_interval",
                        )
                    ),
                    vol.Required(
                        CONF_ACCESS_MODE, default=current_access_mode
                    ): _access_mode_selector(),
                }
            ),
        )


class VaillantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup of a Vaillant gateway on a shared Modbus connection."""

    VERSION = 1

    @staticmethod
    @callback
    @override
    def async_get_options_flow(
        _config_entry: Any,
    ) -> VaillantOptionsFlow:
        """Return the options flow."""
        return VaillantOptionsFlow()

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a shared connection, unit ID, and validate the gateway."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                connection_entry_id = str(user_input[CONF_CONNECTION])
                unit_id = int(user_input[CONF_UNIT_ID])
                access_mode = str(user_input.get(CONF_ACCESS_MODE, DEFAULT_ACCESS_MODE))
            except (KeyError, TypeError, ValueError):
                errors["base"] = "invalid_unit_id"
            else:
                if not 1 <= unit_id <= MAX_UNIT_ID:
                    errors["base"] = "invalid_unit_id"
                elif access_mode not in ACCESS_MODES:
                    errors["base"] = "invalid_access_mode"
                else:
                    unique_id = f"{connection_entry_id}:{unit_id}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    try:
                        gateway_version = await _async_validate_input(
                            self.hass, connection_entry_id, unit_id
                        )
                    except (
                        ConfigEntryNotReady,
                        OSError,
                        TimeoutError,
                        ValueError,
                    ):
                        errors["base"] = "cannot_connect"
                    except Exception:  # pragma: no cover - defensive HA boundary
                        _LOGGER.exception(
                            "Unexpected error while validating Vaillant gateway"
                        )
                        errors["base"] = "unknown"
                    else:
                        existing = self._async_current_entries()
                        title = NAME if not existing else f"{NAME} {unit_id}"
                        return self.async_create_entry(
                            title=title,
                            data={
                                CONF_CONNECTION: connection_entry_id,
                                CONF_UNIT_ID: unit_id,
                                "gateway_version": gateway_version,
                            },
                            options={CONF_ACCESS_MODE: access_mode},
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _user_schema(self.hass), user_input or {}
            ),
            errors=errors,
        )
