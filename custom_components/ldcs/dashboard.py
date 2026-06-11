"""Lovelace dashboard generation for LDCS rack views."""

from __future__ import annotations

import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import CONF_RACK_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

DASHBOARD_STORAGE_VERSION = 1
DASHBOARD_STORAGE_MINOR_VERSION = 1
DASHBOARDS_STORAGE_KEY = "lovelace_dashboards"
RESOURCES_STORAGE_KEY = "lovelace_resources"
RESOURCE_URL_PREFIX = "/ldcs_static"
LDCS_RESOURCES = (
    ("ldcs_protocol_health_card", f"{RESOURCE_URL_PREFIX}/ldcs-protocol-health-card.js"),
    ("ldcs_raritan_rack_visual_card", f"{RESOURCE_URL_PREFIX}/raritan-rack-visual-card.js"),
    ("ldcs_raritan_cooling_card", f"{RESOURCE_URL_PREFIX}/raritan-cooling-card.js"),
    ("ldcs_raritan_waveform_card", f"{RESOURCE_URL_PREFIX}/raritan-waveform-card.js"),
    ("ldcs_raritan_outlet_load_card", f"{RESOURCE_URL_PREFIX}/raritan-outlet-load-card.js"),
)


async def async_install_rack_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Create or update the storage-mode Lovelace dashboard for an LDCS rack."""
    rack_name = entry.data.get(CONF_RACK_NAME) or entry.options.get(CONF_RACK_NAME) or "LDCS Rack"
    url_path = f"ldcs-{_slug(rack_name)}"
    dashboard_id = url_path.replace("-", "_")
    entity_ids = _ldcs_entity_ids_for_rack(hass, rack_name)
    config = _build_dashboard_config(rack_name, entity_ids)

    await _async_install_resources(hass)
    await Store(
        hass,
        DASHBOARD_STORAGE_VERSION,
        f"lovelace.{dashboard_id}",
        minor_version=DASHBOARD_STORAGE_MINOR_VERSION,
    ).async_save({"config": config})

    dashboards = await Store(
        hass,
        DASHBOARD_STORAGE_VERSION,
        DASHBOARDS_STORAGE_KEY,
        minor_version=DASHBOARD_STORAGE_MINOR_VERSION,
    ).async_load()
    if not isinstance(dashboards, dict):
        dashboards = {"items": []}
    items = dashboards.setdefault("items", [])
    item = next(
        (
            current
            for current in items
            if current.get("id") == dashboard_id or current.get("url_path") == url_path
        ),
        None,
    )
    registry_item = {
        "id": dashboard_id,
        "icon": "mdi:server-rack",
        "title": rack_name,
        "url_path": url_path,
        "require_admin": False,
        "mode": "storage",
        "show_in_sidebar": True,
    }
    if item is None:
        items.append(registry_item)
    else:
        item.update(registry_item)
    await Store(
        hass,
        DASHBOARD_STORAGE_VERSION,
        DASHBOARDS_STORAGE_KEY,
        minor_version=DASHBOARD_STORAGE_MINOR_VERSION,
    ).async_save(dashboards)

    _LOGGER.info(
        "Installed LDCS rack dashboard %s with %s entities",
        url_path,
        len(entity_ids),
    )
    return url_path


async def _async_install_resources(hass: HomeAssistant) -> None:
    """Register LDCS visual cards as Lovelace module resources."""
    resources = await Store(
        hass,
        DASHBOARD_STORAGE_VERSION,
        RESOURCES_STORAGE_KEY,
        minor_version=DASHBOARD_STORAGE_MINOR_VERSION,
    ).async_load()
    if not isinstance(resources, dict):
        resources = {"items": []}
    items = resources.setdefault("items", [])

    changed = False
    for resource_id, url in LDCS_RESOURCES:
        item = next(
            (
                current
                for current in items
                if current.get("id") == resource_id or current.get("url") == url
            ),
            None,
        )
        resource_item = {"id": resource_id, "res_type": "module", "url": url}
        if item is None:
            items.append(resource_item)
            changed = True
        elif any(item.get(key) != value for key, value in resource_item.items()):
            item.update(resource_item)
            changed = True

    if changed:
        await Store(
            hass,
            DASHBOARD_STORAGE_VERSION,
            RESOURCES_STORAGE_KEY,
            minor_version=DASHBOARD_STORAGE_MINOR_VERSION,
        ).async_save(resources)


def _ldcs_entity_ids(hass: HomeAssistant) -> list[str]:
    """Return enabled entity IDs owned by this integration."""
    return _entity_ids_for_config_entries(hass, None)


def _ldcs_entity_ids_for_rack(hass: HomeAssistant, rack_name: str) -> list[str]:
    """Return enabled entity IDs owned by LDCS config entries in one rack."""
    rack_entry_ids = {
        entry.entry_id
        for entry in hass.config_entries.async_entries(DOMAIN)
        if (entry.data.get(CONF_RACK_NAME) or entry.options.get(CONF_RACK_NAME)) == rack_name
    }
    return _entity_ids_for_config_entries(hass, rack_entry_ids)


def _entity_ids_for_config_entries(
    hass: HomeAssistant,
    config_entry_ids: set[str] | None,
) -> list[str]:
    """Return enabled LDCS entity IDs for all entries or a selected entry set."""
    registry = er.async_get(hass)
    entities = []
    for item in registry.entities.values():
        if item.platform != DOMAIN or item.disabled_by is not None:
            continue
        if config_entry_ids is not None and item.config_entry_id not in config_entry_ids:
            continue
        entities.append(item.entity_id)
    return sorted(entities, key=_natural_sort_key)


def _build_dashboard_config(rack_name: str, entities: list[str]) -> dict:
    """Build the Lovelace config for one rack."""
    power_entities = _matching(
        entities,
        "active_power",
        "apparent_power",
        "current",
        "voltage",
        "energy",
        "frequency",
        "power_factor",
        "inlet",
        "ocp",
        "breaker",
        "waveform",
    )
    outlet_entities = _matching(entities, "_outlet_", "outlet_")
    environment_entities = _matching(
        entities,
        "temperature",
        "humidity",
        "air_",
        "water_",
        "fan_",
        "valve",
        "cooling",
        "rdhx",
    )
    security_entities = _matching(entities, "door", "lock", "handle", "security", "access")
    asset_entities = _matching(entities, "asset", "tag", "rack_unit")
    event_entities = _matching(
        entities,
        "alarm",
        "breach",
        "warning",
        "critical",
        "event",
        "threshold",
        "dry_contact",
        "contact",
    )
    waveform_buttons = _matching(entities, "capture_power_quality_waveform")
    telemetry_samples = _matching(
        power_entities + environment_entities,
        "active_power",
        "current",
        "voltage",
        "temperature",
        "humidity",
    )[:12]
    protocol_health = {
        "type": "custom:ldcs-protocol-health-card",
        "title": f"{rack_name} protocol health",
        "entities": {
            "telemetrySamples": telemetry_samples,
            "redfishOutlet": _first(outlet_entities, "redfish") or _first(outlet_entities, "outlet_state"),
            "modbusLayout": _first(entities, "xerus_modbus_tcp_layout"),
            "mqttTopic": "raritan/#",
        },
    }
    minmax_entities = _matching(
        entities,
        "minimum",
        "maximum",
        "min_",
        "max_",
        "reset_sensor_minimum_maximum_values",
    )

    visual = {
        "type": "custom:raritan-rack-visual-card",
        "title": f"{rack_name} live containment",
        "entities": {
            "frontDoor": _first(security_entities, "front", "door"),
            "rearDoor": _first(security_entities, "rear", "door")
            or _first(security_entities, "door_state_2"),
            "frontLock": _first(security_entities, "lock", "1")
            or _first(security_entities, "front", "lock"),
            "rearLock": _first(security_entities, "lock", "2")
            or _first(security_entities, "rear", "lock"),
            "alarmA": _first(event_entities, "alarm"),
            "alarmB": _first(event_entities, "critical") or _first(event_entities, "warning"),
            "securityStatus": _first(security_entities, "security_status"),
            "assetInventories": asset_entities[:4],
        },
    }

    cooling_visual = {
        "type": "custom:raritan-cooling-card",
        "title": f"{rack_name} cooling airflow",
        "entities": {
            "unitOn": _first(environment_entities, "unit_on"),
            "globalAlarm": _first(event_entities, "global_alarm"),
            "leakAlarm": _first(event_entities, "leak"),
            "airOff": _first(environment_entities, "air_off"),
            "airOn": _first(environment_entities, "air_on"),
            "roomTemp": _first(environment_entities, "room_temperature")
            or _first(environment_entities, "temperature"),
            "fanFeedback": _first(environment_entities, "fan"),
            "valveFeedback": _first(environment_entities, "valve"),
            "rackFrontA": _first(environment_entities, "front", "temperature"),
            "rackRearA": _first(environment_entities, "rear", "temperature"),
            "rackFrontB": _nth(environment_entities, 1, "temperature"),
            "rackRearB": _nth(environment_entities, 2, "temperature"),
        },
    }

    return {
        "title": rack_name,
        "views": [
            {
                "title": "Rack Overview",
                "path": "overview",
                "icon": "mdi:server-rack",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    _section([_heading("Operations Health", "mdi:server-network"), protocol_health], 3),
                    _section([_heading("Rack Visual", "mdi:server-rack"), visual], 2),
                    _section(
                        [
                            _heading("Live Status", "mdi:pulse"),
                            _entity_tile(
                                _first(event_entities, "alarm"),
                                "Rack alarm beacon",
                                "mdi:alarm-light",
                            ),
                            _entity_tile(
                                _first(security_entities, "security"),
                                "Rack security",
                                "mdi:shield-lock",
                            ),
                            _gauge(_first(power_entities, "active_power"), "Rack power"),
                            _entities_card("Active alarms and breaches", event_entities[:12]),
                        ]
                    ),
                    _section(
                        [
                            _heading("Rack Inventory", "mdi:tag-multiple"),
                            _entities_card("Asset strips and tags", asset_entities[:16]),
                            _entities_card("External sensors", environment_entities[:16]),
                        ]
                    ),
                ],
            },
            {
                "title": "Power",
                "path": "power",
                "icon": "mdi:flash",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    _section(
                        [
                            _heading("Inlet Load", "mdi:transmission-tower"),
                            _history(
                                "Power history",
                                _matching(power_entities, "active_power")[:8],
                            ),
                        ],
                        2,
                    ),
                    _section(
                        [
                            _heading("Phase Balance", "mdi:sine-wave"),
                            _entities_card("Voltage/current/frequency", power_entities[:24]),
                        ]
                    ),
                    _section(
                        [
                            _heading("Min/Max", "mdi:chart-bell-curve"),
                            _entities_card("Recorded extrema", minmax_entities[:24]),
                        ]
                    ),
                ],
            },
            {
                "title": "Outlets",
                "path": "outlets",
                "icon": "mdi:power-socket-au",
                "type": "sections",
                "max_columns": 4,
                "sections": _outlet_sections(outlet_entities),
            },
            {
                "title": "Environment",
                "path": "environment",
                "icon": "mdi:thermometer-water",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    _section([_heading("Cooling Visual", "mdi:fan"), cooling_visual], 2),
                    _section(
                        [
                            _heading("Temperature", "mdi:thermometer"),
                            _history(
                                "Temperature history",
                                _matching(environment_entities, "temperature")[:8],
                            ),
                        ]
                    ),
                    _section(
                        [
                            _heading("Environmental Sensors", "mdi:leak"),
                            _entities_card("Environment", environment_entities[:30]),
                        ]
                    ),
                ],
            },
            {
                "title": "Security & Assets",
                "path": "security-assets",
                "icon": "mdi:shield-lock",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    _section([_heading("Rack Visual", "mdi:server-security"), visual], 2),
                    _section(
                        [
                            _heading("Doors & Locks", "mdi:door"),
                            _entities_card("Security", security_entities[:30]),
                        ]
                    ),
                    _section(
                        [
                            _heading("Asset Strip", "mdi:tag-multiple"),
                            _entities_card("Assets", asset_entities[:30]),
                        ]
                    ),
                ],
            },
            {
                "title": "Events",
                "path": "events",
                "icon": "mdi:alarm-light",
                "type": "sections",
                "max_columns": 3,
                "sections": [
                    _section(
                        [
                            _heading("Alarm Summary", "mdi:alarm-light"),
                            _entities_card("Alarms and thresholds", event_entities[:30]),
                        ]
                    ),
                    _section(
                        [
                            _heading("Dry Contacts", "mdi:electric-switch-closed"),
                            _entities_card(
                                "Contacts",
                                _matching(event_entities, "contact")[:24],
                            ),
                        ]
                    ),
                    _section(
                        [
                            _heading("Power Quality", "mdi:sine-wave"),
                            _entities_card(
                                "Waveform capture",
                                waveform_buttons
                                + _matching(power_entities, "waveform")[:12],
                            ),
                        ]
                    ),
                ],
            },
        ],
    }


def _outlet_sections(outlet_entities: list[str]) -> list[dict]:
    """Build outlet sections split into manageable blocks."""
    if not outlet_entities:
        return [
            _section(
                [_heading("Outlets", "mdi:power-strip"), _entities_card("Outlet states", [])]
            )
        ]
    sections = []
    for index in range(0, min(len(outlet_entities), 96), 24):
        sections.append(
            _section(
                [
                    _heading(
                        f"Outlets {index + 1}-{min(index + 24, len(outlet_entities))}",
                        "mdi:power-strip",
                    ),
                    _entities_card("Outlet details", outlet_entities[index : index + 24]),
                ],
                2 if index == 0 else 1,
            )
        )
    return sections


def _heading(text: str, icon: str) -> dict:
    return {"type": "heading", "heading": text, "heading_style": "title", "icon": icon}


def _section(cards: list[dict | None], column_span: int = 1) -> dict:
    return {"type": "grid", "column_span": column_span, "cards": [card for card in cards if card]}


def _entities_card(title: str, entity_ids: list[str]) -> dict | None:
    if not entity_ids:
        return {
            "type": "markdown",
            "content": f"### {title}\nNo matching LDCS entities have been discovered yet.",
        }
    return {"type": "entities", "title": title, "show_header_toggle": False, "entities": entity_ids}


def _history(title: str, entity_ids: list[str]) -> dict | None:
    if not entity_ids:
        return _entities_card(title, [])
    return {"type": "history-graph", "title": title, "hours_to_show": 24, "entities": entity_ids}


def _gauge(entity_id: str | None, name: str) -> dict | None:
    if entity_id is None:
        return None
    return {
        "type": "gauge",
        "entity": entity_id,
        "name": name,
        "needle": True,
        "severity": {"green": 0, "yellow": 60, "red": 85},
    }


def _entity_tile(entity_id: str | None, name: str, icon: str) -> dict | None:
    if entity_id is None:
        return None
    return {"type": "tile", "entity": entity_id, "name": name, "icon": icon}


def _matching(entities: list[str], *needles: str) -> list[str]:
    values = []
    for entity_id in entities:
        lowered = entity_id.lower()
        if any(needle in lowered for needle in needles):
            values.append(entity_id)
    return sorted(set(values), key=_natural_sort_key)


def _first(entities: list[str], *needles: str) -> str | None:
    for entity_id in entities:
        lowered = entity_id.lower()
        if all(needle in lowered for needle in needles):
            return entity_id
    return None


def _nth(entities: list[str], index: int, *needles: str) -> str | None:
    matches = [
        entity_id
        for entity_id in entities
        if all(needle in entity_id.lower() for needle in needles)
    ]
    return matches[index] if len(matches) > index else None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "rack"


def _natural_sort_key(value: str) -> list[tuple[int, int | str]]:
    parts: list[tuple[int, int | str]] = []
    current = ""
    for char in value:
        if char.isdigit():
            current += char
        else:
            if current:
                parts.append((1, int(current)))
                current = ""
            parts.append((0, char))
    if current:
        parts.append((1, int(current)))
    return parts
