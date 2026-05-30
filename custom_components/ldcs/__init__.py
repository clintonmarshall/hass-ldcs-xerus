"""Legrand Data Center Solutions integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.components import mqtt
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_PROFILE,
    CONF_VERIFY_SSL,
    DEFAULT_PROFILE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MQTT_REFRESH_DEBOUNCE,
    PLATFORMS,
)
from .raritan_client import RaritanClient, RaritanError

_LOGGER = logging.getLogger(__name__)
MQTT_FLEET_TOPIC = "raritan/#"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an LDCS device from a config entry."""
    client = RaritanClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, False),
        profile=entry.options.get(CONF_PROFILE, entry.data.get(CONF_PROFILE, DEFAULT_PROFILE)),
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

    mqtt_refresh_cancel = None

    @callback
    def _async_mqtt_refresh(_now):
        nonlocal mqtt_refresh_cancel
        mqtt_refresh_cancel = None
        hass.async_create_task(coordinator.async_request_refresh())

    @callback
    def _async_mqtt_message(_message):
        nonlocal mqtt_refresh_cancel
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an LDCS config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
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
