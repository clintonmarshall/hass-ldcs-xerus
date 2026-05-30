"""Buttons for Legrand Data Center Solutions operations."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up operational buttons."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    client = runtime["client"]
    coordinator = runtime["coordinator"]

    entities = [RaritanResetExtremaButton(coordinator, client, entry.entry_id)]
    entities.extend(
        RaritanWaveformCaptureButton(coordinator, client, entry.entry_id, line_name)
        for line_name in (None, "L1", "L2", "L3")
    )
    async_add_entities(entities)


class RaritanWaveformCaptureButton(CoordinatorEntity, ButtonEntity):
    """Acquire a fresh inlet waveform from Xerus."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:sine-wave"

    def __init__(self, coordinator, client, entry_id, line_name):
        """Initialize a waveform acquisition button."""
        super().__init__(coordinator)
        self._client = client
        self._line_name = line_name
        line_slug = f"_{line_name.lower()}" if line_name else ""
        line_label = f" {line_name}" if line_name else ""
        self._attr_unique_id = f"{entry_id}_inlet_1{line_slug}_capture_power_quality_waveform"
        self._attr_name = f"Inlet 1{line_label} Capture Power Quality Waveform"
        self._attr_device_info = client.device_info

    async def async_press(self):
        """Acquire a new waveform and refresh its sensor."""
        method = (
            self._client.capture_inlet_waveform
            if self._line_name is None
            else self._client.capture_inlet_pole_waveform
        )
        args = () if self._line_name is None else (self._line_name,)
        await self.hass.async_add_executor_job(
            method,
            *args,
        )
        await self.coordinator.async_request_refresh()


class RaritanResetExtremaButton(CoordinatorEntity, ButtonEntity):
    """Reset all PDU-maintained numeric sensor extrema."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:restore-alert"

    def __init__(self, coordinator, client, entry_id):
        """Initialize a min/max reset button."""
        super().__init__(coordinator)
        self._client = client
        self._attr_unique_id = f"{entry_id}_reset_sensor_minimum_maximum_values"
        self._attr_name = "Reset Sensor Minimum and Maximum Values"
        self._attr_device_info = client.device_info

    async def async_press(self):
        """Reset extrema and refresh coordinator data."""
        await self.hass.async_add_executor_job(self._client.reset_all_minmax)
        await self.coordinator.async_request_refresh()
