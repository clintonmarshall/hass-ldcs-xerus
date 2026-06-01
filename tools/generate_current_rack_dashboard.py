#!/usr/bin/env python3
"""Generate a visual single-rack Lovelace dashboard from the LDCS entity registry."""

from __future__ import annotations

import json
import re
from pathlib import Path

REGISTRY_PATH = Path("/tmp/ldcs-core.entity_registry")
OUTPUT_PATH = Path("/tmp/lovelace.rack")


def load_entities() -> list[dict]:
    registry = json.loads(REGISTRY_PATH.read_text())
    return [
        entity
        for entity in registry["data"]["entities"]
        if entity.get("platform") == "ldcs" and not entity.get("disabled_by")
    ]


def entity(entities: list[dict], entity_id: str) -> str | None:
    return entity_id if any(item["entity_id"] == entity_id for item in entities) else None


def first(entities: list[dict], *entity_ids: str) -> str | None:
    for entity_id in entity_ids:
        if entity(entities, entity_id):
            return entity_id
    return None


def by_prefix(entities: list[dict], prefix: str, suffix: str | None = None) -> list[str]:
    values = []
    for item in entities:
        entity_id = item["entity_id"]
        if entity_id.startswith(prefix) and (suffix is None or entity_id.endswith(suffix)):
            values.append(entity_id)
    return sorted(values, key=natural_sort_key)


def natural_sort_key(value: str) -> list[int | str]:
    parts: list[int | str] = []
    current = ""
    for char in value:
        if char.isdigit():
            current += char
        else:
            if current:
                parts.append(int(current))
                current = ""
            parts.append(char)
    if current:
        parts.append(int(current))
    return parts


def template_tile(entity_id: str, primary: str, secondary: str, icon: str, color: str) -> dict:
    return {
        "type": "custom:mushroom-template-card",
        "entity": entity_id,
        "primary": primary,
        "secondary": secondary,
        "icon": icon,
        "icon_color": color,
        "multiline_secondary": True,
        "tap_action": {"action": "more-info"},
    }


def gauge(entity_id: str, name: str, severity: dict | None = None) -> dict:
    return {
        "type": "gauge",
        "entity": entity_id,
        "name": name,
        "needle": True,
        "severity": severity or {"green": 0, "yellow": 60, "red": 85},
    }


def heading(text: str, icon: str) -> dict:
    return {"type": "heading", "heading": text, "heading_style": "title", "icon": icon}


def graph(name: str, entities: list[str], hours: int = 12) -> dict | None:
    if not entities:
        return None
    return {
        "type": "custom:mini-graph-card",
        "name": name,
        "hours_to_show": hours,
        "points_per_hour": 6,
        "line_width": 2,
        "show": {"legend": True, "labels": True},
        "entities": [{"entity": item, "name": item.split(".")[-1].replace("_", " ")} for item in entities],
    }


def entities_card(title: str, entity_ids: list[str]) -> dict | None:
    filtered = [item for item in entity_ids if item]
    if not filtered:
        return None
    return {
        "type": "entities",
        "title": title,
        "show_header_toggle": False,
        "entities": filtered,
    }


def outlet_tiles(entities: list[dict], pdu: str) -> list[dict]:
    cards = []
    states = by_prefix(entities, f"sensor.{pdu}_outlet_", "_outlet_state")
    for state_sensor in states[:36]:
        base = state_sensor.removesuffix("_outlet_state")
        power = entity(entities, f"{base}_active_power")
        switch = entity(entities, f"switch.{base.removeprefix('sensor.')}_power")
        match = re.search(r"_outlet_(\d+)_", state_sensor)
        outlet_name = match.group(1) if match else "?"
        cards.append(
            template_tile(
                switch or state_sensor,
                f"{pdu.replace('_', ' ').upper()} outlet {outlet_name}",
                (
                    f"State {{{{ states('{state_sensor}') | title }}}}"
                    + (f"  |  Load {{{{ states('{power}') }}}} W" if power else "")
                ),
                "mdi:power-socket-au",
                (
                    f"{{% set outlet_state = states('{state_sensor}') | lower %}}"
                    "{% if 'cycl' in outlet_state %}amber"
                    "{% elif outlet_state in ['on', 'true'] %}green"
                    "{% elif outlet_state in ['off', 'false'] %}red"
                    "{% else %}grey{% endif %}"
                ),
            )
        )
    return cards


def section(cards: list[dict | None], column_span: int = 1) -> dict:
    return {
        "type": "grid",
        "column_span": column_span,
        "cards": [card for card in cards if card],
    }


def build_dashboard(entities: list[dict]) -> dict:
    pdu_a_power = first(entities, "sensor.pro4x_pdu_a_inlet_1_active_power")
    pdu_b_power = first(entities, "sensor.pro4x_pdu_b_inlet_1_active_power")
    pdu_a_current = first(entities, "sensor.pro4x_pdu_a_inlet_1_current")
    pdu_b_current = first(entities, "sensor.pro4x_pdu_b_inlet_1_current")
    alarm = first(entities, "sensor.pro4x_pdu_a_alarm_status")
    breaches = first(entities, "sensor.pro4x_pdu_a_active_breach_count")
    warning = first(entities, "sensor.pro4x_pdu_a_warning_sensor_count")
    critical = first(entities, "sensor.pro4x_pdu_a_critical_sensor_count")
    security = first(entities, "sensor.pro4x_pdu_a_rack_security_status")

    visual = {
        "type": "custom:raritan-rack-visual-card",
        "title": "Rack live containment",
        "entities": {
            "frontDoor": first(entities, "sensor.pro4x_pdu_a_front_door_door_state"),
            "rearDoor": first(entities, "sensor.pro4x_pdu_a_door_state_2_door_state"),
            "frontLock": first(entities, "sensor.pro4x_pdu_a_door_handle_1_door_lock_state"),
            "rearLock": first(entities, "sensor.pro4x_pdu_a_door_handle_2_door_lock_state"),
            "alarmA": alarm,
            "alarmB": alarm,
            "securityStatus": security,
            "assetInventories": [
                item
                for item in (
                    first(entities, "sensor.pro4x_pdu_a_asset_strip_inventory"),
                    first(entities, "sensor.pro4x_pdu_b_asset_strip_inventory"),
                )
                if item
            ],
        },
    }

    overview_sections = [
        section([heading("Rack Visual", "mdi:server-rack"), visual], 2),
        section(
            [
                heading("Live Status", "mdi:pulse"),
                template_tile(
                    alarm or pdu_a_power,
                    "Rack alarm beacon",
                    (
                        f"Status {{{{ states('{alarm}') }}}}  |  "
                        f"Breaches {{{{ states('{breaches}') }}}}  |  "
                        f"Warning {{{{ states('{warning}') }}}}  |  "
                        f"Critical {{{{ states('{critical}') }}}}"
                    ),
                    "mdi:alarm-light",
                    (
                        f"{{% if states('{alarm}') == 'critical' or states('{critical}') | int(0) > 0 %}}red"
                        f"{{% elif states('{alarm}') == 'warning' or states('{warning}') | int(0) > 0 %}}amber"
                        f"{{% elif states('{alarm}') == 'normal' %}}green"
                        "{% else %}grey{% endif %}"
                    ),
                ),
                template_tile(
                    security or alarm or pdu_a_power,
                    "Rack security",
                    f"State {{{{ states('{security}') }}}}",
                    "mdi:shield-lock",
                    (
                        f"{{% if states('{security}') == 'normal' %}}green"
                        f"{{% elif states('{security}') in ['unsupported', 'unknown', 'unavailable'] %}}grey"
                        "{% else %}amber{% endif %}"
                    ),
                ),
                gauge(pdu_a_power, "PDU A W") if pdu_a_power else None,
                gauge(pdu_b_power, "PDU B W") if pdu_b_power else None,
            ]
        ),
        section(
            [
                heading("PDU Load", "mdi:flash"),
                graph("Rack inlet power", [item for item in (pdu_a_power, pdu_b_power) if item], 24),
                graph("Rack inlet current", [item for item in (pdu_a_current, pdu_b_current) if item], 24),
                entities_card(
                    "Rack inventories",
                    [
                        first(entities, "sensor.pro4x_pdu_a_external_sensor_inventory"),
                        first(entities, "sensor.pro4x_pdu_b_external_sensor_inventory"),
                        first(entities, "sensor.pro4x_pdu_a_asset_strip_inventory"),
                        first(entities, "sensor.pro4x_pdu_b_asset_strip_inventory"),
                    ],
                ),
            ]
        ),
    ]

    cooling_entities = [
        first(entities, "sensor.usystems_rdhx_192_1_29_89_cabinet_front_room_temperature"),
        first(entities, "sensor.usystems_rdhx_192_1_29_89_air_off_coil_temperature"),
        first(entities, "sensor.usystems_rdhx_192_1_29_89_air_on_coil_temperature"),
        first(entities, "sensor.pro4x_pdu_a_temperature_1_temperature"),
        first(entities, "sensor.pro4x_pdu_a_temperature_2_temperature"),
        first(entities, "sensor.pro4x_pdu_b_garage_temp_temperature"),
        first(entities, "sensor.pro4x_pdu_b_temperature_2_temperature"),
    ]
    cooling_visual = {
        "type": "custom:raritan-cooling-card",
        "title": "Rack cooling airflow",
        "entities": {
            "unitOn": first(entities, "binary_sensor.usystems_rdhx_192_1_29_89_unit_on"),
            "globalAlarm": first(entities, "binary_sensor.usystems_rdhx_192_1_29_89_global_alarm"),
            "leakAlarm": first(entities, "binary_sensor.usystems_rdhx_192_1_29_89_leak_alarm"),
            "airOff": first(entities, "sensor.usystems_rdhx_192_1_29_89_air_off_coil_temperature"),
            "airOn": first(entities, "sensor.usystems_rdhx_192_1_29_89_air_on_coil_temperature"),
            "roomTemp": first(entities, "sensor.usystems_rdhx_192_1_29_89_cabinet_front_room_temperature"),
            "fanFeedback": first(entities, "sensor.usystems_rdhx_192_1_29_89_fan_2_feedback_raw"),
            "valveFeedback": first(entities, "sensor.usystems_rdhx_192_1_29_89_valve_feedback"),
            "rackFrontA": first(entities, "sensor.pro4x_pdu_a_temperature_1_temperature"),
            "rackRearA": first(entities, "sensor.pro4x_pdu_a_temperature_2_temperature"),
            "rackFrontB": first(entities, "sensor.pro4x_pdu_b_garage_temp_temperature"),
            "rackRearB": first(entities, "sensor.pro4x_pdu_b_temperature_2_temperature"),
        },
    }

    views = [
        {
            "title": "Rack Overview",
            "path": "overview",
            "icon": "mdi:server-rack",
            "type": "sections",
            "max_columns": 3,
            "sections": overview_sections,
        },
        {
            "title": "Power",
            "path": "power",
            "icon": "mdi:flash",
            "type": "sections",
            "max_columns": 3,
            "sections": [
                section([heading("PDU A", "mdi:power-plug"), graph("PDU A inlet", [item for item in [pdu_a_power, pdu_a_current] if item], 24)]),
                section([heading("PDU B", "mdi:power-plug"), graph("PDU B inlet", [item for item in [pdu_b_power, pdu_b_current] if item], 24)]),
                section([heading("Breakers", "mdi:electric-switch"), entities_card("OCP trip/current", by_prefix(entities, "sensor.pro4x_pdu_a_ocp_") + by_prefix(entities, "sensor.pro4x_pdu_b_ocp_"))]),
            ],
        },
        {
            "title": "Outlets",
            "path": "outlets",
            "icon": "mdi:power-socket-au",
            "type": "sections",
            "max_columns": 4,
            "sections": [
                section([heading("PDU A Outlets", "mdi:power-strip")] + outlet_tiles(entities, "pro4x_pdu_a"), 2),
                section([heading("PDU B Outlets", "mdi:power-strip")] + outlet_tiles(entities, "pro4x_pdu_b"), 2),
            ],
        },
        {
            "title": "Environment",
            "path": "environment",
            "icon": "mdi:thermometer-water",
            "type": "sections",
            "max_columns": 3,
            "sections": [
                section([heading("Cooling Visual", "mdi:fan"), cooling_visual], 2),
                section([heading("Temperatures", "mdi:thermometer"), graph("Rack temperature history", [item for item in cooling_entities if item], 24)]),
                section([heading("Humidity", "mdi:water-percent"), entities_card("Humidity sensors", by_prefix(entities, "sensor.pro4x_pdu_a_relative_humidity") + by_prefix(entities, "sensor.pro4x_pdu_b_relative_humidity"))]),
            ],
        },
        {
            "title": "Security & Assets",
            "path": "security-assets",
            "icon": "mdi:shield-lock",
            "type": "sections",
            "max_columns": 3,
            "sections": [
                section([heading("Rack Visual", "mdi:server-security"), visual], 2),
                section([heading("Doors & Locks", "mdi:door"), entities_card("Door and lock sensors", by_prefix(entities, "sensor.pro4x_pdu_a_door") + by_prefix(entities, "sensor.pro4x_pdu_a_front_door"))]),
                section([heading("Asset Strip", "mdi:tag-multiple"), entities_card("Asset inventory", [first(entities, "sensor.pro4x_pdu_a_asset_strip_inventory"), first(entities, "sensor.pro4x_pdu_b_asset_strip_inventory")])]),
            ],
        },
        {
            "title": "Events",
            "path": "events",
            "icon": "mdi:alarm-light",
            "type": "sections",
            "max_columns": 3,
            "sections": [
                section([heading("Alarms", "mdi:alarm-light"), entities_card("Alarm summary", [alarm, breaches, warning, critical, first(entities, "sensor.pro4x_pdu_a_acknowledgement_required_alarm_count")])]),
                section([heading("Dry Contacts", "mdi:electric-switch-closed"), entities_card("Dry contact states", by_prefix(entities, "sensor.pro4x_pdu_a_powered_dry_contact") + by_prefix(entities, "sensor.pro4x_pdu_b_powered_dry_contact"))]),
                section([heading("Waveforms", "mdi:sine-wave"), entities_card("Capture and waveform entities", by_prefix(entities, "button.xerus_device_10_210_1_38_inlet_1") + by_prefix(entities, "sensor.pro4x_pdu_a_inlet_1", "waveform") + by_prefix(entities, "sensor.pro4x_pdu_b_inlet_1", "waveform"))]),
            ],
        },
    ]

    return {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace.rack",
        "data": {"config": {"title": "Rack", "views": views}},
    }


def main() -> None:
    OUTPUT_PATH.write_text(json.dumps(build_dashboard(load_entities()), indent=2))
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
