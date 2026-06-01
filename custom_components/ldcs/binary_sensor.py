"""Binary sensors for Legrand Data Center Solutions devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .usystems_rdhx import RDHX_BINARY_SENSORS


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up LDCS binary sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    if runtime.get("product_type") != "usystems_rdhx":
        return
    client = runtime["client"]
    coordinator = runtime["coordinator"]
    async_add_entities(
        RdhxBinarySensor(coordinator, client, entry.entry_id, register)
        for register in RDHX_BINARY_SENSORS
    )


class RdhxBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a USystems RDHx discrete input."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry_id, register):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._register = register
        self._attr_unique_id = f"{entry_id}_{register.key}"
        self._attr_name = register.name
        self._attr_device_info = client.device_info
        if register.device_class == "problem":
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def available(self):
        """Return whether the sensor is available."""
        value = self.coordinator.data.get(self._register.key)
        return value is not None and value.get("available", False)

    @property
    def is_on(self):
        """Return whether the discrete input is on."""
        value = self.coordinator.data.get(self._register.key)
        if not value:
            return None
        return value.get("value")

    @property
    def extra_state_attributes(self):
        """Return register metadata."""
        return {
            "ldcs_protocol": "modbus",
            "modbus_address": self._register.address,
            "modbus_register_type": "discrete_input",
        }
