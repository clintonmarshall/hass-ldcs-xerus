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
    frontend_features = await _async_frontend_features(hass)
    config = _build_dashboard_config(rack_name, entity_ids, frontend_features)

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


async def _async_frontend_features(hass: HomeAssistant) -> dict[str, bool]:
    """Return optional frontend resources currently registered in Home Assistant."""
    resources = await Store(
        hass,
        DASHBOARD_STORAGE_VERSION,
        RESOURCES_STORAGE_KEY,
        minor_version=DASHBOARD_STORAGE_MINOR_VERSION,
    ).async_load()
    urls = []
    if isinstance(resources, dict):
        urls = [str(item.get("url", "")).lower() for item in resources.get("items", [])]
    return {
        "bubble_card": any("bubble-card" in url for url in urls),
        "gauge_card_pro": any("gauge-card-pro" in url for url in urls),
    }


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


def _build_dashboard_config(
    rack_name: str,
    entities: list[str],
    frontend_features: dict[str, bool] | None = None,
) -> dict:
    """Build the Lovelace config for one rack."""
    frontend_features = frontend_features or {}
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
    active_power_entities = _matching(power_entities, "active_power")
    inlet_power_entities = _matching(active_power_entities, "inlet")
    inlet_current_entities = _matching(power_entities, "inlet", "current")
    inlet_voltage_entities = _matching(power_entities, "inlet", "voltage")
    inlet_frequency_entities = _matching(power_entities, "frequency")
    outlet_power_entities = _matching(outlet_entities, "active_power")
    temperature_entities = _matching(environment_entities, "temperature")
    humidity_entities = _matching(environment_entities, "humidity")
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
                            _heading("Rack Status", "mdi:pulse"),
                            _status_card(
                                _first(event_entities, "alarm"),
                                "Rack alarm beacon",
                                "mdi:alarm-light",
                                frontend_features,
                            ),
                            _status_card(
                                _first(event_entities, "active_breach_count")
                                or _first(event_entities, "breach"),
                                "Active breaches",
                                "mdi:alert-circle",
                                frontend_features,
                            ),
                            _status_card(
                                _first(security_entities, "security"),
                                "Rack security",
                                "mdi:shield-lock",
                                frontend_features,
                            ),
                            _status_card(
                                _first(entities, "xerus_modbus_tcp_layout"),
                                "Modbus layout",
                                "mdi:transit-connection-variant",
                                frontend_features,
                            ),
                        ]
                    ),
                    _section(
                        [
                            _heading("Rack Load", "mdi:gauge"),
                            _power_gauge(
                                inlet_power_entities[0] if inlet_power_entities else _first(active_power_entities),
                                "Inlet power",
                                frontend_features,
                                maximum=10000,
                            ),
                            _power_gauge(
                                inlet_current_entities[0] if inlet_current_entities else _first(power_entities, "current"),
                                "Inlet current",
                                frontend_features,
                                maximum=32,
                            ),
                            _power_gauge(
                                inlet_voltage_entities[0] if inlet_voltage_entities else _first(power_entities, "voltage"),
                                "Voltage",
                                frontend_features,
                                maximum=260,
                                thresholds=(210, 240),
                            ),
                        ],
                    ),
                    _section(
                        [
                            _heading("Quick Drill-Down", "mdi:view-dashboard"),
                            _navigation_card("Power quality", "mdi:sine-wave", "/ldcs-" + _slug(rack_name) + "/power", frontend_features),
                            _navigation_card("Outlets", "mdi:power-socket-au", "/ldcs-" + _slug(rack_name) + "/outlets", frontend_features),
                            _navigation_card("Security & assets", "mdi:shield-lock", "/ldcs-" + _slug(rack_name) + "/security-assets", frontend_features),
                            _entities_card("Active alarms and breaches", event_entities[:8]),
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
                            *_gauge_cards(
                                [
                                    (
                                        inlet_power_entities[0] if inlet_power_entities else _first(active_power_entities),
                                        "Inlet power",
                                        10000,
                                    ),
                                    (
                                        inlet_current_entities[0] if inlet_current_entities else _first(power_entities, "current"),
                                        "Inlet current",
                                        32,
                                    ),
                                    (
                                        inlet_voltage_entities[0] if inlet_voltage_entities else _first(power_entities, "voltage"),
                                        "Voltage",
                                        260,
                                    ),
                                ],
                                frontend_features,
                            ),
                            _history(
                                "Power history",
                                active_power_entities[:8],
                            ),
                        ],
                        2,
                    ),
                    _section(
                        [
                            _heading("Phase Balance", "mdi:sine-wave"),
                            *_gauge_cards(
                                [
                                    (entity_id, f"Line {index + 1} current", 32)
                                    for index, entity_id in enumerate(inlet_current_entities[:3])
                                ],
                                frontend_features,
                            ),
                            _entities_card(
                                "Voltage/current/frequency",
                                (inlet_voltage_entities + inlet_current_entities + inlet_frequency_entities)[:18],
                            ),
                        ]
                    ),
                    _section(
                        [
                            _heading("Min/Max", "mdi:chart-bell-curve"),
                            _entities_card("Recorded extrema", minmax_entities[:18]),
                            _entities_card("Power quality waveform", waveform_buttons + _matching(power_entities, "waveform")[:8]),
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
                "sections": _outlet_sections(outlet_entities, frontend_features),
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
                            *_gauge_cards(
                                [(entity_id, f"Temp {index + 1}", 60) for index, entity_id in enumerate(temperature_entities[:4])],
                                frontend_features,
                            ),
                            _history(
                                "Temperature history",
                                temperature_entities[:8],
                            ),
                        ]
                    ),
                    _section(
                        [
                            _heading("Air & Humidity", "mdi:water-percent"),
                            *_gauge_cards(
                                [(entity_id, f"Humidity {index + 1}", 100) for index, entity_id in enumerate(humidity_entities[:4])],
                                frontend_features,
                            ),
                            _entities_card("Environment detail", environment_entities[:18]),
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
                            _status_card(_first(security_entities, "front", "door"), "Front door", "mdi:door-open", frontend_features),
                            _status_card(_first(security_entities, "rear", "door"), "Rear door", "mdi:door-open", frontend_features),
                            _status_card(_first(security_entities, "lock"), "Smart lock", "mdi:lock-smart", frontend_features),
                            _entities_card("Security detail", security_entities[:18]),
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
                            _status_card(_first(event_entities, "alarm"), "Rack alarm beacon", "mdi:alarm-light", frontend_features),
                            _status_card(_first(event_entities, "breach"), "Threshold breach", "mdi:alert-circle", frontend_features),
                            _entities_card("Alarms and thresholds", event_entities[:24]),
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


def _outlet_sections(
    outlet_entities: list[str],
    frontend_features: dict[str, bool],
) -> list[dict]:
    """Build outlet sections split into manageable blocks."""
    if not outlet_entities:
        return [
            _section(
                [_heading("Outlets", "mdi:power-strip"), _entities_card("Outlet states", [])]
            )
        ]
    outlet_cards = _outlet_control_cards(outlet_entities, frontend_features)
    outlet_power_entities = _matching(outlet_entities, "active_power")
    outlet_current_entities = _matching(outlet_entities, "current")
    outlet_state_entities = _matching(outlet_entities, "state", "power")
    sections = []
    for index in range(0, min(len(outlet_cards), 48), 12):
        sections.append(
            _section(
                [
                    _heading(
                        f"Outlets {index + 1}-{min(index + 12, len(outlet_cards))}",
                        "mdi:power-strip",
                    ),
                    *outlet_cards[index : index + 12],
                ],
                2 if index == 0 else 1,
            )
        )
    sections.append(
        _section(
            [
                _heading("Outlet Trends", "mdi:chart-line"),
                _history("Outlet power history", outlet_power_entities[:10]),
                _entities_card(
                    "Outlet telemetry drill-down",
                    (outlet_power_entities + outlet_current_entities + outlet_state_entities)[:24],
                ),
            ],
            2,
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


def _gauge_cards(
    specs: list[tuple[str | None, str, int]],
    frontend_features: dict[str, bool],
) -> list[dict]:
    return [
        card
        for card in (
            _power_gauge(entity_id, name, frontend_features, maximum=maximum)
            for entity_id, name, maximum in specs
        )
        if card
    ]


def _power_gauge(
    entity_id: str | None,
    name: str,
    frontend_features: dict[str, bool],
    *,
    minimum: int = 0,
    maximum: int = 100,
    thresholds: tuple[int, int] | None = None,
) -> dict | None:
    if entity_id is None:
        return None
    yellow, red = thresholds or (int(maximum * 0.65), int(maximum * 0.85))
    if frontend_features.get("gauge_card_pro"):
        return {
            "type": "custom:gauge-card-pro",
            "entity": entity_id,
            "min": minimum,
            "max": maximum,
            "needle": True,
            "gradient": True,
            "segments": [
                {"from": minimum, "color": "var(--success-color)"},
                {"from": yellow, "color": "var(--warning-color)"},
                {"from": red, "color": "var(--error-color)"},
            ],
            "titles": {"primary": name},
            "value_texts": {"primary": "{{ state }}"},
        }
    return {
        "type": "gauge",
        "entity": entity_id,
        "name": name,
        "min": minimum,
        "max": maximum,
        "needle": True,
        "segments": [
            {"from": minimum, "color": "var(--success-color)"},
            {"from": yellow, "color": "var(--warning-color)"},
            {"from": red, "color": "var(--error-color)"},
        ],
    }


def _entity_tile(entity_id: str | None, name: str, icon: str) -> dict | None:
    if entity_id is None:
        return None
    return {"type": "tile", "entity": entity_id, "name": name, "icon": icon}


def _status_card(
    entity_id: str | None,
    name: str,
    icon: str,
    frontend_features: dict[str, bool],
    *,
    button_type: str = "state",
) -> dict | None:
    if entity_id is None:
        return None
    if frontend_features.get("bubble_card"):
        return {
            "type": "custom:bubble-card",
            "card_type": "button",
            "button_type": button_type,
            "entity": entity_id,
            "name": name,
            "icon": icon,
            "show_state": True,
            "card_layout": "large",
        }
    return _entity_tile(entity_id, name, icon)


def _navigation_card(
    name: str,
    icon: str,
    navigation_path: str,
    frontend_features: dict[str, bool],
) -> dict:
    if frontend_features.get("bubble_card"):
        return {
            "type": "custom:bubble-card",
            "card_type": "button",
            "button_type": "name",
            "name": name,
            "icon": icon,
            "card_layout": "large",
            "button_action": {
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": navigation_path,
                }
            },
        }
    return {
        "type": "button",
        "name": name,
        "icon": icon,
        "tap_action": {"action": "navigate", "navigation_path": navigation_path},
    }


def _outlet_control_cards(
    outlet_entities: list[str],
    frontend_features: dict[str, bool],
) -> list[dict]:
    outlet_numbers = sorted(
        {
            number
            for entity_id in outlet_entities
            if (number := _outlet_number(entity_id)) is not None
        }
    )
    if not outlet_numbers:
        return [_entities_card("Outlet details", outlet_entities[:24])]

    cards = []
    for number in outlet_numbers[:48]:
        switch_entity = _first(outlet_entities, f"outlet_{number}", "power")
        if switch_entity and not switch_entity.startswith("switch."):
            switch_entity = next(
                (
                    entity_id
                    for entity_id in outlet_entities
                    if entity_id.startswith("switch.")
                    and f"outlet_{number}_" in entity_id.lower()
                ),
                None,
            )
        power_entity = _first(outlet_entities, f"outlet_{number}", "active_power")
        current_entity = _first(outlet_entities, f"outlet_{number}", "current")
        state_entity = _first(outlet_entities, f"outlet_{number}", "state")
        primary_entity = switch_entity or state_entity or power_entity or current_entity
        if primary_entity is None:
            continue
        if frontend_features.get("bubble_card"):
            sub_buttons = [
                {
                    "entity": entity_id,
                    "show_state": True,
                    "show_name": False,
                    "icon": icon,
                }
                for entity_id, icon in (
                    (power_entity, "mdi:flash"),
                    (current_entity, "mdi:current-ac"),
                )
                if entity_id
            ]
            cards.append(
                {
                    "type": "custom:bubble-card",
                    "card_type": "button",
                    "button_type": "switch" if primary_entity.startswith("switch.") else "state",
                    "entity": primary_entity,
                    "name": f"Outlet {number}",
                    "icon": "mdi:power-socket-au",
                    "show_state": True,
                    "card_layout": "large",
                    "sub_button": sub_buttons,
                }
            )
        else:
            cards.append(_entity_tile(primary_entity, f"Outlet {number}", "mdi:power-socket-au"))
    return [card for card in cards if card]


def _outlet_number(entity_id: str) -> int | None:
    match = re.search(r"outlet[_-](\d+)", entity_id.lower())
    if match is None:
        return None
    return int(match.group(1))


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
