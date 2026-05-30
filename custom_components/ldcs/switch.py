"""Redfish outlet switches for Xerus devices."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up switchable Redfish outlets."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    client = runtime["client"]
    coordinator = runtime["coordinator"]

    async def _async_discover_and_add():
        outlets = await hass.async_add_executor_job(client.discover_redfish_outlets)
        async_add_entities(
            [
                RaritanOutletSwitch(coordinator, client, entry.entry_id, outlet)
                for outlet in outlets
            ]
        )

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
