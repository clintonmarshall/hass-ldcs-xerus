#!/usr/bin/env python3
"""Generate a Rack 02 Lovelace dashboard from the Home Assistant entity registry."""

from __future__ import annotations

import json
from pathlib import Path

REGISTRY_PATH = Path("/tmp/px4_core.entity_registry.json")
DASHBOARDS_PATH = Path("/tmp/lovelace_dashboards.json")
OUTPUT_DASHBOARD = Path("lovelace.rack_02")
OUTPUT_DASHBOARDS = Path("lovelace_dashboards.rack_02")

PDU_A = "01KST1698PEEYVTHVWE0BV2J8A"
PDU_B = "01KST19VEW9AFE3NZKXAYZ540S"
PDU_NAMES = {
    PDU_A: "Rack 02 PDU A",
    PDU_B: "Rack 02 PDU B",
}


def load_entities() -> list[dict]:
    """Return enabled PX4 entities for Rack 02."""
    registry = json.loads(REGISTRY_PATH.read_text())
    return [
        entity
        for entity in registry["data"]["entities"]
        if entity.get("platform") == "raritan_px4"
        and entity.get("config_entry_id") in PDU_NAMES
        and not entity.get("disabled_by")
    ]


def entities_for(entities: list[dict], entry_id: str, domain: str) -> list[dict]:
    """Return sorted entities for a PDU and entity domain."""
    prefix = f"{domain}."
    return sorted(
        [
            entity
            for entity in entities
            if entity["config_entry_id"] == entry_id
            and entity["entity_id"].startswith(prefix)
        ],
        key=lambda entity: entity["entity_id"],
    )


def entity_id(entities: list[dict], entry_id: str, original_name: str) -> str:
    """Find one entity by its original name."""
    for entity in entities:
        if entity["config_entry_id"] == entry_id and entity.get("original_name") == original_name:
            return entity["entity_id"]
    raise KeyError(f"Missing {entry_id}: {original_name}")


def optional_entity_id(entities: list[dict], entry_id: str, original_name: str) -> str | None:
    """Find one entity by its original name when present."""
    try:
        return entity_id(entities, entry_id, original_name)
    except KeyError:
        return None


def pdu_summary_card(entities: list[dict], entry_id: str, suffix: str) -> dict:
    """Build one PDU summary tile."""
    inlet_power = entity_id(entities, entry_id, "Inlet 1 Active Power")
    l1_current = entity_id(entities, entry_id, "Inlet 1 L1 Current")
    l2_current = entity_id(entities, entry_id, "Inlet 1 L2 Current")
    l3_current = entity_id(entities, entry_id, "Inlet 1 L3 Current")
    imbalance = entity_id(entities, entry_id, "Inlet 1 Unbalanced Current")
    return {
        "type": "custom:mushroom-template-card",
        "entity": inlet_power,
        "primary": f"{PDU_NAMES[entry_id]} - {suffix}",
        "secondary": (
            f"Three-phase  |  {{{{ states('{inlet_power}') }}}} W\n"
            f"L1 {{{{ states('{l1_current}') }}}} A  |  "
            f"L2 {{{{ states('{l2_current}') }}}} A  |  "
            f"L3 {{{{ states('{l3_current}') }}}} A\n"
            f"Current unbalance {{{{ states('{imbalance}') }}}} %"
        ),
        "icon": "mdi:power-strip",
        "icon_color": (
            f"{{% if states('{imbalance}') in ['unknown', 'unavailable'] %}}grey"
            f"{{% elif states('{imbalance}') | float(0) >= 20 %}}red"
            f"{{% elif states('{imbalance}') | float(0) >= 10 %}}amber"
            "{% else %}green{% endif %}"
        ),
        "layout": "vertical",
        "multiline_secondary": True,
        "tap_action": {"action": "more-info"},
    }


def phase_balance_cards(entities: list[dict], entry_id: str) -> list[dict]:
    """Build phase-current tiles and inlet unbalance indicators."""
    cards = []
    for line in ("L1", "L2", "L3"):
        current = entity_id(entities, entry_id, f"Inlet 1 {line} Current")
        voltage = entity_id(entities, entry_id, f"Inlet 1 {line} Voltage L N")
        power = entity_id(entities, entry_id, f"Inlet 1 {line} Active Power")
        cards.append(
            {
                "type": "custom:mushroom-template-card",
                "entity": current,
                "primary": f"{PDU_NAMES[entry_id]} {line}",
                "secondary": (
                    "{{ states(entity) }} A  |  "
                    f"{{{{ states('{voltage}') }}}} V LN  |  "
                    f"{{{{ states('{power}') }}}} W"
                ),
                "icon": "mdi:sine-wave",
                "icon_color": (
                    "{% if states(entity) in ['unknown', 'unavailable'] %}grey"
                    "{% elif state_attr(entity, 'above_upper_critical') %}red"
                    "{% elif state_attr(entity, 'above_upper_warning') %}amber"
                    "{% else %}green{% endif %}"
                ),
                "tap_action": {"action": "more-info"},
            }
        )
    for field, label in (
        ("Unbalanced Current", "Current unbalance"),
        ("Unbalanced Voltage", "Voltage unbalance"),
        ("Unbalanced Line Line Voltage", "Line-line voltage unbalance"),
    ):
        sensor = optional_entity_id(entities, entry_id, f"Inlet 1 {field}")
        if sensor:
            cards.append(alarm_tile(sensor, f"{PDU_NAMES[entry_id]} {label}", "mdi:scale-balance"))
    return cards


def breaker_cards(entities: list[dict], entry_id: str) -> list[dict]:
    """Build OCP load tiles with the known upstream phase."""
    cards = []
    lines = ("L1", "L2", "L3", "L1", "L2", "L3")
    for ocp_number, line in enumerate(lines, start=1):
        current = entity_id(entities, entry_id, f"OCP {ocp_number} Current")
        trip = entity_id(entities, entry_id, f"OCP {ocp_number} Trip")
        cards.append(
            {
                "type": "custom:mushroom-template-card",
                "entity": current,
                "primary": f"C{ocp_number}  |  {line}",
                "secondary": (
                    "{{ states(entity) }} A / "
                    "{{ state_attr(entity, 'rated_current_a') or '-' }} A  |  "
                    f"{{{{ states('{trip}') | title }}}}"
                ),
                "icon": "mdi:electric-switch",
                "icon_color": (
                    f"{{% if states('{trip}') not in ['0', 'off', 'normal', 'untripped'] %}}red"
                    "{% elif state_attr(entity, 'above_upper_critical') %}red"
                    "{% elif state_attr(entity, 'above_upper_warning') %}amber"
                    "{% else %}green{% endif %}"
                ),
                "tap_action": {"action": "more-info"},
            }
        )
    return cards


def pdu_alarm_card(entities: list[dict], entry_id: str) -> dict:
    """Build one PDU alarm summary tile."""
    status = entity_id(entities, entry_id, "Alarm Status")
    breaches = entity_id(entities, entry_id, "Active Breach Count")
    warnings = entity_id(entities, entry_id, "Warning Sensor Count")
    critical = entity_id(entities, entry_id, "Critical Sensor Count")
    acknowledgements = entity_id(entities, entry_id, "Acknowledgement Required Alarm Count")
    return {
        "type": "custom:mushroom-template-card",
        "entity": status,
        "primary": f"{PDU_NAMES[entry_id]} alarms",
        "secondary": (
            f"{{{{ states('{breaches}') }}}} active  |  "
            f"{{{{ states('{warnings}') }}}} warning  |  "
            f"{{{{ states('{critical}') }}}} critical  |  "
            f"{{{{ states('{acknowledgements}') }}}} ack"
        ),
        "icon": "mdi:alarm-light",
        "icon_color": (
            "{% if states(entity) == 'critical' %}red"
            "{% elif states(entity) == 'warning' %}amber"
            "{% elif states(entity) == 'normal' %}green"
            "{% else %}grey{% endif %}"
        ),
        "multiline_secondary": True,
        "tap_action": {"action": "more-info"},
    }


def rack_alarm_card(entities: list[dict]) -> dict:
    """Build the combined Rack 02 alarm tile."""
    a_status = entity_id(entities, PDU_A, "Alarm Status")
    b_status = entity_id(entities, PDU_B, "Alarm Status")
    a_breaches = entity_id(entities, PDU_A, "Active Breach Count")
    b_breaches = entity_id(entities, PDU_B, "Active Breach Count")
    a_ack = entity_id(entities, PDU_A, "Acknowledgement Required Alarm Count")
    b_ack = entity_id(entities, PDU_B, "Acknowledgement Required Alarm Count")
    return {
        "type": "custom:mushroom-template-card",
        "entity": a_status,
        "primary": "Rack 02 alarm summary",
        "secondary": (
            f"{{{{ states('{a_breaches}') | int(0) + states('{b_breaches}') | int(0) }}}} "
            f"active breaches  |  "
            f"{{{{ states('{a_ack}') | int(0) + states('{b_ack}') | int(0) }}}} "
            "acknowledgements required"
        ),
        "icon": "mdi:shield-alert-outline",
        "icon_color": (
            f"{{% if states('{a_status}') == 'critical' or states('{b_status}') == 'critical' %}}red"
            f"{{% elif states('{a_status}') == 'warning' or states('{b_status}') == 'warning' %}}amber"
            f"{{% elif states('{a_status}') == 'normal' and states('{b_status}') == 'normal' %}}green"
            "{% else %}grey{% endif %}"
        ),
        "tap_action": {"action": "navigate", "navigation_path": "/rack-02/alarms"},
    }


def pdu_security_card(entities: list[dict], entry_id: str) -> dict:
    """Build one PDU rack security status tile."""
    status = entity_id(entities, entry_id, "Rack Security Status")
    rules = entity_id(entities, entry_id, "Door Access Rule Count")
    events = entity_id(entities, entry_id, "Recent Rack Access Event Count")
    return {
        "type": "custom:mushroom-template-card",
        "entity": status,
        "primary": f"{PDU_NAMES[entry_id]} security",
        "secondary": (
            "Smartlock {{ states(entity) }}  |  "
            f"{{{{ states('{rules}') }}}} rules  |  "
            f"{{{{ states('{events}') }}}} recent events"
        ),
        "icon": "mdi:lock-check",
        "icon_color": (
            "{% if states(entity) == 'normal' %}green"
            "{% elif states(entity) == 'unsupported' %}grey"
            "{% elif states(entity) in ['unknown', 'unavailable'] %}grey"
            "{% else %}amber{% endif %}"
        ),
        "multiline_secondary": True,
        "tap_action": {"action": "navigate", "navigation_path": "/rack-02/rack-security"},
    }


def rack_security_card(entities: list[dict]) -> dict:
    """Build the combined Rack 02 security tile."""
    a_status = entity_id(entities, PDU_A, "Rack Security Status")
    b_status = entity_id(entities, PDU_B, "Rack Security Status")
    a_events = entity_id(entities, PDU_A, "Recent Rack Access Event Count")
    b_events = entity_id(entities, PDU_B, "Recent Rack Access Event Count")
    return {
        "type": "custom:mushroom-template-card",
        "entity": a_status,
        "primary": "Rack 02 security summary",
        "secondary": (
            f"{{{{ states('{a_events}') | int(0) + states('{b_events}') | int(0) }}}} recent access events"
        ),
        "icon": "mdi:shield-lock",
        "icon_color": (
            f"{{% if states('{a_status}') == 'normal' or states('{b_status}') == 'normal' %}}green"
            f"{{% elif states('{a_status}') == 'unsupported' and states('{b_status}') == 'unsupported' %}}grey"
            "{% else %}amber{% endif %}"
        ),
        "tap_action": {"action": "navigate", "navigation_path": "/rack-02/rack-security"},
    }


def security_entities_card(entities: list[dict], entry_id: str) -> dict:
    """Build detailed security entity list for one PDU."""
    names = (
        "Rack Security Status",
        "Door Access Rule Count",
        "Recent Rack Access Event Count",
    )
    return {
        "type": "entities",
        "title": PDU_NAMES[entry_id],
        "show_header_toggle": False,
        "entities": [entity_id(entities, entry_id, name) for name in names],
    }


def reset_extrema_card(entities: list[dict], entry_id: str) -> dict | None:
    """Build a min/max reset button for one PDU."""
    reset = optional_entity_id(entities, entry_id, "Reset Sensor Minimum and Maximum Values")
    if reset is None:
        return None
    return {
        "type": "button",
        "entity": reset,
        "name": f"{PDU_NAMES[entry_id]} reset min/max",
        "icon": "mdi:restore-alert",
        "show_state": False,
        "tap_action": {"action": "toggle"},
    }


def cooling_visual_card(entities: list[dict]) -> dict:
    """Build the animated RDHx rack cooling visual."""
    return {
        "type": "custom:raritan-cooling-card",
        "title": "Rack 02 cooling containment",
        "entities": {
            "unitOn": "binary_sensor.usystems_rdhx_unit_on",
            "globalAlarm": "binary_sensor.usystems_rdhx_global_alarm",
            "leakAlarm": "binary_sensor.usystems_rdhx_leak_alarm",
            "coilWarning": "binary_sensor.usystems_rdhx_coil_clean_warning",
            "filterWarning": "binary_sensor.usystems_rdhx_filter_clean_warning",
            "fanWarning": "binary_sensor.usystems_rdhx_fan_check_warning",
            "serviceWarning": "binary_sensor.usystems_rdhx_service_warning",
            "valveWarning": "binary_sensor.usystems_rdhx_valve_check_warning",
            "airOff": "sensor.usystems_rdhx_air_off_coil_temperature",
            "airOn": "sensor.usystems_rdhx_air_on_coil_temperature",
            "altAirOff": "sensor.usystems_rdhx_alternative_air_off_temperature",
            "altAirOn": "sensor.usystems_rdhx_alternative_air_on_temperature",
            "roomTemp": "sensor.usystems_rdhx_cabinet_front_room_temperature",
            "fanCommand": "sensor.usystems_rdhx_fan_2_command",
            "fanFeedback": "sensor.usystems_rdhx_fan_2_feedback_raw",
            "valveRequest": "sensor.usystems_rdhx_valve_request",
            "valveFeedback": "sensor.usystems_rdhx_valve_feedback",
            "rackFrontA": optional_entity_id(entities, PDU_A, "Temperature 1 Temperature"),
            "rackRearA": optional_entity_id(entities, PDU_A, "Temperature 2 Temperature"),
            "rackFrontB": optional_entity_id(entities, PDU_B, "Temperature 1 Temperature"),
            "rackRearB": optional_entity_id(entities, PDU_B, "Temperature 2 Temperature"),
        },
    }


def cooling_health_card() -> dict:
    """Build RDHx operational health tile."""
    unit = "binary_sensor.usystems_rdhx_unit_on"
    alarm = "binary_sensor.usystems_rdhx_global_alarm"
    leak = "binary_sensor.usystems_rdhx_leak_alarm"
    fan = "sensor.usystems_rdhx_fan_2_feedback_raw"
    valve = "sensor.usystems_rdhx_valve_feedback"
    return {
        "type": "custom:mushroom-template-card",
        "entity": alarm,
        "primary": "RDHx cooling health",
        "secondary": (
            f"Unit {{{{ states('{unit}') }}}}  |  "
            f"Fan {{{{ states('{fan}') }}}}%  |  "
            f"Valve {{{{ states('{valve}') }}}}%  |  "
            f"Leak {{{{ states('{leak}') }}}}"
        ),
        "icon": "mdi:fan",
        "icon_color": (
            f"{{% if states('{alarm}') == 'on' or states('{leak}') == 'on' %}}red"
            f"{{% elif states('{unit}') == 'on' %}}green"
            "{% else %}grey{% endif %}"
        ),
        "multiline_secondary": True,
        "tap_action": {"action": "more-info"},
    }


def cooling_alarm_card() -> dict:
    """Build RDHx warning and alarm entity list."""
    return {
        "type": "entities",
        "title": "RDHx alarms and warnings",
        "show_header_toggle": False,
        "entities": [
            "binary_sensor.usystems_rdhx_global_alarm",
            "binary_sensor.usystems_rdhx_leak_alarm",
            "binary_sensor.usystems_rdhx_fan_global_alarm",
            "binary_sensor.usystems_rdhx_fan_2_speed_alarm",
            "binary_sensor.usystems_rdhx_high_air_off_temperature_alarm",
            "binary_sensor.usystems_rdhx_low_air_off_temperature_alarm",
            "binary_sensor.usystems_rdhx_high_temperature_zone_1_alarm",
            "binary_sensor.usystems_rdhx_high_temperature_zone_2_alarm",
            "binary_sensor.usystems_rdhx_coil_clean_warning",
            "binary_sensor.usystems_rdhx_filter_clean_warning",
            "binary_sensor.usystems_rdhx_fan_check_warning",
            "binary_sensor.usystems_rdhx_service_warning",
            "binary_sensor.usystems_rdhx_valve_check_warning",
            "binary_sensor.usystems_rdhx_valve_feedback_alarm",
        ],
    }


def cooling_controls_card() -> dict:
    """Build RDHx controls and setpoint telemetry entity list."""
    return {
        "type": "entities",
        "title": "RDHx setpoints and control loop",
        "show_header_toggle": False,
        "entities": [
            "sensor.usystems_rdhx_fan_setpoint",
            "sensor.usystems_rdhx_fan_differential",
            "sensor.usystems_rdhx_fan_minimum_speed",
            "sensor.usystems_rdhx_fan_maximum_speed",
            "sensor.usystems_rdhx_valve_setpoint",
            "sensor.usystems_rdhx_valve_differential",
            "sensor.usystems_rdhx_valve_minimum_opening",
            "sensor.usystems_rdhx_valve_maximum_opening",
            "sensor.usystems_rdhx_zone_2_setpoint",
            "sensor.usystems_rdhx_zone_2_differential",
        ],
    }


def cooling_graph_cards(entities: list[dict]) -> list[dict]:
    """Build temperature and cooling-control history cards."""
    rack_front_a = optional_entity_id(entities, PDU_A, "Temperature 1 Temperature")
    rack_rear_a = optional_entity_id(entities, PDU_A, "Temperature 2 Temperature")
    rack_front_b = optional_entity_id(entities, PDU_B, "Temperature 1 Temperature")
    rack_rear_b = optional_entity_id(entities, PDU_B, "Temperature 2 Temperature")
    rack_temp_entities = [
        {"entity": entity, "name": name}
        for entity, name in (
            (rack_front_a, "PDU A front"),
            (rack_rear_a, "PDU A rear"),
            (rack_front_b, "PDU B front"),
            (rack_rear_b, "PDU B rear"),
            ("sensor.usystems_rdhx_cabinet_front_room_temperature", "Room"),
            ("sensor.usystems_rdhx_air_off_coil_temperature", "Air off"),
            ("sensor.usystems_rdhx_air_on_coil_temperature", "Air on"),
        )
        if entity
    ]
    return [
        {
            "type": "custom:mini-graph-card",
            "name": "Rack and RDHx temperatures",
            "icon": "mdi:thermometer-lines",
            "hours_to_show": 12,
            "points_per_hour": 12,
            "line_width": 2,
            "show": {"legend": True, "labels": True},
            "entities": rack_temp_entities,
        },
        {
            "type": "custom:mini-graph-card",
            "name": "Fan and valve response",
            "icon": "mdi:fan",
            "hours_to_show": 12,
            "points_per_hour": 12,
            "line_width": 2,
            "show": {"legend": True, "labels": True},
            "entities": [
                {"entity": "sensor.usystems_rdhx_fan_2_command", "name": "Fan command"},
                {"entity": "sensor.usystems_rdhx_fan_2_feedback_raw", "name": "Fan feedback"},
                {"entity": "sensor.usystems_rdhx_valve_request", "name": "Valve request"},
                {"entity": "sensor.usystems_rdhx_valve_feedback", "name": "Valve feedback"},
            ],
        },
    ]


def outlet_power_entities(entities: list[dict], entry_id: str) -> list[str]:
    """Return active power entities for every outlet on one PDU."""
    return [
        entity
        for number in range(1, 37)
        if (entity := optional_entity_id(entities, entry_id, f"Outlet {number} Active Power"))
    ]


def outlet_load_history_cards(entities: list[dict]) -> list[dict]:
    """Build visual outlet load min/max cards and history graphs."""
    a_entities = outlet_power_entities(entities, PDU_A)
    b_entities = outlet_power_entities(entities, PDU_B)
    return [
        {
            "type": "custom:raritan-outlet-load-card",
            "title": "Rack 02 PDU A outlet loads",
            "entities": a_entities,
        },
        {
            "type": "custom:raritan-outlet-load-card",
            "title": "Rack 02 PDU B outlet loads",
            "entities": b_entities,
        },
        {
            "type": "custom:mini-graph-card",
            "name": "PDU A outlet load history",
            "icon": "mdi:chart-line",
            "hours_to_show": 24,
            "points_per_hour": 6,
            "line_width": 2,
            "show": {"legend": True, "labels": True},
            "entities": [{"entity": entity, "name": f"A{index + 1:02d}"} for index, entity in enumerate(a_entities[:12])],
        },
        {
            "type": "custom:mini-graph-card",
            "name": "PDU B outlet load history",
            "icon": "mdi:chart-line",
            "hours_to_show": 24,
            "points_per_hour": 6,
            "line_width": 2,
            "show": {"legend": True, "labels": True},
            "entities": [{"entity": entity, "name": f"B{index + 1:02d}"} for index, entity in enumerate(b_entities[:12])],
        },
    ]


def rack_visual_card(entities: list[dict]) -> dict:
    """Build the animated rack door, beacon, and asset strip visual card."""
    return {
        "type": "custom:raritan-rack-visual-card",
        "title": "Rack 02 live rack visual",
        "entities": {
            "frontDoor": optional_entity_id(entities, PDU_A, "Door State 1 Door State"),
            "rearDoor": optional_entity_id(entities, PDU_A, "Door State 2 Door State"),
            "frontDoorB": optional_entity_id(entities, PDU_B, "Door State 1 Door State"),
            "rearDoorB": optional_entity_id(entities, PDU_B, "Door State 2 Door State"),
            "frontLock": optional_entity_id(entities, PDU_A, "Door Handle 1 Door Lock State"),
            "rearLock": optional_entity_id(entities, PDU_A, "Door Handle 2 Door Lock State"),
            "frontLockB": optional_entity_id(entities, PDU_B, "Door Handle 1 Door Lock State"),
            "rearLockB": optional_entity_id(entities, PDU_B, "Door Handle 2 Door Lock State"),
            "alarmA": entity_id(entities, PDU_A, "Alarm Status"),
            "alarmB": entity_id(entities, PDU_B, "Alarm Status"),
            "securityStatus": entity_id(entities, PDU_A, "Rack Security Status"),
            "assetInventory": (
                optional_entity_id(entities, PDU_A, "Asset Strip Inventory")
                or optional_entity_id(entities, PDU_B, "Asset Strip Inventory")
                or optional_entity_id(entities, PDU_A, "Asset Log Total Event Count")
            ),
        },
    }


def alarm_entities_card(entities: list[dict], entry_id: str) -> dict:
    """Build the detailed alarm entity list for one PDU."""
    names = (
        "Alarm Status",
        "Active Breach Count",
        "Warning Sensor Count",
        "Critical Sensor Count",
        "Acknowledgement Required Alarm Count",
    )
    return {
        "type": "entities",
        "title": PDU_NAMES[entry_id],
        "show_header_toggle": False,
        "entities": [entity_id(entities, entry_id, name) for name in names],
    }


def alarm_tile(entity: str, label: str, icon: str) -> dict:
    """Build an alarm-aware sensor tile."""
    return {
        "type": "custom:mushroom-template-card",
        "entity": entity,
        "primary": label,
        "secondary": "{{ states(entity) }} {{ state_attr(entity, 'unit_of_measurement') or '' }}",
        "icon": icon,
        "icon_color": (
            "{% if states(entity) in ['unknown', 'unavailable'] %}grey"
            "{% elif state_attr(entity, 'above_upper_critical') or "
            "state_attr(entity, 'below_lower_critical') %}red"
            "{% elif state_attr(entity, 'above_upper_warning') or "
            "state_attr(entity, 'below_lower_warning') %}amber"
            "{% else %}green{% endif %}"
        ),
        "tap_action": {"action": "more-info"},
    }


def outlet_card(
    switch_entity: str,
    active_power: str | None,
    state_sensor: str | None,
    label: str,
    outlet_number: int,
) -> dict:
    """Build a colored outlet mimic tile."""
    state_expression = f"states('{state_sensor}')" if state_sensor else "states(entity)"
    power_expression = f"states('{active_power}')" if active_power else "'-'"
    return {
        "type": "custom:mushroom-template-card",
        "entity": switch_entity,
        "primary": (
            f"{label}  |  "
            "{{ state_attr(entity, 'configured_name') or "
            f"'Outlet {outlet_number}' }}}}"
        ),
        "secondary": (
            f"{{{{ {state_expression} | title }}}}  |  "
            f"{{{{ {power_expression} }}}} W"
        ),
        "icon": "mdi:power-socket-au",
        "icon_color": (
            f"{{% set outlet_state = {state_expression} %}}"
            "{% if outlet_state in ['power_cycling', 'cycling'] %}amber"
            "{% elif states(entity) == 'on' %}green"
            "{% elif states(entity) == 'off' %}red"
            "{% else %}grey{% endif %}"
        ),
        "tap_action": {"action": "more-info"},
        "hold_action": {"action": "toggle"},
        "double_tap_action": {"action": "none"},
    }


def outlet_cards(entities: list[dict], entry_id: str, prefix: str) -> list[dict]:
    """Build tiles for all Redfish switches on one PDU."""
    cards = []
    for outlet_number in range(1, 37):
        switch_entity = entity_id(entities, entry_id, f"Outlet {outlet_number} Power")
        cards.append(
            outlet_card(
                switch_entity,
                optional_entity_id(entities, entry_id, f"Outlet {outlet_number} Active Power"),
                optional_entity_id(entities, entry_id, f"Outlet {outlet_number} Outlet State"),
                f"{prefix}{outlet_number:02d}",
                outlet_number,
            )
        )
    return cards


def outlet_detail_cards(entities: list[dict], entry_id: str, outlet_number: int) -> list[dict]:
    """Build the investigation cards for one outlet."""
    switch = entity_id(entities, entry_id, f"Outlet {outlet_number} Power")
    power = optional_entity_id(entities, entry_id, f"Outlet {outlet_number} Active Power")
    state = optional_entity_id(entities, entry_id, f"Outlet {outlet_number} Outlet State")
    waveform = optional_entity_id(entities, entry_id, f"Outlet {outlet_number} Inrush Waveform")
    entities_card = {
        "type": "entities",
        "title": f"{PDU_NAMES[entry_id]} - outlet {outlet_number}",
        "show_header_toggle": False,
        "entities": [entity for entity in (switch, state, power, waveform) if entity],
    }
    cards = [
        {
            "type": "custom:mushroom-template-card",
            "entity": switch,
            "primary": (
                "{{ state_attr(entity, 'configured_name') or "
                f"'Outlet {outlet_number}' }}}}"
            ),
            "secondary": (
                "{{ states(entity) | title }}  |  "
                "{{ state_attr(entity, 'device_label') or '-' }}  |  "
                "OCP {{ state_attr(entity, 'ocp_label') or '-' }} "
                "{{ state_attr(entity, 'ocp_rated_current_a') or '-' }} A"
            ),
            "icon": "mdi:power-socket-au",
            "icon_color": "{% if states(entity) == 'on' %}green{% elif states(entity) == 'off' %}red{% else %}grey{% endif %}",
            "tap_action": {"action": "more-info"},
            "hold_action": {"action": "toggle"},
        },
        entities_card,
    ]
    if power:
        cards.append(
            {
                "type": "custom:mini-graph-card",
                "name": f"{PDU_NAMES[entry_id]} outlet {outlet_number} active power",
                "icon": "mdi:flash",
                "hours_to_show": 24,
                "points_per_hour": 12,
                "line_width": 2,
                "show": {"labels": True},
                "entities": [power],
            }
        )
    if waveform:
        cards.append(
            {
                "type": "custom:raritan-waveform-card",
                "entity": waveform,
                "name": f"{PDU_NAMES[entry_id]} outlet {outlet_number} last inrush waveform",
            }
        )
    return cards


def entity_chunks(entities: list[dict], entry_id: str, chunk_size: int = 32) -> list[dict]:
    """Build readable entity-list cards containing the full sensor inventory."""
    sensors = entities_for(entities, entry_id, "sensor")
    cards = []
    for offset in range(0, len(sensors), chunk_size):
        chunk = sensors[offset : offset + chunk_size]
        cards.append(
            {
                "type": "entities",
                "title": f"{PDU_NAMES[entry_id]} sensors {offset + 1}-{offset + len(chunk)}",
                "show_header_toggle": False,
                "entities": [entity["entity_id"] for entity in chunk],
            }
        )
    return cards


def environmental_cards(entities: list[dict]) -> list[dict]:
    """Build environmental tiles where the simulated sensor set exposes them."""
    specs = [
        (PDU_A, "Temperature 1 Temperature", "PDU A rack temperature", "mdi:thermometer"),
        (PDU_A, "Relative Humidity 1 Humidity", "PDU A rack humidity", "mdi:water-percent"),
        (PDU_A, "Door State 1 Door State", "PDU A containment door", "mdi:door"),
        (PDU_B, "Temperature 1 Temperature", "PDU B rack temperature", "mdi:thermometer"),
        (PDU_B, "Relative Humidity 1 Humidity", "PDU B rack humidity", "mdi:water-percent"),
        (PDU_B, "Door State 1 Door State", "PDU B containment door", "mdi:door"),
    ]
    cards = []
    for entry_id, original_name, label, icon in specs:
        entity = optional_entity_id(entities, entry_id, original_name)
        if entity:
            cards.append(alarm_tile(entity, label, icon))
    return cards


def environmental_detail_cards(entities: list[dict]) -> list[dict]:
    """Build historical environmental panels with configured descriptions."""
    specs = [
        (PDU_A, "Temperature 1 Temperature", "PDU A rack temperature", "mdi:thermometer"),
        (PDU_A, "Relative Humidity 1 Humidity", "PDU A rack humidity", "mdi:water-percent"),
        (PDU_B, "Temperature 1 Temperature", "PDU B rack temperature", "mdi:thermometer"),
        (PDU_B, "Relative Humidity 1 Humidity", "PDU B rack humidity", "mdi:water-percent"),
    ]
    cards = []
    for entry_id, original_name, label, icon in specs:
        entity = optional_entity_id(entities, entry_id, original_name)
        if not entity:
            continue
        cards.extend(
            [
                {
                    "type": "custom:mushroom-template-card",
                    "entity": entity,
                    "primary": label,
                    "secondary": (
                        "{{ states(entity) }} {{ state_attr(entity, 'unit_of_measurement') or '' }}  |  "
                        "{{ state_attr(entity, 'sensor_description') or state_attr(entity, 'sensor_name') or 'No description' }}"
                    ),
                    "icon": icon,
                    "icon_color": (
                        "{% if states(entity) in ['unknown', 'unavailable'] %}grey"
                        "{% elif state_attr(entity, 'above_upper_critical') or state_attr(entity, 'below_lower_critical') %}red"
                        "{% elif state_attr(entity, 'above_upper_warning') or state_attr(entity, 'below_lower_warning') %}amber"
                        "{% else %}green{% endif %}"
                    ),
                    "tap_action": {"action": "more-info"},
                },
                {
                    "type": "custom:mini-graph-card",
                    "name": label,
                    "icon": icon,
                    "hours_to_show": 24,
                    "points_per_hour": 12,
                    "line_width": 2,
                    "show": {"labels": True},
                    "entities": [entity],
                },
            ]
        )
    return cards


def inlet_power_quality_cards(entities: list[dict], entry_id: str) -> list[dict]:
    """Build inlet power history and waveform cards."""
    voltage = entity_id(entities, entry_id, "Inlet 1 Voltage")
    current = entity_id(entities, entry_id, "Inlet 1 Current")
    power = entity_id(entities, entry_id, "Inlet 1 Active Power")
    cards = [
        {
            "type": "custom:mini-graph-card",
            "name": f"{PDU_NAMES[entry_id]} inlet power quality history",
            "icon": "mdi:sine-wave",
            "hours_to_show": 24,
            "points_per_hour": 12,
            "line_width": 2,
            "show": {"legend": True, "labels": True},
            "entities": [
                {"entity": voltage, "name": "Voltage"},
                {"entity": current, "name": "Current"},
                {"entity": power, "name": "Active power"},
            ],
        },
    ]
    for line in ("L1", "L2", "L3"):
        waveform = entity_id(entities, entry_id, f"Inlet 1 {line} Power Quality Waveform")
        capture = entity_id(entities, entry_id, f"Inlet 1 {line} Capture Power Quality Waveform")
        cards.extend(
            [
                {
                    "type": "button",
                    "entity": capture,
                    "name": f"Capture {line} waveform",
                    "icon": "mdi:sine-wave",
                    "show_state": False,
                    "tap_action": {"action": "toggle"},
                },
                {
                    "type": "custom:raritan-waveform-card",
                    "entity": waveform,
                    "name": f"{PDU_NAMES[entry_id]} {line} waveform",
                },
            ]
        )
    return cards


def section_cards(title: str, cards: list[dict], column_span: int = 1) -> dict:
    """Build a Home Assistant sections-layout section."""
    section = {
        "type": "grid",
        "cards": [
            {"type": "heading", "heading": title, "heading_style": "title"},
            *cards,
        ],
    }
    if column_span != 1:
        section["column_span"] = column_span
    return section


def replace_with_sections(view: dict, sections: list[dict], max_columns: int = 3) -> None:
    """Convert a masonry view to a sections view."""
    view.pop("cards", None)
    view["type"] = "sections"
    view["max_columns"] = max_columns
    view["sections"] = sections


def apply_sections_layout(dashboard: dict) -> None:
    """Group the generated dashboard cards into roomier Home Assistant sections."""
    views = dashboard["data"]["config"]["views"]
    by_path = {view["path"]: view for view in views}

    cards = by_path["overview"]["cards"]
    replace_with_sections(
        by_path["overview"],
        [
            section_cards("Rack status", [cards[0], cards[1], cards[5], cards[6]], 2),
            section_cards("Rack visual and access", [cards[8], cards[9], cards[10]], 2),
            section_cards("Cooling and power trend", [cards[12], cards[13]], 1),
            section_cards("Three-phase balance", [cards[3]], 2),
            section_cards("Breaker loading", [cards[15]], 2),
            section_cards("Environment", [cards[17]], 1),
            section_cards("Outlet mimic", [cards[19]], 3),
        ],
    )

    cards = by_path["rack-visual"]["cards"]
    replace_with_sections(
        by_path["rack-visual"],
        [
            section_cards("Rack door, alarms, and assets", [cards[0]], 3),
            section_cards("Access state", [cards[1], cards[2]], 2),
        ],
    )

    cards = by_path["outlet-loads"]["cards"]
    load_cards = cards[1]["cards"]
    replace_with_sections(
        by_path["outlet-loads"],
        [
            section_cards("PDU A load history", load_cards[0::2], 2),
            section_cards("PDU B load history", load_cards[1::2], 2),
        ],
    )

    cards = by_path["cooling"]["cards"]
    replace_with_sections(
        by_path["cooling"],
        [
            section_cards("Cooling containment", [cards[0]], 3),
            section_cards("Live telemetry", [cards[1]], 2),
            section_cards("Cooling trends", [cards[2]], 2),
            section_cards("Alarms and controls", [cards[3]], 2),
        ],
    )

    cards = by_path["rack-security"]["cards"]
    replace_with_sections(
        by_path["rack-security"],
        [
            section_cards("Door state and asset strip", [cards[1]], 3),
            section_cards("Security summary", [cards[2], cards[3]], 2),
            section_cards("Rules and recent events", [cards[4]], 2),
            section_cards("Maintenance actions", [cards[5]], 1),
        ],
    )

    cards = by_path["alarms"]["cards"]
    replace_with_sections(
        by_path["alarms"],
        [
            section_cards("Rack alarms", [cards[1], cards[2]], 2),
            section_cards("Alarm detail", [cards[3]], 2),
        ],
    )

    cards = by_path["outlet-controls"]["cards"]
    replace_with_sections(
        by_path["outlet-controls"],
        [section_cards("Outlet controls", [cards[0], cards[1]], 3)],
    )

    cards = by_path["outlet-detail"]["cards"]
    replace_with_sections(
        by_path["outlet-detail"],
        [section_cards("Outlet 1 inspection", [cards[1]], 3)],
    )

    cards = by_path["environment-detail"]["cards"]
    replace_with_sections(
        by_path["environment-detail"],
        [section_cards("Environmental sensor history", [cards[1]], 3)],
    )

    cards = by_path["power-quality"]["cards"]
    replace_with_sections(
        by_path["power-quality"],
        [section_cards("Power quality waveforms", [cards[1]], 3)],
    )

    for path, title in (("pdu-a-sensors", "PDU A sensor inventory"), ("pdu-b-sensors", "PDU B sensor inventory")):
        cards = by_path[path]["cards"]
        replace_with_sections(
            by_path[path],
            [section_cards(title, cards, 3)],
        )


def build_dashboard(entities: list[dict]) -> dict:
    """Build the complete storage-mode Lovelace dashboard."""
    pdu_a_power = entity_id(entities, PDU_A, "Inlet 1 Active Power")
    pdu_b_power = entity_id(entities, PDU_B, "Inlet 1 Active Power")
    dashboard = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace.rack_02",
        "data": {
            "config": {
                "title": "Rack 02",
                "views": [
                    {
                        "title": "Rack 02 Overview",
                        "path": "overview",
                        "icon": "mdi:server-rack",
                        "cards": [
                            {
                                "type": "markdown",
                                "content": (
                                    "# Rack 02 containment\n"
                                    "PX4-5730 paired feed. Hold an outlet tile to toggle power; "
                                    "tap it for details."
                                ),
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    pdu_summary_card(entities, PDU_A, "left rail"),
                                    pdu_summary_card(entities, PDU_B, "right rail"),
                                ],
                            },
                            {
                                "type": "markdown",
                                "content": "## Three-phase inlet balance",
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {
                                        "type": "vertical-stack",
                                        "cards": phase_balance_cards(entities, PDU_A),
                                    },
                                    {
                                        "type": "vertical-stack",
                                        "cards": phase_balance_cards(entities, PDU_B),
                                    },
                                ],
                            },
                            {
                                "type": "markdown",
                                "content": "## Alarm and threshold state",
                            },
                            rack_alarm_card(entities),
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    pdu_alarm_card(entities, PDU_A),
                                    pdu_alarm_card(entities, PDU_B),
                                ],
                            },
                            {
                                "type": "markdown",
                                "content": "## Rack access and smartlock",
                            },
                            rack_visual_card(entities),
                            rack_security_card(entities),
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    pdu_security_card(entities, PDU_A),
                                    pdu_security_card(entities, PDU_B),
                                ],
                            },
                            {
                                "type": "markdown",
                                "content": "## Cooling state",
                            },
                            cooling_health_card(),
                            {
                                "type": "custom:mini-graph-card",
                                "name": "Rack 02 inlet active power",
                                "icon": "mdi:flash",
                                "hours_to_show": 12,
                                "points_per_hour": 12,
                                "line_width": 2,
                                "show": {"legend": True, "labels": True},
                                "entities": [
                                    {"entity": pdu_a_power, "name": "PDU A"},
                                    {"entity": pdu_b_power, "name": "PDU B"},
                                ],
                            },
                            {
                                "type": "markdown",
                                "content": "## Breaker loading by phase",
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {
                                        "type": "vertical-stack",
                                        "cards": [
                                            {"type": "markdown", "content": "### PDU A breakers"},
                                            {
                                                "type": "grid",
                                                "columns": 3,
                                                "square": False,
                                                "cards": breaker_cards(entities, PDU_A),
                                            },
                                        ],
                                    },
                                    {
                                        "type": "vertical-stack",
                                        "cards": [
                                            {"type": "markdown", "content": "### PDU B breakers"},
                                            {
                                                "type": "grid",
                                                "columns": 3,
                                                "square": False,
                                                "cards": breaker_cards(entities, PDU_B),
                                            },
                                        ],
                                    },
                                ],
                            },
                            {
                                "type": "markdown",
                                "content": "## Environmental and containment state",
                            },
                            {
                                "type": "grid",
                                "columns": 3,
                                "square": False,
                                "cards": environmental_cards(entities),
                            },
                            {
                                "type": "markdown",
                                "content": (
                                    "## Outlet mimic\n"
                                    "Green is on, red is off, amber is reserved for a power-cycle "
                                    "transition, and gray is unavailable."
                                ),
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {
                                        "type": "vertical-stack",
                                        "cards": [
                                            {"type": "markdown", "content": "### PDU A - left rail"},
                                            {
                                                "type": "grid",
                                                "columns": 3,
                                                "square": False,
                                                "cards": outlet_cards(entities, PDU_A, "A"),
                                            },
                                        ],
                                    },
                                    {
                                        "type": "vertical-stack",
                                        "cards": [
                                            {"type": "markdown", "content": "### PDU B - right rail"},
                                            {
                                                "type": "grid",
                                                "columns": 3,
                                                "square": False,
                                                "cards": outlet_cards(entities, PDU_B, "B"),
                                            },
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Rack Visual",
                        "path": "rack-visual",
                        "icon": "mdi:server-security",
                        "cards": [
                            rack_visual_card(entities),
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    rack_alarm_card(entities),
                                    rack_security_card(entities),
                                ],
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    security_entities_card(entities, PDU_A),
                                    security_entities_card(entities, PDU_B),
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Outlet Loads",
                        "path": "outlet-loads",
                        "icon": "mdi:chart-timeline-variant",
                        "cards": [
                            {"type": "markdown", "content": "# Outlet load history and extrema"},
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": outlet_load_history_cards(entities),
                            },
                        ],
                    },
                    {
                        "title": "Cooling",
                        "path": "cooling",
                        "icon": "mdi:snowflake-thermometer",
                        "cards": [
                            cooling_visual_card(entities),
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    cooling_health_card(),
                                    {
                                        "type": "entities",
                                        "title": "RDHx live telemetry",
                                        "show_header_toggle": False,
                                        "entities": [
                                            "binary_sensor.usystems_rdhx_unit_on",
                                            "sensor.usystems_rdhx_air_off_coil_temperature",
                                            "sensor.usystems_rdhx_air_on_coil_temperature",
                                            "sensor.usystems_rdhx_cabinet_front_room_temperature",
                                            "sensor.usystems_rdhx_fan_2_command",
                                            "sensor.usystems_rdhx_fan_2_feedback_raw",
                                            "sensor.usystems_rdhx_valve_request",
                                            "sensor.usystems_rdhx_valve_feedback",
                                            "sensor.usystems_rdhx_return_water_tqs3_temperature_raw",
                                        ],
                                    },
                                ],
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": cooling_graph_cards(entities),
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    cooling_alarm_card(),
                                    cooling_controls_card(),
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Rack Security",
                        "path": "rack-security",
                        "icon": "mdi:shield-lock",
                        "cards": [
                            {"type": "markdown", "content": "# Rack 02 security"},
                            rack_visual_card(entities),
                            rack_security_card(entities),
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    pdu_security_card(entities, PDU_A),
                                    pdu_security_card(entities, PDU_B),
                                ],
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    security_entities_card(entities, PDU_A),
                                    security_entities_card(entities, PDU_B),
                                ],
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    card
                                    for card in (
                                        reset_extrema_card(entities, PDU_A),
                                        reset_extrema_card(entities, PDU_B),
                                    )
                                    if card
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Alarms",
                        "path": "alarms",
                        "icon": "mdi:alarm-light",
                        "cards": [
                            {"type": "markdown", "content": "# Rack 02 alarms"},
                            rack_alarm_card(entities),
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    pdu_alarm_card(entities, PDU_A),
                                    pdu_alarm_card(entities, PDU_B),
                                ],
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    alarm_entities_card(entities, PDU_A),
                                    alarm_entities_card(entities, PDU_B),
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Outlet Controls",
                        "path": "outlet-controls",
                        "icon": "mdi:power-socket-au",
                        "cards": [
                            {
                                "type": "markdown",
                                "content": (
                                    "# Rack 02 outlet controls\n"
                                    "Tap for state details. Hold to toggle the selected outlet."
                                ),
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {
                                        "type": "vertical-stack",
                                        "cards": [
                                            {"type": "markdown", "content": "## PDU A"},
                                            *outlet_cards(entities, PDU_A, "A"),
                                        ],
                                    },
                                    {
                                        "type": "vertical-stack",
                                        "cards": [
                                            {"type": "markdown", "content": "## PDU B"},
                                            *outlet_cards(entities, PDU_B, "B"),
                                        ],
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Outlet Detail",
                        "path": "outlet-detail",
                        "icon": "mdi:power-socket-au",
                        "cards": [
                            {"type": "markdown", "content": "# Outlet 1 inspection"},
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {"type": "vertical-stack", "cards": outlet_detail_cards(entities, PDU_A, 1)},
                                    {"type": "vertical-stack", "cards": outlet_detail_cards(entities, PDU_B, 1)},
                                ],
                            },
                        ],
                    },
                    {
                        "title": "Environment Detail",
                        "path": "environment-detail",
                        "icon": "mdi:thermometer-lines",
                        "cards": [
                            {"type": "markdown", "content": "# Environmental sensor history"},
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": environmental_detail_cards(entities),
                            },
                        ],
                    },
                    {
                        "title": "Power Quality",
                        "path": "power-quality",
                        "icon": "mdi:sine-wave",
                        "cards": [
                            {"type": "markdown", "content": "# Rack 02 power quality"},
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {"type": "vertical-stack", "cards": inlet_power_quality_cards(entities, PDU_A)},
                                    {"type": "vertical-stack", "cards": inlet_power_quality_cards(entities, PDU_B)},
                                ],
                            },
                        ],
                    },
                    {
                        "title": "PDU A Sensors",
                        "path": "pdu-a-sensors",
                        "icon": "mdi:chart-box-outline",
                        "cards": entity_chunks(entities, PDU_A),
                    },
                    {
                        "title": "PDU B Sensors",
                        "path": "pdu-b-sensors",
                        "icon": "mdi:chart-box-outline",
                        "cards": entity_chunks(entities, PDU_B),
                    },
                ],
            }
        },
    }
    apply_sections_layout(dashboard)
    return dashboard


def build_dashboard_registry() -> dict:
    """Add the Rack 02 dashboard entry without replacing existing entries."""
    dashboards = json.loads(DASHBOARDS_PATH.read_text())
    items = dashboards["data"]["items"]
    if not any(item["id"] == "rack_02" for item in items):
        items.append(
            {
                "id": "rack_02",
                "icon": "mdi:server-rack",
                "title": "Rack 02",
                "url_path": "rack-02",
                "require_admin": False,
                "mode": "storage",
                "show_in_sidebar": True,
            }
        )
    return dashboards


def main() -> None:
    """Write generated dashboard storage files."""
    entities = load_entities()
    dashboard = build_dashboard(entities)
    dashboards = build_dashboard_registry()
    OUTPUT_DASHBOARD.write_text(json.dumps(dashboard, indent=2) + "\n")
    OUTPUT_DASHBOARDS.write_text(json.dumps(dashboards, indent=2) + "\n")
    print(f"Wrote {OUTPUT_DASHBOARD} with {len(entities)} PX4 entities")
    print(f"Wrote {OUTPUT_DASHBOARDS}")


if __name__ == "__main__":
    main()
