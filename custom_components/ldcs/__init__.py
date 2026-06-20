"""Legrand Data Center Solutions integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
import json
import logging
from pathlib import Path
import shutil

from homeassistant.config_entries import ConfigEntry
from homeassistant.components import mqtt
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    DEFAULT_PROFILE,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MODBUS_SLAVE_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_XERUS_MQTT_DATAPUSH,
    DEFAULT_XERUS_MQTT_PORT,
    DEFAULT_XERUS_MQTT_TLS,
    DOMAIN,
    MQTT_REFRESH_DEBOUNCE,
    PRODUCT_RACK_DASHBOARD,
    PRODUCT_USYSTEMS_RDHX,
    PRODUCT_XERUS_PDU,
    USYSTEMS_RDHX_PLATFORMS,
    XERUS_PLATFORMS,
)
from .dashboard import async_install_rack_dashboard
from .raritan_client import RaritanClient, RaritanError
from .usystems_rdhx import USystemsRdhxClient

try:
    from homeassistant.components.http import StaticPathConfig
except ImportError:
    StaticPathConfig = None

try:
    from homeassistant.components.http import async_register_static_paths
except ImportError:
    async_register_static_paths = None

_LOGGER = logging.getLogger(__name__)
MQTT_FLEET_TOPIC = "raritan/#"
STATIC_URL_PATH = "/local/ldcs"
STATIC_PATH = Path(__file__).parent / "www"
WWW_STATIC_PATH = Path("/config/www/ldcs")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up shared LDCS resources."""
    await _async_register_frontend_assets(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an LDCS device from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await _async_register_frontend_assets(hass)
    product_type = entry.data.get(CONF_PRODUCT_TYPE, PRODUCT_XERUS_PDU)
    if product_type == PRODUCT_USYSTEMS_RDHX:
        await _async_setup_usystems_rdhx(hass, entry)
        _async_schedule_dashboard_install(hass, entry)
        return True

    if product_type != PRODUCT_XERUS_PDU:
        await _async_setup_metadata_entry(hass, entry, product_type)
        _async_schedule_dashboard_install(hass, entry)
        return True

    rack_name = entry.data.get(CONF_RACK_NAME) or entry.options.get(CONF_RACK_NAME)
    if rack_name and entry.title != rack_name:
        hass.config_entries.async_update_entry(entry, title=rack_name)

    client = RaritanClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        profile=entry.options.get(CONF_PROFILE, entry.data.get(CONF_PROFILE, DEFAULT_PROFILE)),
        device_identifier=entry.unique_id,
        modbus_port=entry.data.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT),
        modbus_slave_id=entry.data.get(CONF_MODBUS_SLAVE_ID, DEFAULT_MODBUS_SLAVE_ID),
        rack_name=rack_name,
        rack_role=entry.data.get(CONF_RACK_ROLE) or entry.options.get(CONF_RACK_ROLE),
        rack_position=entry.data.get(CONF_RACK_POSITION) or entry.options.get(CONF_RACK_POSITION),
        mqtt_datapush_config=_mqtt_datapush_config(entry),
    )

    async def _async_update_data():
        try:
            return await hass.async_add_executor_job(client.update)
        except RaritanError as err:
            raise UpdateFailed(str(err)) from err

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )

    coordinator.async_set_updated_data({})

    runtime = {
        "client": client,
        "coordinator": coordinator,
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    _async_register_rack_parent(hass, entry, client)

    mqtt_refresh_cancel = None

    @callback
    def _async_mqtt_refresh(_now):
        nonlocal mqtt_refresh_cancel
        mqtt_refresh_cancel = None
        hass.async_create_task(coordinator.async_request_refresh())

    @callback
    def _async_mqtt_message(_message):
        nonlocal mqtt_refresh_cancel
        client.note_mqtt_message(
            topic=_message.topic,
            payload=_decode_mqtt_payload(_message.payload),
        )
        if mqtt_refresh_cancel is None:
            mqtt_refresh_cancel = async_call_later(
                hass,
                MQTT_REFRESH_DEBOUNCE,
                _async_mqtt_refresh,
            )

    try:
        runtime["mqtt_unsubscribe"] = await mqtt.async_subscribe(
            hass,
            client.mqtt_topic,
            _async_mqtt_message,
            qos=0,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Unable to subscribe to %s: %s", client.mqtt_topic, err)

    @callback
    def _async_cancel_mqtt_refresh():
        nonlocal mqtt_refresh_cancel
        if mqtt_refresh_cancel is not None:
            mqtt_refresh_cancel()
            mqtt_refresh_cancel = None

    runtime["mqtt_cancel_refresh"] = _async_cancel_mqtt_refresh
    await _async_setup_fleet_mqtt(hass)
    if client.mqtt_datapush_enabled:
        entry.async_create_background_task(
            hass,
            _async_ensure_mqtt_datapush(hass, client, coordinator, entry.title),
            name=f"{DOMAIN}_{entry.entry_id}_mqtt_datapush_setup",
        )

    await hass.config_entries.async_forward_entry_setups(entry, XERUS_PLATFORMS)
    _async_schedule_dashboard_install(hass, entry)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply option changes that do not need a full reload."""
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def _async_register_rack_parent(hass: HomeAssistant, entry: ConfigEntry, client: RaritanClient) -> None:
    """Register the rack parent before child entities are added."""
    if not client.rack_name:
        return
    device_info = client.rack_device_info
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=device_info["identifiers"],
        manufacturer=device_info.get("manufacturer"),
        model=device_info.get("model"),
        name=device_info.get("name"),
        configuration_url=device_info.get("configuration_url"),
    )


def _mqtt_datapush_config(entry: ConfigEntry) -> dict:
    """Return merged MQTT Data Push options for a Xerus device."""
    options = entry.options
    data = entry.data
    return {
        "enabled": bool(options.get(CONF_XERUS_MQTT_DATAPUSH, data.get(CONF_XERUS_MQTT_DATAPUSH, DEFAULT_XERUS_MQTT_DATAPUSH))),
        "host": str(options.get(CONF_XERUS_MQTT_HOST, data.get(CONF_XERUS_MQTT_HOST, ""))).strip(),
        "port": int(options.get(CONF_XERUS_MQTT_PORT, data.get(CONF_XERUS_MQTT_PORT, DEFAULT_XERUS_MQTT_PORT)) or DEFAULT_XERUS_MQTT_PORT),
        "tls": bool(options.get(CONF_XERUS_MQTT_TLS, data.get(CONF_XERUS_MQTT_TLS, DEFAULT_XERUS_MQTT_TLS))),
        "username": str(options.get(CONF_XERUS_MQTT_USERNAME, data.get(CONF_XERUS_MQTT_USERNAME, ""))).strip(),
        "password": str(options.get(CONF_XERUS_MQTT_PASSWORD, data.get(CONF_XERUS_MQTT_PASSWORD, ""))),
        "topic_prefix": str(options.get(CONF_XERUS_MQTT_TOPIC_PREFIX, data.get(CONF_XERUS_MQTT_TOPIC_PREFIX, ""))).strip(),
    }


def _decode_mqtt_payload(payload) -> object:
    """Decode an MQTT payload into JSON when possible."""
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace")
    else:
        text = str(payload)
    try:
        return json.loads(text)
    except ValueError:
        return text


async def _async_ensure_mqtt_datapush(
    hass: HomeAssistant,
    client: RaritanClient,
    coordinator: DataUpdateCoordinator,
    title: str,
) -> None:
    """Create/update Xerus MQTT data push entries and refresh state."""
    try:
        result = await hass.async_add_executor_job(client.ensure_mqtt_datapush)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Unable to configure Xerus MQTT Data Push for %s: %s", title, err)
        return
    _LOGGER.info("Xerus MQTT Data Push configuration for %s: %s", title, result)
    await coordinator.async_request_refresh()


async def _async_register_frontend_assets(hass: HomeAssistant) -> None:
    """Serve bundled LDCS Lovelace cards from the integration."""
    registered_key = f"{DOMAIN}_static_registered"
    if hass.data.get(registered_key):
        return
    if not STATIC_PATH.exists():
        _LOGGER.warning("Unable to register LDCS frontend assets: %s is missing", STATIC_PATH)
        return
    try:
        WWW_STATIC_PATH.mkdir(parents=True, exist_ok=True)
        for source in STATIC_PATH.glob("*.js"):
            target = WWW_STATIC_PATH / source.name
            if not target.exists() or source.stat().st_mtime_ns != target.stat().st_mtime_ns:
                shutil.copy2(source, target)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Unable to copy LDCS frontend assets from %s to %s: %s", STATIC_PATH, WWW_STATIC_PATH, err)
        return
    _LOGGER.info("Installed LDCS frontend assets at %s from %s", WWW_STATIC_PATH, STATIC_PATH)
    hass.data[registered_key] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an LDCS config entry."""
    product_type = entry.data.get(CONF_PRODUCT_TYPE, PRODUCT_XERUS_PDU)
    if product_type == PRODUCT_USYSTEMS_RDHX:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, USYSTEMS_RDHX_PLATFORMS)
        if unload_ok:
            hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        return unload_ok

    if product_type != PRODUCT_XERUS_PDU:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        return True

    unload_ok = await hass.config_entries.async_unload_platforms(entry, XERUS_PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id, {})
        if unsubscribe := runtime.get("mqtt_unsubscribe"):
            unsubscribe()
        if cancel_refresh := runtime.get("mqtt_cancel_refresh"):
            cancel_refresh()
        if not hass.data[DOMAIN]:
            if unsubscribe := hass.data.pop(f"{DOMAIN}_mqtt_unsubscribe", None):
                unsubscribe()
            if cancel_refresh := hass.data.pop(f"{DOMAIN}_mqtt_cancel_refresh", None):
                cancel_refresh()
    return unload_ok


async def _async_setup_usystems_rdhx(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up a USystems RDHx Modbus device from a config entry."""
    client = USystemsRdhxClient(entry.data)

    async def _async_update_data():
        return await hass.async_add_executor_job(client.update)

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{entry.entry_id}",
        update_method=_async_update_data,
        update_interval=timedelta(seconds=scan_interval),
    )
    coordinator.async_set_updated_data({})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "product_type": PRODUCT_USYSTEMS_RDHX,
    }
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, USYSTEMS_RDHX_PLATFORMS)


async def _async_setup_metadata_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    product_type: str,
) -> None:
    """Register non-Xerus LDCS entries until their native adapters are enabled."""
    rack_name = entry.data.get(CONF_RACK_NAME)
    rack_position = entry.data.get(CONF_RACK_POSITION)
    rack_role = entry.data.get(CONF_RACK_ROLE)
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        manufacturer="Legrand",
        name=entry.title,
        model=_model_name(product_type),
        configuration_url=f"http://{entry.data[CONF_HOST]}" if CONF_HOST in entry.data else None,
        suggested_area=rack_name,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "product_type": product_type,
        "rack_name": rack_name,
        "rack_position": rack_position,
        "rack_role": rack_role,
    }


def _model_name(product_type: str) -> str:
    """Return a user-facing model label for an LDCS product type."""
    if product_type == PRODUCT_USYSTEMS_RDHX:
        return "USystems RDHx"
    if product_type == PRODUCT_RACK_DASHBOARD:
        return "Rack dashboard"
    return "LDCS device"


async def _async_setup_fleet_mqtt(hass: HomeAssistant) -> None:
    """Subscribe once to the shared Xerus topic prefix."""
    unsubscribe_key = f"{DOMAIN}_mqtt_unsubscribe"
    cancel_key = f"{DOMAIN}_mqtt_cancel_refresh"
    if unsubscribe_key in hass.data:
        return

    mqtt_refresh_cancel = None

    @callback
    def _async_refresh_fleet(_now):
        nonlocal mqtt_refresh_cancel
        mqtt_refresh_cancel = None
        for runtime in hass.data.get(DOMAIN, {}).values():
            hass.async_create_task(runtime["coordinator"].async_request_refresh())

    @callback
    def _async_mqtt_message(_message):
        nonlocal mqtt_refresh_cancel
        if mqtt_refresh_cancel is None:
            mqtt_refresh_cancel = async_call_later(
                hass,
                MQTT_REFRESH_DEBOUNCE,
                _async_refresh_fleet,
            )

    @callback
    def _async_cancel_refresh():
        nonlocal mqtt_refresh_cancel
        if mqtt_refresh_cancel is not None:
            mqtt_refresh_cancel()
            mqtt_refresh_cancel = None

    try:
        hass.data[unsubscribe_key] = await mqtt.async_subscribe(
            hass,
            MQTT_FLEET_TOPIC,
            _async_mqtt_message,
            qos=0,
        )
        hass.data[cancel_key] = _async_cancel_refresh
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Unable to subscribe to %s: %s", MQTT_FLEET_TOPIC, err)


def _dashboard_requested(entry: ConfigEntry) -> bool:
    """Return whether this entry asked for dashboard generation."""
    return bool(
        entry.options.get(
            CONF_CREATE_DASHBOARD,
            entry.data.get(CONF_CREATE_DASHBOARD, False),
        )
    )


async def _async_maybe_install_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Install the dashboard if the entry requested one."""
    if not _dashboard_requested(entry):
        return
    try:
        await async_install_rack_dashboard(hass, entry)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Unable to install LDCS rack dashboard: %s", err)


def _async_schedule_dashboard_install(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Schedule dashboard installation after entity discovery has had time to run."""
    if not _dashboard_requested(entry):
        return
    hass.async_create_task(_async_maybe_install_dashboard(hass, entry))

    @callback
    def _async_install_later(_now):
        hass.async_create_task(_async_maybe_install_dashboard(hass, entry))

    entry.async_on_unload(async_call_later(hass, 30, _async_install_later))
