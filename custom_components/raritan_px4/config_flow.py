"""Config flow for Raritan PX4."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback

from .const import (
    CONF_PROFILE,
    CONF_VERIFY_SSL,
    DEFAULT_PROFILE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    PROFILES,
)
from .raritan_client import RaritanClient, RaritanError


class RaritanPx4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Raritan PX4."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            client = RaritanClient(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                verify_ssl=user_input[CONF_VERIFY_SSL],
                profile=user_input[CONF_PROFILE],
            )
            try:
                metadata = await self.hass.async_add_executor_job(client.test_connection)
            except RaritanError:
                errors["base"] = "cannot_connect"
            else:
                serial = metadata.get("serial_number") or user_input[CONF_HOST]
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()
                title = metadata.get("name") or metadata.get("model") or user_input[CONF_HOST]
                return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_USERNAME, default="admin"): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
                vol.Required(CONF_PROFILE, default=DEFAULT_PROFILE): vol.In(PROFILES),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=3600)
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return RaritanPx4OptionsFlow(config_entry)


class RaritanPx4OptionsFlow(config_entries.OptionsFlow):
    """Handle Raritan PX4 options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        scan_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        profile = self._config_entry.options.get(
            CONF_PROFILE,
            self._config_entry.data.get(CONF_PROFILE, DEFAULT_PROFILE),
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_PROFILE, default=profile): vol.In(PROFILES),
                vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=3600)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
