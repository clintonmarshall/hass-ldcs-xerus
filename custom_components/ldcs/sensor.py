"""Sensors for Legrand Data Center Solutions devices."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    PERCENTAGE,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .device_tree import async_register_xerus_device_tree
from .raritan_client import SensorKind
from .usystems_rdhx import RDHX_SENSORS

_LOGGER = logging.getLogger(__name__)

UNIT_MAP = {
    "AMPERE": UnitOfElectricCurrent.AMPERE,
    "VOLT": UnitOfElectricPotential.VOLT,
    "WATT": UnitOfPower.WATT,
    "WATT_HOUR": UnitOfEnergy.WATT_HOUR,
    "HZ": UnitOfFrequency.HERTZ,
    "PERCENT": PERCENTAGE,
    "DEGREE_CELSIUS": "°C",
    "DEGREE_FAHRENHEIT": "°F",
    "KELVIN": "K",
    "VOLT_AMP": "VA",
    "VOLT_AMP_REACTIVE": "var",
    "VOLT_AMP_HOUR": "VAh",
    "VOLT_AMP_REACTIVE_HOUR": "varh",
    "METER_PER_SEC": "m/s",
    "PASCAL": "Pa",
    "PSI": "psi",
    "METER": "m",
    "FOOT": "ft",
    "GRAM": "g",
    "OHM": "Ω",
    "RPM": "rpm",
    "SECOND": "s",
    "MINUTE": "min",
    "HOUR": "h",
}

DEVICE_CLASS_MAP = {
    "CURRENT": SensorDeviceClass.CURRENT,
    "ENERGY": SensorDeviceClass.ENERGY,
    "FREQUENCY": SensorDeviceClass.FREQUENCY,
    "HUMIDITY": SensorDeviceClass.HUMIDITY,
    "POWER": SensorDeviceClass.POWER,
    "POWER_FACTOR": SensorDeviceClass.POWER_FACTOR,
    "TEMPERATURE": SensorDeviceClass.TEMPERATURE,
    "VOLTAGE": SensorDeviceClass.VOLTAGE,
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up LDCS sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    client = runtime["client"]
    coordinator = runtime["coordinator"]
    if runtime.get("product_type") == "usystems_rdhx":
        async_add_entities(
            RdhxSensor(coordinator, client, entry.entry_id, register)
            for register in RDHX_SENSORS
        )
        return

    async def _async_discover_and_add():
        await asyncio.sleep(10)
        if not client.sensor_descriptors:
            await hass.async_add_executor_job(client.discover, "fast")
        async_register_xerus_device_tree(hass, entry, client)
        known_keys = {descriptor.key for descriptor in client.sensor_descriptors}
        entities = [
            RaritanSensor(coordinator, client, entry.entry_id, descriptor)
            for descriptor in client.sensor_descriptors
        ]
        async_add_entities(entities)
        _LOGGER.info("LDCS added %s fast-discovery sensor entities for %s", len(entities), entry.title)
        await asyncio.sleep(10)
        await coordinator.async_request_refresh()
        await asyncio.sleep(60)
        await hass.async_add_executor_job(client.discover, "full")
        async_register_xerus_device_tree(hass, entry, client)
        new_descriptors = [
            descriptor
            for descriptor in client.sensor_descriptors
            if descriptor.key not in known_keys
        ]
        if new_descriptors:
            async_add_entities(
                RaritanSensor(coordinator, client, entry.entry_id, descriptor)
                for descriptor in new_descriptors
            )
            _LOGGER.info("LDCS added %s full-discovery sensor entities for %s", len(new_descriptors), entry.title)
            await coordinator.async_request_refresh()

    entry.async_create_background_task(
        hass,
        _async_discover_and_add(),
        name=f"{DOMAIN}_{entry.entry_id}_sensor_discovery",
    )


class RaritanSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Xerus sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, client, entry_id, descriptor):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._client = client
        self._descriptor = descriptor
        self._attr_unique_id = f"{entry_id}_{descriptor.key}"
        self._attr_translation_key = None
        self._attr_device_info = descriptor.device_info or client.device_info

        if descriptor.kind == SensorKind.NUMERIC:
            self._attr_suggested_display_precision = 2
            self._attr_native_unit_of_measurement = UNIT_MAP.get(descriptor.unit_name)
            self._attr_device_class = _device_class(descriptor)
            self._attr_state_class = SensorStateClass.MEASUREMENT
            if descriptor.type_name == "ENERGY" and self._attr_device_class == SensorDeviceClass.ENERGY:
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        else:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def name(self):
        """Return the latest discovered sensor name."""
        return self._latest_descriptor.name

    @property
    def available(self):
        """Return if entity is available."""
        value = self.coordinator.data.get(self._descriptor.key)
        return value is not None and value.get("available", False)

    @property
    def native_value(self):
        """Return the sensor value."""
        value = self.coordinator.data.get(self._descriptor.key)
        if not value:
            return None
        return value.get("value")

    @property
    def extra_state_attributes(self):
        """Return extra sensor attributes."""
        descriptor = self._latest_descriptor
        value = self.coordinator.data.get(self._descriptor.key) or {}
        attrs = {
            "raritan_target": descriptor.target,
            "raritan_context": descriptor.context,
            "raritan_type": descriptor.type_name,
            "raritan_unit": descriptor.unit_name,
            "raritan_kind": descriptor.kind.value,
        }
        attrs.update(descriptor.attributes or {})
        attrs.update(value.get("attributes", {}))
        return attrs

    @property
    def _latest_descriptor(self):
        """Return refreshed metadata while preserving the stable entity key."""
        return self._client.descriptor_for_key(self._descriptor.key) or self._descriptor


def _device_class(descriptor):
    """Return a Home Assistant device class compatible with the native unit."""
    if descriptor.unit_name == "VOLT_AMP":
        return getattr(SensorDeviceClass, "APPARENT_POWER", None)
    if descriptor.unit_name == "VOLT_AMP_REACTIVE":
        return getattr(SensorDeviceClass, "REACTIVE_POWER", None)
    if descriptor.unit_name in {"VOLT_AMP_HOUR", "VOLT_AMP_REACTIVE_HOUR"}:
        return None
    return DEVICE_CLASS_MAP.get(descriptor.type_name)


class RdhxSensor(CoordinatorEntity, SensorEntity):
    """Representation of a USystems RDHx Modbus sensor."""

    _attr_has_entity_name = True
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, client, entry_id, register):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._register = register
        self._attr_unique_id = f"{entry_id}_{register.key}"
        self._attr_name = register.name
        self._attr_device_info = client.device_info
        self._attr_native_unit_of_measurement = UNIT_MAP.get(register.unit, register.unit)
        self._attr_device_class = _sensor_device_class(register.device_class)
        self._attr_state_class = _sensor_state_class(register.state_class)

    @property
    def available(self):
        """Return whether the sensor is available."""
        value = self.coordinator.data.get(self._register.key)
        return value is not None and value.get("available", False)

    @property
    def native_value(self):
        """Return the sensor value."""
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
            "modbus_register_type": self._register.register_type,
            "modbus_data_type": self._register.data_type,
        }


def _sensor_device_class(value):
    if value == "temperature":
        return SensorDeviceClass.TEMPERATURE
    return None


def _sensor_state_class(value):
    if value == "measurement":
        return SensorStateClass.MEASUREMENT
    if value == "total_increasing":
        return SensorStateClass.TOTAL_INCREASING
    return None
