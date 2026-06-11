"""Config flow for Legrand Data Center Solutions."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CREATE_DASHBOARD,
    CONF_MODBUS_PORT,
    CONF_MODBUS_SLAVE_ID,
    CONF_PROFILE,
    CONF_PRODUCT_TYPE,
    CONF_RACK_NAME,
    CONF_RACK_POSITION,
    CONF_RACK_ROLE,
    CONF_VERIFY_SSL,
    CONF_XERUS_MQTT_DATAPUSH,
    CONF_XERUS_MQTT_HOST,
    CONF_XERUS_MQTT_PASSWORD,
    CONF_XERUS_MQTT_PORT,
    CONF_XERUS_MQTT_TLS,
    CONF_XERUS_MQTT_TOPIC_PREFIX,
    CONF_XERUS_MQTT_USERNAME,
    CONF_XERUS_TOPOLOGY,
    DEFAULT_CREATE_DASHBOARD,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MODBUS_SLAVE_ID,
    DEFAULT_PROFILE,
    DEFAULT_PRODUCT_TYPE,
    DEFAULT_RACK_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DEFAULT_XERUS_MQTT_DATAPUSH,
    DEFAULT_XERUS_MQTT_PORT,
    DEFAULT_XERUS_MQTT_TLS,
    DEFAULT_XERUS_TOPOLOGY,
    DOMAIN,
    PRODUCT_RACK_DASHBOARD,
    PRODUCT_USYSTEMS_RDHX,
    PRODUCT_XERUS_PDU,
)
from .raritan_client import RaritanClient, RaritanError


class LdcsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Legrand Data Center Solutions."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            product_type = user_input[CONF_PRODUCT_TYPE]
            if product_type == PRODUCT_XERUS_PDU:
                return await self.async_step_xerus_pdu()
            if product_type == PRODUCT_USYSTEMS_RDHX:
                return await self.async_step_usystems_rdhx()
            return await self.async_step_rack_dashboard()

        schema = vol.Schema(
            {
                vol.Required(CONF_PRODUCT_TYPE, default=DEFAULT_PRODUCT_TYPE): _product_selector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_xerus_pdu(self, user_input=None):
        """Add a Xerus-based rack PDU."""
        errors = {}

        if user_input is not None:
            client = RaritanClient(
                host=user_input[CONF_HOST],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                verify_ssl=user_input[CONF_VERIFY_SSL],
                profile=user_input[CONF_PROFILE],
                modbus_port=user_input[CONF_MODBUS_PORT],
                modbus_slave_id=user_input[CONF_MODBUS_SLAVE_ID],
            )
            try:
                metadata = await self.hass.async_add_executor_job(client.test_connection)
            except RaritanError:
                errors["base"] = "cannot_connect"
            else:
                self._xerus_user_input = user_input
                self._xerus_metadata = metadata
                return await self.async_step_xerus_mqtt()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_USERNAME, default="admin"): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
                vol.Required(CONF_PROFILE, default=DEFAULT_PROFILE): _profile_selector(),
                vol.Optional(CONF_MODBUS_PORT, default=DEFAULT_MODBUS_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_MODBUS_SLAVE_ID, default=DEFAULT_MODBUS_SLAVE_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=247)
                ),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=3600)
                ),
                vol.Optional(CONF_RACK_NAME, default=DEFAULT_RACK_NAME): str,
                vol.Optional(CONF_XERUS_TOPOLOGY, default=DEFAULT_XERUS_TOPOLOGY): _xerus_topology_selector(),
                vol.Optional(CONF_RACK_POSITION, default=""): str,
                vol.Optional(CONF_CREATE_DASHBOARD, default=DEFAULT_CREATE_DASHBOARD): bool,
            }
        )
        return self.async_show_form(
            step_id="xerus_pdu",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_xerus_mqtt(self, user_input=None):
        """Configure optional Xerus MQTT Data Push for the PDU."""
        base_input = getattr(self, "_xerus_user_input", None)
        metadata = getattr(self, "_xerus_metadata", {})
        if base_input is None:
            return await self.async_step_xerus_pdu()

        if user_input is not None:
            merged = {**base_input, **user_input}
            serial = metadata.get("serial_number") or merged[CONF_HOST]
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()
            title = merged.get(CONF_RACK_NAME) or metadata.get("name") or metadata.get("model") or merged[CONF_HOST]
            merged[CONF_PRODUCT_TYPE] = PRODUCT_XERUS_PDU
            merged[CONF_RACK_ROLE] = merged.get(CONF_XERUS_TOPOLOGY, DEFAULT_XERUS_TOPOLOGY)
            return self.async_create_entry(title=title, data=merged)

        schema = vol.Schema(_xerus_mqtt_fields())
        return self.async_show_form(step_id="xerus_mqtt", data_schema=schema)

    async def async_step_usystems_rdhx(self, user_input=None):
        """Add a USystems RDHx cooling device placeholder."""
        if user_input is not None:
            unique_id = (
                f"usystems_rdhx_{user_input[CONF_HOST]}_"
                f"{user_input[CONF_MODBUS_PORT]}_{user_input[CONF_MODBUS_SLAVE_ID]}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            user_input[CONF_PRODUCT_TYPE] = PRODUCT_USYSTEMS_RDHX
            title = f"USystems RDHx {user_input[CONF_HOST]}"
            return self.async_create_entry(title=title, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_MODBUS_PORT, default=DEFAULT_MODBUS_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_MODBUS_SLAVE_ID, default=DEFAULT_MODBUS_SLAVE_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=247)
                ),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=3600)
                ),
                vol.Optional(CONF_RACK_NAME, default=DEFAULT_RACK_NAME): str,
                vol.Optional(CONF_RACK_ROLE, default="cooling"): _rack_role_selector(),
                vol.Optional(CONF_RACK_POSITION, default="Rear door"): str,
                vol.Optional(CONF_CREATE_DASHBOARD, default=DEFAULT_CREATE_DASHBOARD): bool,
            }
        )
        return self.async_show_form(step_id="usystems_rdhx", data_schema=schema)

    async def async_step_rack_dashboard(self, user_input=None):
        """Create a rack/dashboard configuration entry."""
        if user_input is not None:
            rack_name = user_input[CONF_RACK_NAME]
            await self.async_set_unique_id(f"rack_dashboard_{rack_name.lower().replace(' ', '_')}")
            self._abort_if_unique_id_configured()
            user_input[CONF_PRODUCT_TYPE] = PRODUCT_RACK_DASHBOARD
            user_input[CONF_CREATE_DASHBOARD] = True
            return self.async_create_entry(title=f"{rack_name} dashboard", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_RACK_NAME, default=DEFAULT_RACK_NAME): str,
                vol.Optional(CONF_RACK_POSITION, default=""): str,
            }
        )
        return self.async_show_form(step_id="rack_dashboard", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return LdcsOptionsFlow(config_entry)


class LdcsOptionsFlow(config_entries.OptionsFlow):
    """Handle LDCS options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            if self._config_entry.data.get(CONF_PRODUCT_TYPE, PRODUCT_XERUS_PDU) == PRODUCT_XERUS_PDU:
                user_input[CONF_RACK_ROLE] = user_input.get(CONF_XERUS_TOPOLOGY, self._config_entry.data.get(CONF_RACK_ROLE))
            return self.async_create_entry(title="", data=user_input)

        product_type = self._config_entry.data.get(CONF_PRODUCT_TYPE, PRODUCT_XERUS_PDU)
        if product_type == PRODUCT_RACK_DASHBOARD:
            schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_CREATE_DASHBOARD,
                        default=self._config_entry.options.get(
                            CONF_CREATE_DASHBOARD,
                            self._config_entry.data.get(CONF_CREATE_DASHBOARD, True),
                        ),
                    ): bool,
                }
            )
            return self.async_show_form(step_id="init", data_schema=schema)

        scan_interval = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        fields = {
            vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=3600)
            ),
            vol.Optional(
                CONF_CREATE_DASHBOARD,
                default=self._config_entry.options.get(
                    CONF_CREATE_DASHBOARD,
                    self._config_entry.data.get(CONF_CREATE_DASHBOARD, DEFAULT_CREATE_DASHBOARD),
                ),
            ): bool,
        }
        if product_type == PRODUCT_XERUS_PDU:
            profile = self._config_entry.options.get(
                CONF_PROFILE,
                self._config_entry.data.get(CONF_PROFILE, DEFAULT_PROFILE),
            )
            fields = {
                vol.Optional(CONF_PROFILE, default=profile): _profile_selector(),
                **fields,
                vol.Optional(
                    CONF_XERUS_TOPOLOGY,
                    default=self._config_entry.options.get(
                        CONF_XERUS_TOPOLOGY,
                        self._config_entry.data.get(CONF_XERUS_TOPOLOGY, self._config_entry.data.get(CONF_RACK_ROLE, DEFAULT_XERUS_TOPOLOGY)),
                    ),
                ): _xerus_topology_selector(),
                vol.Optional(
                    CONF_XERUS_MQTT_DATAPUSH,
                    default=self._config_entry.options.get(
                        CONF_XERUS_MQTT_DATAPUSH,
                        self._config_entry.data.get(CONF_XERUS_MQTT_DATAPUSH, DEFAULT_XERUS_MQTT_DATAPUSH),
                    ),
                ): bool,
                vol.Optional(
                    CONF_XERUS_MQTT_HOST,
                    default=self._config_entry.options.get(
                        CONF_XERUS_MQTT_HOST,
                        self._config_entry.data.get(CONF_XERUS_MQTT_HOST, ""),
                    ),
                ): str,
                vol.Optional(
                    CONF_XERUS_MQTT_PORT,
                    default=self._config_entry.options.get(
                        CONF_XERUS_MQTT_PORT,
                        self._config_entry.data.get(CONF_XERUS_MQTT_PORT, DEFAULT_XERUS_MQTT_PORT),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Optional(
                    CONF_XERUS_MQTT_TLS,
                    default=self._config_entry.options.get(
                        CONF_XERUS_MQTT_TLS,
                        self._config_entry.data.get(CONF_XERUS_MQTT_TLS, DEFAULT_XERUS_MQTT_TLS),
                    ),
                ): bool,
                vol.Optional(
                    CONF_XERUS_MQTT_USERNAME,
                    default=self._config_entry.options.get(
                        CONF_XERUS_MQTT_USERNAME,
                        self._config_entry.data.get(CONF_XERUS_MQTT_USERNAME, ""),
                    ),
                ): str,
                vol.Optional(
                    CONF_XERUS_MQTT_PASSWORD,
                    default=self._config_entry.options.get(
                        CONF_XERUS_MQTT_PASSWORD,
                        self._config_entry.data.get(CONF_XERUS_MQTT_PASSWORD, ""),
                    ),
                ): str,
                vol.Optional(
                    CONF_XERUS_MQTT_TOPIC_PREFIX,
                    default=self._config_entry.options.get(
                        CONF_XERUS_MQTT_TOPIC_PREFIX,
                        self._config_entry.data.get(CONF_XERUS_MQTT_TOPIC_PREFIX, ""),
                    ),
                ): str,
            }
        schema = vol.Schema(fields)
        return self.async_show_form(step_id="init", data_schema=schema)


def _select(options: list[tuple[str, str]]) -> selector.SelectSelector:
    """Build a labelled dropdown selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"value": value, "label": label}
                for value, label in options
            ],
            mode="dropdown",
        )
    )


def _product_selector() -> selector.SelectSelector:
    """Return the LDCS product selector."""
    return _select(
        [
            (PRODUCT_XERUS_PDU, "Xerus rack PDU"),
            (PRODUCT_USYSTEMS_RDHX, "USystems RDHx cooling"),
            (PRODUCT_RACK_DASHBOARD, "Rack/dashboard only"),
        ]
    )


def _profile_selector() -> selector.SelectSelector:
    """Return the Xerus discovery profile selector."""
    return _select(
        [
            ("basic", "Basic - recommended for fleets"),
            ("power", "Power - broader electrical telemetry"),
            ("full", "Full - all discovered sensors"),
        ]
    )


def _xerus_mqtt_fields() -> dict:
    """Return the optional Xerus MQTT Data Push setup fields."""
    return {
        vol.Optional(CONF_XERUS_MQTT_DATAPUSH, default=DEFAULT_XERUS_MQTT_DATAPUSH): bool,
        vol.Optional(CONF_XERUS_MQTT_HOST, default=""): str,
        vol.Optional(CONF_XERUS_MQTT_PORT, default=DEFAULT_XERUS_MQTT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_XERUS_MQTT_TLS, default=DEFAULT_XERUS_MQTT_TLS): bool,
        vol.Optional(CONF_XERUS_MQTT_USERNAME, default=""): str,
        vol.Optional(CONF_XERUS_MQTT_PASSWORD, default=""): str,
        vol.Optional(CONF_XERUS_MQTT_TOPIC_PREFIX, default=""): str,
    }


def _rack_role_selector() -> selector.SelectSelector:
    """Return the rack role selector."""
    return _select(
        [
            ("left_pdu", "Left PDU rail"),
            ("right_pdu", "Right PDU rail"),
            ("cooling", "Cooling"),
            ("busway", "Busway or tap-off"),
            ("sensor_strip", "Sensor or asset strip"),
            ("rack", "Rack-level device"),
        ]
    )


def _xerus_topology_selector() -> selector.SelectSelector:
    """Return the Xerus rack topology selector."""
    return _select(
        [
            ("pdu_link_master", "PDU Link master - discover linked PDUs from this device"),
            ("standalone", "Standalone PDU - this device is the whole rack power view"),
            ("separate_rack_pdu", "Separate PDU in the same rack - add each PDU individually"),
        ]
    )
