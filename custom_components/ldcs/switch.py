"""Redfish outlet switches for Xerus devices."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CREATE_DASHBOARD, DOMAIN
from .dashboard import async_install_rack_dashboard

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up switchable Xerus controls."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    client = runtime["client"]
    coordinator = runtime["coordinator"]

    async def _async_discover_and_add():
        for _ in range(300):
            if client.sensor_descriptors:
                break
            await asyncio.sleep(1)
        if not client.sensor_descriptors:
            _LOGGER.warning(
                "LDCS switch setup for %s skipped writable state switches because sensor discovery did not finish in time",
                entry.title,
            )
        controllable_states = await hass.async_add_executor_job(
            client.controllable_state_descriptors
        ) if client.sensor_descriptors else []
        outlets = await hass.async_add_executor_job(client.discover_redfish_outlets)
        _LOGGER.info(
            "LDCS discovered %s Redfish outlet switches and %s writable state switches for %s",
            len(outlets),
            len(controllable_states),
            entry.title,
        )
        entities = [
            RaritanOutletSwitch(coordinator, client, entry.entry_id, outlet)
            for outlet in outlets
        ]
        entities.extend(
            RaritanControllableStateSwitch(coordinator, client, entry.entry_id, descriptor)
            for descriptor in controllable_states
        )
        async_add_entities(entities)
        if entry.options.get(CONF_CREATE_DASHBOARD, entry.data.get(CONF_CREATE_DASHBOARD, False)):
            await asyncio.sleep(2)
            await async_install_rack_dashboard(hass, entry)

    entry.async_create_background_task(
        hass,
        _async_discover_and_add(),
        name=f"{DOMAIN}_{entry.entry_id}_switch_discovery",
    )


class RaritanOutletSwitch(CoordinatorEntity, SwitchEntity):
    """A Xerus outlet controlled through Redfish."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry_id, outlet):
        """Initialize the outlet switch."""
        super().__init__(coordinator)
        self._client = client
        self._outlet = outlet
        self._attr_unique_id = f"{entry_id}_redfish_outlet_{outlet.outlet_id}"
        self._attr_name = f"Outlet {outlet.outlet_id} Power"
        self._attr_device_info = client.device_info

    @property
    def extra_state_attributes(self):
        """Return configured outlet name and protection metadata."""
        return {
            "configured_name": self._outlet.name,
            **self._client.outlet_details(self._outlet.outlet_id),
        }

    @property
    def is_on(self):
        """Return whether the outlet is on."""
        value = self.coordinator.data.get(self._client.outlet_state_key(self._outlet.outlet_id))
        if not value:
            return None
        return value.get("value") == 1

    @property
    def available(self):
        """Return whether the outlet state is available."""
        value = self.coordinator.data.get(self._client.outlet_state_key(self._outlet.outlet_id))
        return value is not None and value.get("available", False)

    async def async_turn_on(self, **kwargs):
        """Turn the outlet on."""
        await self.hass.async_add_executor_job(
            self._client.set_redfish_outlet_power,
            self._outlet.target,
            True,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the outlet off."""
        await self.hass.async_add_executor_job(
            self._client.set_redfish_outlet_power,
            self._outlet.target,
            False,
        )
        await self.coordinator.async_request_refresh()


class RaritanControllableStateSwitch(CoordinatorEntity, SwitchEntity):
    """A writable Xerus state sensor exposed as a Home Assistant switch."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry_id, descriptor):
        """Initialize a controllable state switch."""
        super().__init__(coordinator)
        self._client = client
        self._descriptor = descriptor
        self._attr_unique_id = f"{entry_id}_{descriptor.key}_control"
        self._attr_name = f"{descriptor.name} Control"
        self._attr_device_info = descriptor.device_info or client.device_info

    @property
    def available(self):
        """Return whether the state sensor value is available."""
        value = self.coordinator.data.get(self._descriptor.key)
        return value is not None and value.get("available", False)

    @property
    def is_on(self):
        """Return whether the controllable state is asserted."""
        value = self.coordinator.data.get(self._descriptor.key)
        if not value:
            return None
        return _switch_state_is_on(value.get("value"), value.get("attributes", {}))

    @property
    def extra_state_attributes(self):
        """Return source state sensor metadata."""
        value = self.coordinator.data.get(self._descriptor.key) or {}
        return {
            "source_entity_key": self._descriptor.key,
            "raritan_target": self._descriptor.target,
            "raritan_context": self._descriptor.context,
            "raritan_type": self._descriptor.type_name,
            "control_protocol": "json_rpc_setState",
            **(self._descriptor.attributes or {}),
            **(value.get("attributes", {})),
        }

    async def async_turn_on(self, **kwargs):
        """Assert/close/lock the writable state."""
        await self.hass.async_add_executor_job(
            self._client.set_controllable_state,
            self._descriptor.key,
            True,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Deassert/open/unlock the writable state."""
        await self.hass.async_add_executor_job(
            self._client.set_controllable_state,
            self._descriptor.key,
            False,
        )
        await self.coordinator.async_request_refresh()


def _switch_state_is_on(value, attributes):
    """Return Home Assistant switch state from Xerus state labels or raw values."""
    raw = str(attributes.get("raw_state", value)).lower()
    label = str(value).lower()
    return raw in {"1", "true"} or any(
        token in label
        for token in ("on", "closed", "locked", "active")
    )
