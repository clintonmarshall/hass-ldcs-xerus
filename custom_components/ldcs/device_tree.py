"""Home Assistant device tree helpers for LDCS devices."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr


@callback
def async_register_xerus_device_tree(hass: HomeAssistant, entry: ConfigEntry, client) -> None:
    """Create/update rack, primary PDU, and linked PDU devices after discovery."""
    device_registry = dr.async_get(hass)
    device_infos = []
    if client.rack_name or getattr(client, "_link_statuses", None):
        device_infos.append(client.rack_device_info)
    device_infos.append(client.device_info)
    device_infos.extend(
        descriptor.device_info
        for descriptor in client.sensor_descriptors
        if descriptor.device_info is not None
    )

    seen = set()
    for device_info in device_infos:
        identifiers = device_info.get("identifiers")
        if not identifiers:
            continue
        identifier_key = tuple(sorted(identifiers))
        if identifier_key in seen:
            continue
        seen.add(identifier_key)
        kwargs = {
            "config_entry_id": entry.entry_id,
            "identifiers": identifiers,
        }
        for key in (
            "configuration_url",
            "manufacturer",
            "model",
            "name",
            "sw_version",
            "via_device",
        ):
            value = device_info.get(key)
            if value is not None:
                kwargs[key] = value
        device_registry.async_get_or_create(**kwargs)
