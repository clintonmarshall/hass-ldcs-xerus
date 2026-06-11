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
LDCS_FRONTEND_VERSION = "0.6.57"
USE_OPTIONAL_HACS_CARDS = False
HISTORY_HOURS_TO_SHOW = 8
LDCS_RESOURCES = (
    ("ldcs_protocol_health_card", f"{RESOURCE_URL_PREFIX}/ldcs-protocol-health-card.js?v={LDCS_FRONTEND_VERSION}"),
    ("ldcs_pdu_config_card", f"{RESOURCE_URL_PREFIX}/ldcs-pdu-config-card.js?v={LDCS_FRONTEND_VERSION}"),
    ("ldcs_rack_status_card", f"{RESOURCE_URL_PREFIX}/ldcs-rack-status-card.js?v={LDCS_FRONTEND_VERSION}"),
    ("ldcs_raritan_rack_visual_card", f"{RESOURCE_URL_PREFIX}/raritan-rack-visual-card.js?v={LDCS_FRONTEND_VERSION}"),
    ("ldcs_raritan_cooling_card", f"{RESOURCE_URL_PREFIX}/raritan-cooling-card.js?v={LDCS_FRONTEND_VERSION}"),
    ("ldcs_raritan_waveform_card", f"{RESOURCE_URL_PREFIX}/raritan-waveform-card.js?v={LDCS_FRONTEND_VERSION}"),
    ("ldcs_raritan_outlet_load_card", f"{RESOURCE_URL_PREFIX}/raritan-outlet-load-card.js?v={LDCS_FRONTEND_VERSION}"),
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
    if not USE_OPTIONAL_HACS_CARDS:
        return {
            "bubble_card": False,
            "expander_card": False,
            "gauge_card_pro": False,
            "mushroom": False,
        }
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
        # Keep expander disabled until the frontend resource is verified in-browser.
        "expander_card": False,
        "gauge_card_pro": any("gauge-card-pro" in url for url in urls),
        "mushroom": any("lovelace-mushroom" in url or "mushroom.js" in url for url in urls),
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

    changed = _deduplicate_ldcs_resources(items)
    for resource_id, url in LDCS_RESOURCES:
        item = next(
            (
                current
                for current in items
                if current.get("id") == resource_id
                or _resource_url_key(current.get("url")) == _resource_url_key(url)
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


def _deduplicate_ldcs_resources(items: list[dict]) -> bool:
    """Normalize LDCS Lovelace resources to JavaScript module entries."""
    changed = False
    seen = set()
    kept = []
    for item in items:
        url_key = _resource_url_key(item.get("url"))
        if url_key and url_key.startswith(f"{RESOURCE_URL_PREFIX}/"):
            if url_key in seen:
                changed = True
                continue
            seen.add(url_key)
            if item.get("res_type") != "module":
                item["res_type"] = "module"
                changed = True
        kept.append(item)
    if len(kept) != len(items):
        items[:] = kept
    return changed


def _resource_url_key(url: str | None) -> str:
    """Return a stable key for matching resources across cache-buster updates."""
    return str(url or "").split("?", 1)[0]


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
    controllable_entities = _controllable_switch_entities(entities)
    security_control_entities = _matching(controllable_entities, "door", "lock", "handle")
    contact_control_entities = _matching(controllable_entities, "contact", "dry", "sensor")
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
    active_power_entities = _metric_entities(power_entities, "active_power", "reactive_power", "apparent_power")
    inlet_power_entities = _matching(active_power_entities, "inlet")
    inlet_current_entities = _metric_entities(
        _matching_all(power_entities, "sensor.", "inlet"),
        "current",
        "peak_current",
        "current_thd",
        "inrush_current",
        "unbalanced",
    )
    inlet_voltage_entities = _metric_entities(
        _matching_all(power_entities, "sensor.", "inlet"),
        "voltage",
        "voltage_thd",
        "unbalanced",
    )
    inlet_frequency_entities = _matching_all(power_entities, "sensor.", "inlet", "frequency")
    outlet_power_entities = _metric_entities(outlet_entities, "active_power", "reactive_power", "apparent_power")
    outlet_state_entities = _matching(outlet_entities, "outlet_state", "switch.", "power")
    ocp_entities = _matching(entities, "ocp", "breaker")
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
            "serviceStatus": _first(entities, "pdu_service_status"),
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
    config_snapshot_entities = _matching(entities, "pdu_config_snapshot")

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
            "outletStates": outlet_state_entities[:96],
            "ocpStates": ocp_entities[:48],
            "rackPower": inlet_power_entities[:8] or active_power_entities[:8],
        },
    }
    rack_status = {
        "type": "custom:ldcs-rack-status-card",
        "title": f"{rack_name} rack status",
        "entities": {
            "alarms": event_entities[:48],
            "securityStatus": _first(security_entities, "security"),
            "doorStates": _matching(security_entities, "door")[:16],
            "lockStates": _matching(security_entities, "lock", "handle")[:16],
            "ocpStates": ocp_entities[:64],
            "outletStates": outlet_state_entities[:128],
            "rackPower": inlet_power_entities[:8] or active_power_entities[:8],
            "inletCurrent": inlet_current_entities[:12],
            "phaseCurrent": inlet_current_entities[:12],
            "assetInventories": asset_entities[:6],
            "serviceStatus": _first(entities, "pdu_service_status"),
            "controllableStates": controllable_entities[:64],
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
    review_views = _review_concept_views(
        rack_name=rack_name,
        frontend_features=frontend_features,
        visual=visual,
        protocol_health=protocol_health,
        power_entities=power_entities,
        active_power_entities=active_power_entities,
        inlet_power_entities=inlet_power_entities,
        inlet_current_entities=inlet_current_entities,
        inlet_voltage_entities=inlet_voltage_entities,
        outlet_entities=outlet_entities,
        outlet_power_entities=outlet_power_entities,
        all_entities=entities,
        environment_entities=environment_entities,
        security_entities=security_entities,
        asset_entities=asset_entities,
        event_entities=event_entities,
    )

    return {
        "title": rack_name,
        "views": [
            {
                "title": "Rack Overview",
                "path": "overview",
                "icon": "mdi:server-rack",
                "type": "sections",
                "max_columns": 4,
                "sections": [
                    _section(
                        [
                            _heading("Rack Status", "mdi:pulse"),
                            rack_status,
                        ],
                        2,
                    ),
                    _section([_heading("Rack Visual", "mdi:server-rack"), visual], 2),
                    _section(
                        [
                            _heading("Operations Health", "mdi:server-network"),
                            protocol_health,
                            _entities_card("Active alarms and recent events", event_entities[:10]),
                        ],
                        2,
                    ),
                    _section(
                        [
                            _heading("Quick Drill-Down", "mdi:view-dashboard"),
                            _navigation_card("Power quality", "mdi:sine-wave", "/ldcs-" + _slug(rack_name) + "/power", frontend_features),
                            _navigation_card("Outlets", "mdi:power-socket-au", "/ldcs-" + _slug(rack_name) + "/outlets", frontend_features),
                            _navigation_card("Security & assets", "mdi:shield-lock", "/ldcs-" + _slug(rack_name) + "/security-assets", frontend_features),
                            _navigation_card("Events & contacts", "mdi:electric-switch", "/ldcs-" + _slug(rack_name) + "/events", frontend_features),
                        ]
                    ),
                ],
            },
            *review_views,
            {
                "title": "Power",
                "path": "power",
                "icon": "mdi:flash",
                "type": "sections",
                "max_columns": 4,
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
                                        inlet_current_entities[0] if inlet_current_entities else _first_sensor(power_entities, "current"),
                                        "Inlet current",
                                        32,
                                    ),
                                    (
                                        inlet_voltage_entities[0] if inlet_voltage_entities else _first_sensor(power_entities, "voltage"),
                                        "Voltage",
                                        260,
                                    ),
                                ],
                                frontend_features,
                            ),
                            _history(
                                "Rack electrical history",
                                _electrical_history_entities(
                                    inlet_power_entities or active_power_entities,
                                    inlet_current_entities,
                                    inlet_voltage_entities,
                                    limit=18,
                                ),
                            ),
                        ],
                        2,
                    ),
                    *_inlet_history_sections(
                        inlet_power_entities or active_power_entities,
                        inlet_current_entities,
                        inlet_voltage_entities,
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
                        ],
                        2,
                    ),
                    _section(
                        [
                            _heading("Power Quality", "mdi:sine-wave"),
                            _entities_card("Power quality waveform", waveform_buttons + _matching(power_entities, "waveform")[:8]),
                        ],
                        2,
                    ),
                ],
            },
            {
                "title": "Outlets",
                "path": "outlets",
                "icon": "mdi:power-socket-au",
                "type": "sections",
                "max_columns": 4,
                "sections": _outlet_sections(outlet_entities, frontend_features, _slug(rack_name)),
            },
            {
                "title": "Outlet History",
                "path": "outlet-history",
                "icon": "mdi:chart-line",
                "type": "sections",
                "max_columns": 4,
                "sections": _outlet_history_sections(outlet_entities),
            },
            {
                "title": "Environment",
                "path": "environment",
                "icon": "mdi:thermometer-water",
                "type": "sections",
                "max_columns": 4,
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
                            _history(
                                "Humidity and airflow history",
                                (humidity_entities + environment_entities)[:8],
                            ),
                        ],
                        2,
                    ),
                ],
            },
            {
                "title": "Security & Assets",
                "path": "security-assets",
                "icon": "mdi:shield-lock",
                "type": "sections",
                "max_columns": 4,
                "sections": [
                    _section([_heading("Rack Visual", "mdi:server-security"), visual], 2),
                    _section(
                        [
                            _heading("Doors & Locks", "mdi:door"),
                            _status_card(_first(security_entities, "front", "door"), "Front door", "mdi:door-open", frontend_features),
                            _status_card(_first(security_entities, "rear", "door"), "Rear door", "mdi:door-open", frontend_features),
                            _status_card(_first(security_entities, "lock"), "Smart lock", "mdi:lock-smart", frontend_features),
                            _entities_card("Controllable rack handles and locks", security_control_entities[:18]),
                            _entities_card("Security detail", security_entities[:18]),
                        ]
                    ),
                    _section(
                        [
                            _heading("Asset Strip", "mdi:tag-multiple"),
                            _entities_card("Assets", asset_entities[:30]),
                        ],
                        2,
                    ),
                ],
            },
            {
                "title": "Events",
                "path": "events",
                "icon": "mdi:alarm-light",
                "type": "sections",
                "max_columns": 4,
                "sections": [
                    _section(
                        [
                            _heading("Alarm Summary", "mdi:alarm-light"),
                            _status_card(_first(event_entities, "alarm"), "Rack alarm beacon", "mdi:alarm-light", frontend_features),
                            _status_card(_first(event_entities, "breach"), "Threshold breach", "mdi:alert-circle", frontend_features),
                            _entities_card("Alarms and thresholds", event_entities[:24]),
                        ],
                        2,
                    ),
                    _section(
                        [
                            _heading("Dry Contacts", "mdi:electric-switch-closed"),
                            _entities_card(
                                "Contacts",
                                contact_control_entities[:24] + _matching(event_entities, "contact")[:24],
                            ),
                        ],
                        2,
                    ),
                    _section(
                        [
                            _heading("Power Quality", "mdi:sine-wave"),
                            _entities_card(
                                "Waveform capture",
                                waveform_buttons
                                + _matching(power_entities, "waveform")[:12],
                            ),
                        ],
                        2,
                    ),
                ],
            },
            {
                "title": "PDU Config",
                "path": "pdu-config",
                "icon": "mdi:cog-transfer",
                "type": "sections",
                "max_columns": 4,
                "sections": [
                    _section(
                        [
                            _heading("Configuration Snapshot", "mdi:cog-transfer"),
                            _pdu_config_card(
                                f"{rack_name} PDU configuration",
                                config_snapshot_entities,
                            ),
                        ],
                        4,
                    ),
                    _section(
                        [
                            _heading("Protocol Health", "mdi:server-network"),
                            protocol_health,
                        ],
                        4,
                    ),
                    _section(
                        [
                            _heading("Config Entities", "mdi:database-cog"),
                            _entities_card(
                                "Snapshot sources",
                                config_snapshot_entities
                                + _matching(entities, "pdu_service_status", "rack_security_status")[:12],
                            ),
                        ],
                        2,
                    ),
                ],
            },
        ],
    }


def _review_concept_views(
    *,
    rack_name: str,
    frontend_features: dict[str, bool],
    visual: dict,
    protocol_health: dict,
    power_entities: list[str],
    active_power_entities: list[str],
    inlet_power_entities: list[str],
    inlet_current_entities: list[str],
    inlet_voltage_entities: list[str],
    outlet_entities: list[str],
    outlet_power_entities: list[str],
    all_entities: list[str],
    environment_entities: list[str],
    security_entities: list[str],
    asset_entities: list[str],
    event_entities: list[str],
) -> list[dict]:
    """Build optional dashboard concept tabs for visual review."""
    pdu_a_power = _matching(outlet_power_entities, "pdu_a")
    pdu_b_power = _matching(outlet_power_entities, "pdu_b")
    pdu_a_outlets = _matching(outlet_entities, "pdu_a")
    pdu_b_outlets = _matching(outlet_entities, "pdu_b")
    if not pdu_a_power and outlet_power_entities:
        split = max(1, len(outlet_power_entities) // 2)
        pdu_a_power = outlet_power_entities[:split]
        pdu_b_power = outlet_power_entities[split:]
    if not pdu_a_outlets and outlet_entities:
        split = max(1, len(outlet_entities) // 2)
        pdu_a_outlets = outlet_entities[:split]
        pdu_b_outlets = outlet_entities[split:]

    alarm_status = _first(event_entities, "alarm")
    active_breaches = _first(event_entities, "active_breach_count") or _first(event_entities, "breach")
    warning_count = _first(event_entities, "warning")
    critical_count = _first(event_entities, "critical")
    service_status = _first(all_entities, "pdu_service_status")
    dashboard_slug = _slug(rack_name)

    return [
        {
            "title": "Review Command Wall",
            "path": "review-command-wall",
            "icon": "mdi:view-dashboard-variant",
            "type": "sections",
            "max_columns": 4,
            "sections": [
                _section([_heading("Containment", "mdi:server-rack"), visual], 2),
                _section(
                    [
                        _heading("Live Status", "mdi:pulse"),
                        _status_card(alarm_status, "Rack alarm beacon", "mdi:alarm-light", frontend_features),
                        _status_card(active_breaches, "Active breaches", "mdi:alert-circle", frontend_features),
                        _status_card(_first(security_entities, "security"), "Rack security", "mdi:shield-lock", frontend_features),
                        _status_card(service_status, "PDU services", "mdi:server-network", frontend_features),
                        *_gauge_cards(
                            [
                                (inlet_power_entities[0] if inlet_power_entities else _first(active_power_entities), "Rack W", 12000),
                                (inlet_current_entities[0] if inlet_current_entities else _first_sensor(power_entities, "current"), "Rack A", 64),
                            ],
                            frontend_features,
                        ),
                    ]
                ),
                _section(
                    [
                        _heading("Trends", "mdi:chart-line"),
                        _history(
                            "Rack inlet W/A/V",
                            _electrical_history_entities(
                                inlet_power_entities or active_power_entities,
                                inlet_current_entities,
                                inlet_voltage_entities,
                                limit=18,
                            ),
                        ),
                    ],
                    2,
                ),
            ],
        },
        {
            "title": "Review Outlet Ops",
            "path": "review-outlet-ops",
            "icon": "mdi:power-socket-au",
            "type": "sections",
            "max_columns": 4,
            "sections": [
                _section(
                    [
                        _heading("PDU A Loads", "mdi:power-strip"),
                        _outlet_load_card("PDU A outlet load", pdu_a_power[:12]),
                        *_outlet_control_cards(pdu_a_outlets, frontend_features, dashboard_slug)[:9],
                    ],
                    2,
                ),
                _section(
                    [
                        _heading("PDU B Loads", "mdi:power-strip"),
                        _outlet_load_card("PDU B outlet load", pdu_b_power[:12]),
                        *_outlet_control_cards(pdu_b_outlets, frontend_features, dashboard_slug)[:9],
                    ],
                    2,
                ),
                _section(
                    [
                        _heading("Combined History", "mdi:chart-areaspline"),
                        _history(
                            "Outlet W/A/V summary",
                            _electrical_history_entities(
                                outlet_power_entities,
                                _metric_entities(outlet_entities, "current", "peak_current", "current_thd", "inrush_current"),
                                _metric_entities(outlet_entities, "voltage", "voltage_thd"),
                                limit=24,
                            ),
                        ),
                    ],
                    4,
                ),
            ],
        },
        {
            "title": "Review Alarms & Access",
            "path": "review-alarms-access",
            "icon": "mdi:alarm-light-outline",
            "type": "sections",
            "max_columns": 4,
            "sections": [
                _section([_heading("Rack Security Visual", "mdi:shield-home"), visual], 2),
                _section(
                    [
                        _heading("Alarm Stack", "mdi:alarm-light"),
                        _status_card(alarm_status, "Alarm status", "mdi:alarm-light", frontend_features),
                        _status_card(warning_count, "Warnings", "mdi:alert", frontend_features),
                        _status_card(critical_count, "Critical", "mdi:alert-octagon", frontend_features),
                        _entities_card("Threshold and event detail", event_entities[:24]),
                    ]
                ),
                _section(
                    [
                        _heading("Access & Assets", "mdi:badge-account-horizontal"),
                        _status_card(_first(security_entities, "front", "door"), "Front door", "mdi:door-open", frontend_features),
                        _status_card(_first(security_entities, "rear", "door"), "Rear door", "mdi:door-open", frontend_features),
                        _status_card(_first(security_entities, "lock"), "Handle lock", "mdi:lock-smart", frontend_features),
                        _entities_card("Rack security entities", security_entities[:18]),
                    ]
                ),
                _section(
                    [
                        _heading("Asset Strip", "mdi:tag-multiple"),
                        _entities_card("Rack occupancy sources", asset_entities[:24]),
                    ],
                    2,
                ),
            ],
        },
    ]


def _outlet_sections(
    outlet_entities: list[str],
    frontend_features: dict[str, bool],
    dashboard_slug: str,
) -> list[dict]:
    """Build outlet sections split into manageable blocks."""
    if not outlet_entities:
        return [
            _section(
                [_heading("Outlets", "mdi:power-strip"), _entities_card("Outlet states", [])]
            )
        ]
    outlet_cards = _outlet_control_cards(outlet_entities, frontend_features, dashboard_slug)
    outlet_power_entities = _matching(outlet_entities, "active_power")
    outlet_current_entities = _metric_entities(outlet_entities, "current", "peak_current", "current_thd", "inrush_current")
    outlet_state_entities = _matching(outlet_entities, "state", "power")
    sections = []
    for index in range(0, min(len(outlet_cards), 48), 6):
        sections.append(
            _section(
                [
                    _heading(
                        f"Outlets {index + 1}-{min(index + 6, len(outlet_cards))}",
                        "mdi:power-strip",
                    ),
                    *outlet_cards[index : index + 6],
                ],
                2,
            )
        )
    sections.append(
        _section(
            [
                _heading("Outlet Trends", "mdi:chart-line"),
                _navigation_card(
                    "Open outlet history",
                    "mdi:chart-line",
                    f"/ldcs-{dashboard_slug}/outlet-history",
                    frontend_features,
                ),
                _entities_card("Outlet states", outlet_state_entities[:12]),
            ],
            2,
        )
    )
    return sections


def _outlet_load_card(title: str, entity_ids: list[str]) -> dict | None:
    if not entity_ids:
        return None
    return {"type": "custom:raritan-outlet-load-card", "title": title, "entities": entity_ids}


def _pdu_config_card(title: str, entity_ids: list[str]) -> dict | None:
    if not entity_ids:
        return _entities_card(title, [])
    return {"type": "custom:ldcs-pdu-config-card", "title": title, "entities": entity_ids}


def _outlet_history_sections(outlet_entities: list[str]) -> list[dict]:
    """Build dedicated outlet history sections."""
    outlet_power_entities = _matching(outlet_entities, "active_power")
    outlet_current_entities = _metric_entities(outlet_entities, "current", "peak_current", "current_thd", "inrush_current")
    outlet_voltage_entities = _metric_entities(outlet_entities, "voltage", "voltage_thd")
    outlet_numbers = sorted(
        {
            number
            for entity_id in outlet_entities
            if (number := _outlet_number(entity_id)) is not None
        }
    )
    sections = [
        _section(
            [
                _heading("Outlet Electrical Summary", "mdi:chart-line"),
                _history(
                    "Outlet W/A/V summary",
                    _electrical_history_entities(
                        outlet_power_entities,
                        outlet_current_entities,
                        outlet_voltage_entities,
                        numbers=outlet_numbers[:8],
                        number_parser=_outlet_number,
                    ),
                ),
            ],
            4,
        ),
    ]
    for number in outlet_numbers[:24]:
        history_entities = [
            entity_id
            for entity_id in (
                _first(outlet_entities, f"outlet_{number}", "active_power"),
                _first(outlet_entities, f"outlet_{number}", "current"),
                _first(outlet_entities, f"outlet_{number}", "voltage"),
            )
            if entity_id
        ]
        if history_entities:
            sections.append(
                _section(
                    [
                        _heading(f"Outlet {number}", "mdi:power-socket-au"),
                        _history(f"Outlet {number}", history_entities),
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
    return {
        "type": "history-graph",
        "title": title,
        "hours_to_show": HISTORY_HOURS_TO_SHOW,
        "entities": [
            {"entity": entity_id, "name": _history_name(entity_id)} for entity_id in entity_ids
        ],
    }


def _inlet_history_sections(
    power_entities: list[str],
    current_entities: list[str],
    voltage_entities: list[str],
) -> list[dict]:
    """Build W/A/V history sections for each inlet."""
    inlet_numbers = sorted(
        {
            number
            for entity_id in power_entities + current_entities + voltage_entities
            if (number := _inlet_number(entity_id)) is not None
        }
    )
    sections = []
    for number in inlet_numbers[:8]:
        history_entities = _electrical_history_entities(
            power_entities,
            current_entities,
            voltage_entities,
            numbers=[number],
            number_parser=_inlet_number,
        )
        if history_entities:
            sections.append(
                _section(
                    [
                        _heading(f"Inlet {number} History", "mdi:transmission-tower"),
                        _history(f"Inlet {number} W/A/V", history_entities),
                    ],
                    2,
                )
            )
    return sections


def _electrical_history_entities(
    power_entities: list[str],
    current_entities: list[str],
    voltage_entities: list[str],
    *,
    numbers: list[int] | None = None,
    number_parser=None,
    limit: int = 24,
) -> list[str]:
    """Return W/A/V entities grouped by outlet or inlet number where possible."""
    if numbers and number_parser is not None:
        entities = []
        for number in numbers:
            entities.extend(
                entity_id
                for entity_id in (
                    _first_by_number(power_entities, number, number_parser),
                    _first_by_number(current_entities, number, number_parser),
                    _first_by_number(voltage_entities, number, number_parser),
                )
                if entity_id
            )
        return entities[:limit]
    return (power_entities[: limit // 3] + current_entities[: limit // 3] + voltage_entities[: limit // 3])[:limit]


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
    dashboard_slug: str,
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
        title_card = _outlet_title_card(
            number,
            primary_entity,
            power_entity,
            current_entity,
            frontend_features,
            dashboard_slug,
        )
        cards.append(title_card)
    return [card for card in cards if card]


def _outlet_title_card(
    number: int,
    primary_entity: str,
    power_entity: str | None,
    current_entity: str | None,
    frontend_features: dict[str, bool],
    dashboard_slug: str,
) -> dict:
    navigation_path = f"/ldcs-{dashboard_slug}/outlet-history"
    if frontend_features.get("mushroom"):
        return {
            "type": "custom:mushroom-template-card",
            "primary": f"Outlet {number}",
            "secondary": _mushroom_outlet_secondary(power_entity, current_entity),
            "icon": "mdi:power-socket-au",
            "entity": primary_entity,
            "icon_color": _mushroom_outlet_icon_color(primary_entity),
            "layout": "horizontal",
            "fill_container": True,
            "multiline_secondary": True,
            "tap_action": {"action": "navigate", "navigation_path": navigation_path},
            "hold_action": {"action": "more-info"},
        }
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
        return {
            "type": "custom:bubble-card",
            "card_type": "button",
            "button_type": "state",
            "entity": primary_entity,
            "name": f"Outlet {number}",
            "icon": "mdi:power-socket-au",
            "show_state": True,
            "card_layout": "large",
            "sub_button": sub_buttons,
            "button_action": {
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": navigation_path,
                },
                "hold_action": {"action": "more-info"},
            },
        }
    return {
        "type": "tile",
        "entity": primary_entity,
        "name": f"Outlet {number}",
        "icon": "mdi:power-socket-au",
        "tap_action": {"action": "navigate", "navigation_path": navigation_path},
        "hold_action": {"action": "more-info"},
    }


def _sensor_history_expander(
    title: str,
    icon: str,
    entity_ids: list[str],
    frontend_features: dict[str, bool],
) -> dict | None:
    if not entity_ids:
        return None
    title_card = {"type": "heading", "heading": title, "heading_style": "subtitle", "icon": icon}
    return _expander_card(
        title=title,
        title_card=title_card,
        cards=[_history(f"{title} history", entity_ids[:8])],
        frontend_features=frontend_features,
    )


def _expander_card(
    *,
    title: str,
    title_card: dict | None,
    cards: list[dict | None],
    frontend_features: dict[str, bool],
) -> dict | None:
    child_cards = [card for card in cards if card]
    if title_card is None or not child_cards:
        return title_card
    if frontend_features.get("expander_card"):
        return {
            "type": "custom:expander-card",
            "title": title,
            "title-card": title_card,
            "title-card-clickable": True,
            "child-margin-top": "0.6em",
            "padding": 0,
            "clear": True,
            "expanded": False,
            "cards": child_cards,
        }
    return {"type": "vertical-stack", "cards": [title_card, *child_cards]}


def _mushroom_outlet_secondary(
    power_entity: str | None,
    current_entity: str | None,
) -> str:
    values = []
    if power_entity:
        values.append(_mushroom_state_with_unit(power_entity, "Power"))
    if current_entity:
        values.append(_mushroom_state_with_unit(current_entity, "Current"))
    return " | ".join(values) if values else "Tap for history"


def _mushroom_state_with_unit(entity_id: str, label: str) -> str:
    return (
        f"{label}: {{{{ states('{entity_id}') }}}} "
        f"{{{{ state_attr('{entity_id}', 'unit_of_measurement') or '' }}}}"
    )


def _mushroom_outlet_icon_color(entity_id: str) -> str:
    return (
        "{% if is_state('" + entity_id + "', 'on') %}"
        "green"
        "{% elif is_state('" + entity_id + "', 'off') %}"
        "red"
        "{% else %}"
        "blue"
        "{% endif %}"
    )


def _outlet_number(entity_id: str) -> int | None:
    match = re.search(r"outlet[_-](\d+)", entity_id.lower())
    if match is None:
        return None
    return int(match.group(1))


def _inlet_number(entity_id: str) -> int | None:
    match = re.search(r"inlet[_-](\d+)", entity_id.lower())
    if match is None:
        return None
    return int(match.group(1))


def _first_by_number(
    entity_ids: list[str],
    number: int,
    number_parser,
) -> str | None:
    for entity_id in entity_ids:
        if number_parser(entity_id) == number:
            return entity_id
    return None


def _history_name(entity_id: str) -> str:
    lowered = entity_id.lower()
    outlet_number = _outlet_number(lowered)
    if outlet_number is not None:
        if "active_power" in lowered:
            return f"Outlet {outlet_number} W"
        if "current" in lowered:
            return f"Outlet {outlet_number} A"
        if "voltage" in lowered:
            return f"Outlet {outlet_number} V"
        return f"Outlet {outlet_number}"
    inlet_number = _inlet_number(lowered)
    if inlet_number is not None:
        if "active_power" in lowered:
            return f"Inlet {inlet_number} W"
        if "current" in lowered:
            return f"Inlet {inlet_number} A"
        if "voltage" in lowered:
            return f"Inlet {inlet_number} V"
        if "frequency" in lowered:
            return f"Inlet {inlet_number} Hz"
        return f"Inlet {inlet_number}"
    if "temperature" in lowered:
        return _short_sensor_name(entity_id, "Temperature")
    if "humidity" in lowered:
        return _short_sensor_name(entity_id, "Humidity")
    return _short_sensor_name(entity_id, entity_id.split(".", 1)[-1])


def _short_sensor_name(entity_id: str, fallback: str) -> str:
    object_id = entity_id.split(".", 1)[-1]
    parts = [
        part
        for part in object_id.split("_")
        if part
        and part
        not in {
            "lab",
            "ldcs",
            "legrand",
            "my",
            "pdu",
            "raritan",
            "xerus",
        }
    ]
    if not parts:
        return fallback
    return " ".join(part.upper() if len(part) <= 2 else part.title() for part in parts[:4])


def _matching(entities: list[str], *needles: str) -> list[str]:
    values = []
    for entity_id in entities:
        lowered = entity_id.lower()
        if any(needle in lowered for needle in needles):
            values.append(entity_id)
    return sorted(set(values), key=_natural_sort_key)


def _matching_all(entities: list[str], *needles: str) -> list[str]:
    values = []
    for entity_id in entities:
        lowered = entity_id.lower()
        if all(needle in lowered for needle in needles):
            values.append(entity_id)
    return sorted(set(values), key=_natural_sort_key)


def _metric_entities(entities: list[str], include: str, *exclude: str) -> list[str]:
    """Return metric entities while excluding similarly named derived values."""
    values = []
    include_token = f"_{include}"
    for entity_id in entities:
        lowered = entity_id.lower()
        if include_token not in lowered and not lowered.endswith(include):
            continue
        if any(token in lowered for token in exclude):
            continue
        values.append(entity_id)
    return sorted(set(values), key=_natural_sort_key)


def _controllable_switch_entities(entities: list[str]) -> list[str]:
    """Return writable non-outlet switch entities for rack handles and dry contacts."""
    controls = []
    for entity_id in entities:
        lowered = entity_id.lower()
        if not lowered.startswith("switch."):
            continue
        if "_outlet_" in lowered and lowered.endswith("_power"):
            continue
        if any(token in lowered for token in ("door", "handle", "lock", "contact", "dry", "sensor")):
            controls.append(entity_id)
    return sorted(set(controls), key=_natural_sort_key)


def _first(entities: list[str], *needles: str) -> str | None:
    for entity_id in entities:
        lowered = entity_id.lower()
        if all(needle in lowered for needle in needles):
            return entity_id
    return None


def _first_sensor(entities: list[str], *needles: str) -> str | None:
    return _first([entity_id for entity_id in entities if entity_id.startswith("sensor.")], *needles)


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
