"""Small synchronous client wrapper around the official Raritan SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
import re
import socket
from threading import RLock
from time import monotonic

import requests
from raritan import rpc
from raritan.rpc.BulkRequestHelper import perform_bulk
from raritan.rpc import assetmgrmodel, event, pdumodel, sensors

try:
    from raritan.rpc import peripheral
except ImportError:
    peripheral = None

try:
    from raritan.rpc import cascading
except ImportError:
    cascading = None

try:
    from raritan.rpc import smartcard, smartlock
except ImportError:
    smartcard = None
    smartlock = None

try:
    from raritan.rpc import devsettings, net, security
except ImportError:
    devsettings = None
    net = None
    security = None

from .prometheus import PrometheusCollector
from .redfish import RedfishClient
from .xerus_modbus import XerusModbusClient
from .const import DEFAULT_MODBUS_PORT, DEFAULT_MODBUS_SLAVE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

BULK_CHUNK_SIZE = 100
METADATA_REFRESH_INTERVAL = 300
MINMAX_REFRESH_INTERVAL = 300
WAVEFORM_REFRESH_INTERVAL = 300
SERVICE_STATUS_REFRESH_INTERVAL = 300

BASIC_FIELDS = {
    "activeEnergy",
    "activePower",
    "apparentPower",
    "current",
    "lineFrequency",
    "outletState",
    "powerFactor",
    "state",
    "unbalancedCurrent",
    "unbalancedLineLineCurrent",
    "unbalancedLineLineVoltage",
    "unbalancedVoltage",
    "voltage",
    "voltageLN",
}

POWER_SKIP_FIELDS = {
    "crestFactor",
    "currentThd",
    "inrushCurrent",
    "maximumCurrent",
    "peakCurrent",
    "phaseAngle",
    "voltageThd",
}

SENSOR_TYPE_NAMES = {
    sensors.Sensor.UNSPECIFIED: "UNSPECIFIED",
    sensors.Sensor.VOLTAGE: "VOLTAGE",
    sensors.Sensor.CURRENT: "CURRENT",
    sensors.Sensor.UNBALANCE_CURRENT: "UNBALANCE_CURRENT",
    sensors.Sensor.POWER: "POWER",
    sensors.Sensor.POWER_FACTOR: "POWER_FACTOR",
    sensors.Sensor.ENERGY: "ENERGY",
    sensors.Sensor.FREQUENCY: "FREQUENCY",
    sensors.Sensor.TEMPERATURE: "TEMPERATURE",
    sensors.Sensor.HUMIDITY: "HUMIDITY",
    sensors.Sensor.AIR_FLOW: "AIR_FLOW",
    sensors.Sensor.AIR_PRESSURE: "AIR_PRESSURE",
    sensors.Sensor.CONTACT_CLOSURE: "CONTACT_CLOSURE",
    sensors.Sensor.ON_OFF_SENSOR: "ON_OFF_SENSOR",
    sensors.Sensor.TRIP_SENSOR: "TRIP_SENSOR",
    sensors.Sensor.VIBRATION: "VIBRATION",
    sensors.Sensor.WATER_LEAK: "WATER_LEAK",
    sensors.Sensor.SMOKE_DETECTOR: "SMOKE_DETECTOR",
    sensors.Sensor.TOTAL_HARMONIC_DISTORTION: "TOTAL_HARMONIC_DISTORTION",
    sensors.Sensor.MASS: "MASS",
    sensors.Sensor.ELECTRICAL_RESISTANCE: "ELECTRICAL_RESISTANCE",
    sensors.Sensor.FLUX: "FLUX",
    sensors.Sensor.LUMINOUS_INTENSITY: "LUMINOUS_INTENSITY",
    sensors.Sensor.ACCELERATION: "ACCELERATION",
    sensors.Sensor.MAGNETIC_FLUX_DENSITY: "MAGNETIC_FLUX_DENSITY",
    sensors.Sensor.ELECTRIC_FIELD_STRENGTH: "ELECTRIC_FIELD_STRENGTH",
    sensors.Sensor.MAGNETIC_FIELD_STRENGTH: "MAGNETIC_FIELD_STRENGTH",
    sensors.Sensor.ANGLE: "ANGLE",
    sensors.Sensor.SELECTION: "SELECTION",
    sensors.Sensor.FAULT_STATE: "FAULT_STATE",
    sensors.Sensor.POWER_QUALITY: "POWER_QUALITY",
    sensors.Sensor.ROTATIONAL_SPEED: "ROTATIONAL_SPEED",
    sensors.Sensor.LUMINOUS_ENERGY: "LUMINOUS_ENERGY",
    sensors.Sensor.LUMINOUS_FLUX: "LUMINOUS_FLUX",
    sensors.Sensor.ILLUMINANCE: "ILLUMINANCE",
    sensors.Sensor.LUMINOUS_EMITTANCE: "LUMINOUS_EMITTANCE",
    sensors.Sensor.MOTION: "MOTION",
    sensors.Sensor.OCCUPANCY: "OCCUPANCY",
    sensors.Sensor.TAMPER: "TAMPER",
    sensors.Sensor.DRY_CONTACT: "DRY_CONTACT",
    sensors.Sensor.POWERED_DRY_CONTACT: "POWERED_DRY_CONTACT",
    sensors.Sensor.ABSOLUTE_HUMIDITY: "ABSOLUTE_HUMIDITY",
    sensors.Sensor.DOOR_STATE: "DOOR_STATE",
    sensors.Sensor.DOOR_LOCK_STATE: "DOOR_LOCK_STATE",
    sensors.Sensor.DOOR_HANDLE_LOCK: "DOOR_HANDLE_LOCK",
    sensors.Sensor.CREST_FACTOR: "CREST_FACTOR",
    sensors.Sensor.DISTANCE: "DISTANCE",
    sensors.Sensor.LENGTH: "LENGTH",
    sensors.Sensor.UNBALANCE_VOLTAGE: "UNBALANCE_VOLTAGE",
    sensors.Sensor.PARTICLE_DENSITY: "PARTICLE_DENSITY",
    sensors.Sensor.DEW_POINT: "DEW_POINT",
    sensors.Sensor.ELECTRICAL_IMPEDANCE: "ELECTRICAL_IMPEDANCE",
    sensors.Sensor.TS_BYPASS_STATE: "TS_BYPASS_STATE",
    sensors.Sensor.BATTERY_LEVEL: "BATTERY_LEVEL",
}

UNIT_NAMES = {
    sensors.Sensor.NONE: "NONE",
    sensors.Sensor.VOLT: "VOLT",
    sensors.Sensor.AMPERE: "AMPERE",
    sensors.Sensor.WATT: "WATT",
    sensors.Sensor.VOLT_AMP: "VOLT_AMP",
    sensors.Sensor.WATT_HOUR: "WATT_HOUR",
    sensors.Sensor.VOLT_AMP_HOUR: "VOLT_AMP_HOUR",
    sensors.Sensor.DEGREE_CELSIUS: "DEGREE_CELSIUS",
    sensors.Sensor.HZ: "HZ",
    sensors.Sensor.PERCENT: "PERCENT",
    sensors.Sensor.METER_PER_SEC: "METER_PER_SEC",
    sensors.Sensor.PASCAL: "PASCAL",
    sensors.Sensor.G: "G",
    sensors.Sensor.RPM: "RPM",
    sensors.Sensor.METER: "METER",
    sensors.Sensor.HOUR: "HOUR",
    sensors.Sensor.MINUTE: "MINUTE",
    sensors.Sensor.SECOND: "SECOND",
    sensors.Sensor.VOLT_AMP_REACTIVE: "VOLT_AMP_REACTIVE",
    sensors.Sensor.VOLT_AMP_REACTIVE_HOUR: "VOLT_AMP_REACTIVE_HOUR",
    sensors.Sensor.GRAM: "GRAM",
    sensors.Sensor.OHM: "OHM",
    sensors.Sensor.LITERS_PER_HOUR: "LITERS_PER_HOUR",
    sensors.Sensor.CANDELA: "CANDELA",
    sensors.Sensor.METER_PER_SQUARE_SEC: "METER_PER_SQUARE_SEC",
    sensors.Sensor.TESLA: "TESLA",
    sensors.Sensor.VOLT_PER_METER: "VOLT_PER_METER",
    sensors.Sensor.VOLT_PER_AMPERE: "VOLT_PER_AMPERE",
    sensors.Sensor.DEGREE: "DEGREE",
    sensors.Sensor.DEGREE_FAHRENHEIT: "DEGREE_FAHRENHEIT",
    sensors.Sensor.KELVIN: "KELVIN",
    sensors.Sensor.JOULE: "JOULE",
    sensors.Sensor.COULOMB: "COULOMB",
    sensors.Sensor.NIT: "NIT",
    sensors.Sensor.LUMEN: "LUMEN",
    sensors.Sensor.LUMEN_SECOND: "LUMEN_SECOND",
    sensors.Sensor.LUX: "LUX",
    sensors.Sensor.PSI: "PSI",
    sensors.Sensor.NEWTON: "NEWTON",
    sensors.Sensor.FOOT: "FOOT",
}


class RaritanError(Exception):
    """Raritan integration error."""


class SensorKind(Enum):
    """Sensor kind."""

    NUMERIC = "numeric"
    STATE = "state"
    ASSET_LOG = "asset_log"
    ASSET_INVENTORY = "asset_inventory"
    ALARM_SUMMARY = "alarm_summary"
    SECURITY = "security"
    WAVEFORM = "waveform"
    INVENTORY = "inventory"
    SERVICE_STATUS = "service_status"
    CONFIG_SNAPSHOT = "config_snapshot"


@dataclass(frozen=True)
class SensorDescriptor:
    """Discovered sensor description."""

    key: str
    name: str
    context: str
    target: str
    kind: SensorKind
    field: str | None = None
    type_name: str | None = None
    unit_name: str | None = None
    asset_field: str | None = None
    attributes: dict | None = None
    device_info: dict | None = None


class RaritanClient:
    """Xerus JSON-RPC client backed by the official Raritan SDK."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
        profile: str = "basic",
        device_identifier: str | None = None,
        modbus_port: int = DEFAULT_MODBUS_PORT,
        modbus_slave_id: int = DEFAULT_MODBUS_SLAVE_ID,
        rack_name: str | None = None,
        rack_role: str | None = None,
        rack_position: str | None = None,
        mqtt_datapush_config: dict | None = None,
    ):
        """Initialize the client."""
        self.host = host
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.profile = profile
        self.device_identifier = device_identifier
        self.rack_name = rack_name
        self.rack_role = rack_role
        self.rack_position = rack_position
        self.mqtt_datapush_config = mqtt_datapush_config or {}
        self.agent = None
        self.pdu = None
        self.cascade_manager = None
        self.outlet_group_manager = None
        self.asset_logger = None
        self.alerted_sensor_manager = None
        self.alarm_manager = None
        self.prometheus = PrometheusCollector(host, username, password, verify_ssl)
        self.redfish = RedfishClient(host, username, password, verify_ssl)
        self.modbus = XerusModbusClient(host, modbus_port, modbus_slave_id)
        self._lock = RLock()
        self.sensor_descriptors: list[SensorDescriptor] = []
        self._descriptors_by_key: dict[str, SensorDescriptor] = {}
        self._sensors_by_key = {}
        self._controllable_state_switches = {}
        self._metadata = {}
        self._waveform_sources = {}
        self._waveform_cache = {}
        self._last_waveform_refresh = 0.0
        self._minmax_cache = {}
        self._last_minmax_refresh = 0.0
        self._security_interfaces = {}
        self._security_state_last = {}
        self._security_events = []
        self._mqtt_events = []
        self._mqtt_event_count = 0
        self._mqtt_datapush_status = {"enabled": bool(self.mqtt_datapush_config.get("enabled"))}
        self._service_status_cache = None
        self._last_service_status_refresh = 0.0
        self._config_snapshot_cache = None
        self._last_config_snapshot_refresh = 0.0
        self._link_statuses = {}
        self._asset_strips = {}
        self._asset_strip_selected_targets = {}
        self._asset_strip_probe_errors = {}
        self._external_sensor_inventory_by_pdu = {}
        self._outlet_state_devices_by_key = {}
        self._outlet_details = {}
        self._ocp_details = {}
        self._poles_by_target = {}
        self._last_discovery = 0.0

    @property
    def device_info(self):
        """Return Home Assistant device info."""
        return self._device_info_for_metadata(self._metadata, 0)

    @property
    def rack_device_info(self):
        """Return Home Assistant device info for the rack/PDU Link parent."""
        rack_name = self.rack_name or self._metadata.get("name") or f"Rack {self.host}"
        master_name = self._metadata.get("name") or self.host
        model = "LDCS Rack"
        if self._link_statuses:
            model = f"PDU Link Master: {master_name}"
        return {
            "identifiers": {(DOMAIN, self._rack_device_identifier())},
            "manufacturer": "Legrand Data Center Solutions",
            "model": model,
            "name": rack_name,
            "configuration_url": f"https://{self.host}",
        }

    def _device_info_for_metadata(self, metadata, link_id=0):
        """Return Home Assistant device info for the primary or a linked PDU."""
        serial = metadata.get("serial_number") or f"{self.host}-link-{link_id}"
        if link_id in (0, 1):
            identifier = self.device_identifier or serial or self.host
            name = metadata.get("name") or metadata.get("model") or f"Xerus device {self.host}"
        else:
            identifier = serial or f"{self.device_identifier or self.host}-link-{link_id}"
            name = metadata.get("name") or metadata.get("model") or f"Linked Xerus PDU {link_id}"
        device_info = {
            "identifiers": {(DOMAIN, identifier)},
            "manufacturer": metadata.get("manufacturer") or "Legrand",
            "model": metadata.get("model"),
            "name": name,
            "sw_version": metadata.get("fw_revision"),
            "configuration_url": f"https://{self.host}",
        }
        if self._has_rack_parent():
            device_info["via_device"] = (DOMAIN, self._rack_device_identifier())
        return device_info

    def _rack_device_identifier(self):
        """Return the stable identifier for the rack parent device."""
        rack_key = self.rack_name or self.device_identifier or self.host
        return f"rack_{_slug(rack_key)}"

    def _has_rack_parent(self):
        """Return true when entities should be grouped under a rack parent."""
        return bool(self.rack_name) or bool(self._link_statuses)

    def _rack_or_device_info(self):
        """Return rack device info when a rack parent is available."""
        return self.rack_device_info if self._has_rack_parent() else self.device_info

    @property
    def mqtt_topic(self):
        """Return the dedicated MQTT topic wildcard for this PDU."""
        prefix = _mqtt_topic_prefix(self.mqtt_datapush_config.get("topic_prefix"))
        if not prefix and self.mqtt_datapush_enabled:
            prefix = self._default_mqtt_topic_prefix()
        if prefix:
            return f"{prefix}#"
        return f"raritan/{_slug(self.host)}/#"

    @property
    def mqtt_datapush_enabled(self):
        """Return whether the integration should manage Xerus MQTT Data Push."""
        return bool(self.mqtt_datapush_config.get("enabled") and self.mqtt_datapush_config.get("host"))

    def note_mqtt_message(self, topic, payload):
        """Track a recent MQTT Data Push message and wake-up trigger."""
        with self._lock:
            self._mqtt_event_count += 1
            event_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "topic": topic,
                "payload_type": type(payload).__name__,
                "summary": _mqtt_payload_summary(payload),
            }
            self._mqtt_events.insert(0, event_record)
            self._mqtt_events = self._mqtt_events[:40]
            self._mqtt_datapush_status = {
                **self._mqtt_datapush_status,
                "enabled": bool(self.mqtt_datapush_config.get("enabled")),
                "last_message_time": event_record["timestamp"],
                "last_topic": topic,
                "message_count": self._mqtt_event_count,
            }

    def ensure_mqtt_datapush(self):
        """Create or update managed Xerus MQTT Data Push entries."""
        with self._lock:
            self.connect()
            if not self.mqtt_datapush_enabled:
                self._mqtt_datapush_status = {
                    "enabled": bool(self.mqtt_datapush_config.get("enabled")),
                    "configured": False,
                    "error": "MQTT Data Push is disabled or broker host is empty",
                }
                return self._mqtt_datapush_status
            service = event.DataPushService("/datapush", self.agent)
            entries = service.listEntries()
            created = []
            modified = []
            errors = []
            for entry_type, suffix in (
                (event.DataPushService.EntryType.SENSORLOG, "sensorlog"),
                (event.DataPushService.EntryType.AUDITLOG, "auditlog"),
                (event.DataPushService.EntryType.AMSLOG, "assetlog"),
            ):
                settings = self._mqtt_entry_settings(entry_type, suffix)
                entry_id = _matching_datapush_entry_id(entries, settings)
                try:
                    if entry_id is None:
                        ret, new_entry_id = service.addEntry(settings)
                        if ret == 0:
                            created.append(int(new_entry_id))
                        else:
                            errors.append(f"add {suffix}: return {ret}")
                    else:
                        ret = service.modifyEntry(int(entry_id), settings)
                        if ret == 0:
                            modified.append(int(entry_id))
                        else:
                            errors.append(f"modify {suffix} {entry_id}: return {ret}")
                except Exception as err:  # noqa: BLE001
                    errors.append(f"{suffix}: {err}")
            self._mqtt_datapush_status = {
                "enabled": True,
                "configured": not errors,
                "broker": _redact_url(self._mqtt_broker_url()),
                "topic_prefix": _mqtt_topic_prefix(self.mqtt_datapush_config.get("topic_prefix")) or self._default_mqtt_topic_prefix(),
                "created_entry_ids": created,
                "modified_entry_ids": modified,
                "errors": errors,
                "rule_strategy": "MQTT push entries managed; JSON-RPC polling remains authoritative after each MQTT wake-up.",
                "last_configured": datetime.now(timezone.utc).isoformat(),
            }
            return self._mqtt_datapush_status

    def _mqtt_entry_settings(self, entry_type, suffix):
        """Build one Data Push entry settings object for MQTT."""
        topic_prefix = _mqtt_topic_prefix(self.mqtt_datapush_config.get("topic_prefix")) or self._default_mqtt_topic_prefix()
        return event.DataPushService.EntrySettings(
            url=self._mqtt_broker_url(),
            allowOffTimeRangeCerts=not bool(self.mqtt_datapush_config.get("tls")),
            useAuth=bool(self.mqtt_datapush_config.get("username")),
            username=str(self.mqtt_datapush_config.get("username") or ""),
            password=str(self.mqtt_datapush_config.get("password") or ""),
            type=entry_type,
            items=[],
            mqttSettings=event.DataPushService.MqttSettings(
                topicPrefix=f"{topic_prefix}{suffix}/",
            ),
        )

    def _mqtt_broker_url(self):
        """Return the broker URL expected by Xerus Data Push."""
        scheme = "mqtts" if self.mqtt_datapush_config.get("tls") else "mqtt"
        host = str(self.mqtt_datapush_config.get("host") or "").strip()
        port = int(self.mqtt_datapush_config.get("port") or (8883 if scheme == "mqtts" else 1883))
        return f"{scheme}://{host}:{port}"

    def _default_mqtt_topic_prefix(self):
        """Return the managed topic prefix for this PDU."""
        rack = _slug(self.rack_name or "rack")
        return f"ldcs/xerus/{rack}/{_slug(self.host)}/"

    def connect(self):
        """Create SDK agent and PDU proxy."""
        if self.agent is None:
            self.agent = rpc.Agent(
                "https",
                self.host,
                self.username,
                self.password,
                disable_certificate_verification=not self.verify_ssl,
                timeout=10,
            )
            self.pdu = pdumodel.Pdu("/model/pdu/0", self.agent)
            self.cascade_manager = (
                cascading.CascadeManager("/cascade", self.agent) if cascading is not None else None
            )
            self.outlet_group_manager = pdumodel.OutletGroupManager("/model/outletgroup", self.agent)
            self.asset_logger = assetmgrmodel.AssetStripLogger("/model/assetstriplogger", self.agent)
            self.alerted_sensor_manager = sensors.AlertedSensorManager(
                "/model/alertedsensormanager", self.agent
            )
            self.alarm_manager = event.AlarmManager("/event_engine/alarms", self.agent)

    def test_connection(self):
        """Test login and return simple metadata."""
        with self._lock:
            self.connect()
            try:
                self._metadata = self._read_pdu_metadata(self.pdu)
            except Exception as err:  # noqa: BLE001 - SDK raises several exception types.
                raise RaritanError(f"Unable to connect to Xerus device {self.host}: {err}") from err
            return self._metadata

    def discover(self):
        """Discover sensors exposed by the PDU."""
        with self._lock:
            self.connect()
            try:
                self._metadata = self._read_pdu_metadata(self.pdu)
                descriptors = []
                self._sensors_by_key = {}
                self._controllable_state_switches = {}
                self._waveform_sources = {}
                self._asset_strips = {}
                self._asset_strip_selected_targets = {}
                self._asset_strip_probe_errors = {}
                self._external_sensor_inventory_by_pdu = {}
                self._outlet_state_devices_by_key = {}
                self._outlet_details = {}
                self._ocp_details = {}
                self._poles_by_target = {}
                self._link_statuses = self._link_unit_statuses()
                self._collect_pdu(descriptors, self.pdu, 0, self.device_info)
                for link_id, link_pdu, link_metadata, link_status in self._linked_pdus():
                    self._collect_pdu(
                        descriptors,
                        link_pdu,
                        link_id,
                        self._device_info_for_metadata(link_metadata, link_id),
                        {
                            "pdu_link_id": link_id,
                            "pdu_link_role": "link_unit",
                            "pdu_link_status": link_status,
                        },
                    )
                self._collect_outlet_groups(descriptors)
                self._collect_asset_logger(descriptors)
                self._collect_alarm_summary(descriptors)
                self._collect_security_summary(descriptors)
                self._collect_service_status(descriptors)
                self._collect_config_snapshot(descriptors)
                self._collect_modbus_inventory(descriptors)
                self.sensor_descriptors = descriptors
                self._descriptors_by_key = {descriptor.key: descriptor for descriptor in descriptors}
                self._last_discovery = monotonic()
            except Exception as err:  # noqa: BLE001
                raise RaritanError(f"Unable to discover sensors on {self.host}: {err}") from err

    def update(self):
        """Read all discovered sensor values."""
        with self._lock:
            return self._update_locked()

    def _update_locked(self):
        """Read all discovered sensor values while holding the client lock."""
        if not self.sensor_descriptors or monotonic() - self._last_discovery >= METADATA_REFRESH_INTERVAL:
            self.discover()

        data = {}
        asset_descriptors = []
        asset_inventory_descriptors = []
        alarm_descriptors = []
        security_descriptors = []
        waveform_descriptors = []
        inventory_descriptors = []
        service_descriptors = []
        config_descriptors = []
        sensor_requests = []
        sensor_descriptors = []
        prometheus_samples = {}
        try:
            prometheus_samples = self.prometheus.read()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read Prometheus feed on %s: %s", self.host, err)

        for descriptor in self.sensor_descriptors:
            if descriptor.kind == SensorKind.ASSET_LOG:
                asset_descriptors.append(descriptor)
                continue
            if descriptor.kind == SensorKind.ASSET_INVENTORY:
                asset_inventory_descriptors.append(descriptor)
                continue
            if descriptor.kind == SensorKind.ALARM_SUMMARY:
                alarm_descriptors.append(descriptor)
                continue
            if descriptor.kind == SensorKind.SECURITY:
                security_descriptors.append(descriptor)
                continue
            if descriptor.kind == SensorKind.WAVEFORM:
                waveform_descriptors.append(descriptor)
                continue
            if descriptor.kind == SensorKind.INVENTORY:
                inventory_descriptors.append(descriptor)
                continue
            if descriptor.kind == SensorKind.SERVICE_STATUS:
                service_descriptors.append(descriptor)
                continue
            if descriptor.kind == SensorKind.CONFIG_SNAPSHOT:
                config_descriptors.append(descriptor)
                continue
            sensor = self._sensors_by_key.get(descriptor.key)
            prometheus_sample = (
                self.prometheus.value_for_descriptor(prometheus_samples, descriptor)
                if _is_primary_descriptor(descriptor)
                else None
            )
            if prometheus_sample is not None and not _requires_state_label(descriptor):
                data[descriptor.key] = {
                    "available": prometheus_sample["available"],
                    "value": prometheus_sample["value"],
                    "attributes": {
                        "telemetry_source": "prometheus",
                        "prometheus_labels": prometheus_sample["labels"],
                    },
                }
                continue
            if sensor is None:
                continue
            outlet = self._outlet_state_devices_by_key.get(descriptor.key)
            if outlet is not None:
                method = outlet.getState
            else:
                method = sensor.getReading if descriptor.kind == SensorKind.NUMERIC else sensor.getState
            sensor_requests.append((method, []))
            sensor_descriptors.append(descriptor)

        for offset in range(0, len(sensor_requests), BULK_CHUNK_SIZE):
            chunk_requests = sensor_requests[offset : offset + BULK_CHUNK_SIZE]
            chunk_descriptors = sensor_descriptors[offset : offset + BULK_CHUNK_SIZE]
            try:
                responses = perform_bulk(self.agent, chunk_requests)
            except Exception as err:  # noqa: BLE001
                for descriptor in chunk_descriptors:
                    data[descriptor.key] = _error_value(err)
                continue

            for descriptor, response in zip(chunk_descriptors, responses):
                if isinstance(response, Exception):
                    data[descriptor.key] = _error_value(response)
                    continue
                if descriptor.kind == SensorKind.NUMERIC:
                    reading = response
                    data[descriptor.key] = {
                        "available": bool(reading.available and reading.valid),
                        "value": reading.value if reading.available and reading.valid else None,
                        "attributes": {
                            **_reading_status_attrs(reading),
                            "telemetry_source": "json_rpc",
                        },
                    }
                else:
                    state = response
                    if _is_outlet_state_descriptor(descriptor):
                        data[descriptor.key] = _outlet_state_value(state)
                    elif _is_contact_state_descriptor(descriptor):
                        data[descriptor.key] = _binary_state_value(state, "contact")
                    elif _is_ocp_trip_descriptor(descriptor):
                        data[descriptor.key] = _ocp_trip_state_value(state)
                    elif _is_rack_door_state_descriptor(descriptor):
                        data[descriptor.key] = _rack_security_state_value(state, descriptor.type_name)
                    else:
                        data[descriptor.key] = {
                            "available": bool(state.available),
                            "value": state.value if state.available else None,
                            "attributes": {"telemetry_source": "json_rpc"},
                        }

        self._refresh_minmax_cache()
        for descriptor in self.sensor_descriptors:
            if descriptor.kind != SensorKind.NUMERIC:
                continue
            value = data.get(descriptor.key)
            if value is not None:
                value.setdefault("attributes", {}).update(self._minmax_cache.get(descriptor.key, {}))

        if asset_descriptors:
            try:
                asset_log_info = self.asset_logger.getInfo()
            except Exception as err:  # noqa: BLE001
                for descriptor in asset_descriptors:
                    data[descriptor.key] = _error_value(err)
            else:
                for descriptor in asset_descriptors:
                    data[descriptor.key] = {
                        "available": True,
                        "value": getattr(asset_log_info, descriptor.asset_field),
                        "attributes": {"telemetry_source": "json_rpc"},
                    }

        if asset_inventory_descriptors:
            for descriptor in asset_inventory_descriptors:
                data[descriptor.key] = self._asset_inventory_value(descriptor)

        if alarm_descriptors:
            data.update(self._read_alarm_summary(alarm_descriptors))

        self._track_security_state_events(data)

        if security_descriptors:
            data.update(self._read_security_summary(security_descriptors))

        if waveform_descriptors:
            data.update(self._read_waveforms(waveform_descriptors))

        if inventory_descriptors:
            data.update(self._read_inventory(inventory_descriptors))

        if service_descriptors:
            data.update(self._read_service_status(service_descriptors))

        if config_descriptors:
            data.update(self._read_config_snapshot(config_descriptors))

        for outlet_id, sample in self.prometheus.outlet_states(prometheus_samples).items():
            data[self.outlet_state_key(outlet_id)] = {
                "available": sample["available"],
                "value": sample["value"],
                "attributes": {
                    "telemetry_source": "prometheus",
                    "prometheus_labels": sample["labels"],
                },
            }
        return data

    def _refresh_minmax_cache(self):
        """Refresh slowly changing PDU-maintained extrema in bulk."""
        now = monotonic()
        if self._minmax_cache and now - self._last_minmax_refresh < MINMAX_REFRESH_INTERVAL:
            return

        requests = []
        descriptors = []
        for descriptor in self.sensor_descriptors:
            sensor = self._sensors_by_key.get(descriptor.key)
            if descriptor.kind == SensorKind.NUMERIC and sensor is not None:
                requests.append((sensor.getMinMax, []))
                descriptors.append(descriptor)

        for offset in range(0, len(requests), BULK_CHUNK_SIZE):
            chunk_requests = requests[offset : offset + BULK_CHUNK_SIZE]
            chunk_descriptors = descriptors[offset : offset + BULK_CHUNK_SIZE]
            try:
                responses = perform_bulk(self.agent, chunk_requests)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to read numeric extrema on %s: %s", self.host, err)
                continue

            for descriptor, response in zip(chunk_descriptors, responses):
                if isinstance(response, Exception):
                    self._minmax_cache[descriptor.key] = _minmax_error_attrs(response)
                else:
                    self._minmax_cache[descriptor.key] = _minmax_attrs(response)
        self._last_minmax_refresh = now

    def reset_all_minmax(self):
        """Reset PDU-maintained minimum and maximum readings for all numeric sensors."""
        with self._lock:
            return self._reset_all_minmax_locked()

    def _reset_all_minmax_locked(self):
        """Reset PDU-maintained extrema while holding the client lock."""
        if not self.sensor_descriptors:
            self.discover()

        requests = []
        descriptors = []
        for descriptor in self.sensor_descriptors:
            sensor = self._sensors_by_key.get(descriptor.key)
            if descriptor.kind == SensorKind.NUMERIC and sensor is not None:
                requests.append((sensor.resetMinMax, []))
                descriptors.append(descriptor)

        failures = []
        for offset in range(0, len(requests), BULK_CHUNK_SIZE):
            chunk_requests = requests[offset : offset + BULK_CHUNK_SIZE]
            chunk_descriptors = descriptors[offset : offset + BULK_CHUNK_SIZE]
            try:
                responses = perform_bulk(self.agent, chunk_requests)
            except Exception as err:  # noqa: BLE001
                failures.append(str(err))
                continue

            for descriptor, response in zip(chunk_descriptors, responses):
                if isinstance(response, Exception):
                    failures.append(f"{descriptor.name}: {response}")

        self._minmax_cache = {}
        self._last_minmax_refresh = 0.0
        self._refresh_minmax_cache()
        if failures:
            raise RaritanError(f"Unable to reset extrema for {len(failures)} sensors on {self.host}: {failures[0]}")
        return len(requests)

    def descriptor_for_key(self, key):
        """Return the latest discovered descriptor for an entity key."""
        return self._descriptors_by_key.get(key)

    def discover_redfish_outlets(self):
        """Discover outlets that Redfish allows Home Assistant to switch."""
        with self._lock:
            try:
                return self.redfish.discover_outlets()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to discover Redfish outlets on %s: %s", self.host, err)
                return []

    def set_redfish_outlet_power(self, target, state):
        """Set outlet power using Redfish."""
        with self._lock:
            self.redfish.set_outlet_power(target, state)

    def outlet_state_key(self, outlet_id):
        """Return coordinator key for a Redfish outlet state."""
        return _slug(f"{self.host}_redfish_outlet_{outlet_id}_state")

    def controllable_state_descriptors(self):
        """Return discovered state sensors that expose the Xerus Switch setState API."""
        if not self.sensor_descriptors:
            self.discover()
        controls = [
            descriptor
            for descriptor in self.sensor_descriptors
            if self._is_controllable_state_descriptor(descriptor)
        ]
        switch_like = [
            descriptor
            for descriptor in self.sensor_descriptors
            if "/sensors/switch" in descriptor.target
            or "_sensors_switch_" in _slug(descriptor.target)
        ]
        _LOGGER.debug(
            "LDCS controllable discovery on %s: descriptors=%s switch_like=%s controls=%s first_switch_like=%s",
            self.host,
            len(self.sensor_descriptors),
            len(switch_like),
            len(controls),
            [
                {
                    "name": descriptor.name,
                    "kind": descriptor.kind.value,
                    "type": descriptor.type_name,
                    "target": descriptor.target,
                }
                for descriptor in switch_like[:10]
            ],
        )
        return controls

    def set_controllable_state(self, key, turn_on):
        """Set a writable Xerus state sensor through the SDK Switch interface."""
        with self._lock:
            switch = self._controllable_state_switches.get(key)
            if switch is None:
                sensor = self._sensors_by_key[key]
                switch = sensors.Switch(sensor.target, self.agent)
                self._controllable_state_switches[key] = switch
            switch.setState(1 if turn_on else 0)

    def outlet_details(self, outlet_id):
        """Return discovered metadata for a one-based outlet ID."""
        return self._outlet_details.get(str(outlet_id), {})

    def capture_waveform(self, key):
        """Acquire and cache a fresh waveform for one diagnostic entity."""
        with self._lock:
            method = self._waveform_sources[key]
            self._waveform_cache[key] = self._waveform_value(method())
            return self._waveform_cache[key]

    def capture_inlet_waveform(self, inlet_number=1):
        """Acquire and cache a fresh waveform for a one-based inlet."""
        with self._lock:
            if not self.sensor_descriptors:
                self.discover()
            context = f"Inlet {inlet_number}"
            for descriptor in self.sensor_descriptors:
                if descriptor.kind == SensorKind.WAVEFORM and descriptor.context == context:
                    return self.capture_waveform(descriptor.key)
            raise RaritanError(f"{context} does not expose waveform capture on {self.host}")

    def capture_inlet_pole_waveform(self, line_name, inlet_number=1):
        """Acquire and cache a fresh waveform for one inlet phase."""
        with self._lock:
            if not self.sensor_descriptors:
                self.discover()
            context = f"Inlet {inlet_number} {line_name.upper()}"
            for descriptor in self.sensor_descriptors:
                if descriptor.kind == SensorKind.WAVEFORM and descriptor.context == context:
                    return self.capture_waveform(descriptor.key)
            raise RaritanError(f"{context} does not expose waveform capture on {self.host}")

    def _read_pdu_metadata(self, pdu):
        """Read identifying metadata from a primary or linked PDU proxy."""
        metadata = pdu.getMetaData()
        nameplate = metadata.nameplate
        try:
            settings = pdu.getSettings()
            configured_name = getattr(settings, "name", "")
        except Exception:  # noqa: BLE001
            configured_name = ""
        return {
            "name": configured_name,
            "manufacturer": nameplate.manufacturer,
            "model": nameplate.model,
            "serial_number": nameplate.serialNumber,
            "fw_revision": metadata.fwRevision,
            "mac_address": metadata.macAddress,
        }

    def _linked_pdus(self):
        """Yield linked PDU proxies exposed by the primary unit."""
        statuses = self._link_statuses or self._link_unit_statuses()
        link_ids = sorted(statuses) if statuses else range(2, 9)
        for link_id in link_ids:
            link_pdu = pdumodel.Pdu(f"/model/pdu/{link_id}", self.agent)
            try:
                metadata = self._read_pdu_metadata(link_pdu)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("No linked PDU %s discovered on %s: %s", link_id, self.host, err)
                continue
            yield link_id, link_pdu, metadata, statuses.get(link_id)

    def _link_unit_statuses(self):
        """Return PDU Link status details from the cascade manager when available."""
        if self.cascade_manager is None:
            self._link_statuses = {}
            return {}
        try:
            status = self.cascade_manager.getStatus()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read PDU Link status on %s: %s", self.host, err)
            self._link_statuses = {}
            return {}
        result = {}
        link_units = getattr(status, "linkUnits", []) or []
        if isinstance(link_units, dict):
            items = link_units.items()
        else:
            items = ((None, unit) for unit in link_units)
        for unit_key, unit in items:
            link_id = getattr(unit, "linkId", getattr(unit, "id", None))
            if link_id is None and unit_key is not None:
                link_id = unit_key
            if link_id is None:
                continue
            result[int(link_id)] = _json_safe(unit)
        self._link_statuses = result
        return result

    def _collect_pdu(self, descriptors, pdu, pdu_id, device_info, attributes=None):
        """Collect sensors from one PDU in a primary/link chain."""
        pdu_attributes = {
            "pdu_id": pdu_id,
            "pdu_link_role": "primary" if pdu_id in (0, 1) else "link_unit",
            **(attributes or {}),
        }
        self._collect_from_device(descriptors, "PDU", pdu, pdu_attributes, device_info)
        self._collect_children(descriptors, "Inlet", pdu.getInlets, pdu_id, device_info, pdu_attributes)
        self._collect_children(descriptors, "Outlet", pdu.getOutlets, pdu_id, device_info, pdu_attributes)
        self._collect_children(descriptors, "OCP", pdu.getOverCurrentProtectors, pdu_id, device_info, pdu_attributes)
        if self.profile in {"power", "full"}:
            self._collect_children(
                descriptors,
                "Transfer switch",
                pdu.getTransferSwitches,
                pdu_id,
                device_info,
                pdu_attributes,
            )
        if self.profile in {"power", "full"} and hasattr(pdu, "getPowerMeters"):
            self._collect_children(
                descriptors,
                "Power meter",
                pdu.getPowerMeters,
                pdu_id,
                device_info,
                pdu_attributes,
            )
        self._collect_peripherals(descriptors, pdu, pdu_id, device_info, pdu_attributes)
        self._collect_external_sensor_inventory(descriptors, pdu_id, device_info, pdu_attributes)
        self._collect_asset_inventory(descriptors, pdu_id, device_info, pdu_attributes)

    def _collect_outlet_groups(self, descriptors):
        """Collect sensors for Xerus outlet groups."""
        if self.outlet_group_manager is None:
            return
        try:
            groups = self.outlet_group_manager.getAllGroups()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read outlet groups on %s: %s", self.host, err)
            return

        for group_id, group in _iter_map(groups):
            attributes = self._outlet_group_attributes(group_id, group)
            device_info = self._outlet_group_device_info(group_id, attributes)
            self._collect_from_device(
                descriptors,
                f"Outlet group {group_id}",
                group,
                attributes,
                device_info,
            )

    def _outlet_group_attributes(self, group_id, group):
        """Return settings and member metadata for one outlet group."""
        try:
            metadata = group.getMetaData()
        except Exception:  # noqa: BLE001
            metadata = None
        try:
            settings = group.getSettings()
        except Exception:  # noqa: BLE001
            settings = None

        members = getattr(settings, "members", None) or getattr(metadata, "members", None) or []
        return {
            "outlet_group_id": group_id,
            "outlet_group_name": getattr(settings, "name", None) or getattr(metadata, "name", None),
            "outlet_group_members": _json_safe(members),
            "outlet_group_member_count": len(members),
            "pdu_link_role": "outlet_group",
        }

    def _outlet_group_device_info(self, group_id, attributes):
        """Return a separate Home Assistant device for an outlet group."""
        group_name = attributes.get("outlet_group_name") or f"Outlet Group {group_id}"
        device_info = {
            "identifiers": {(DOMAIN, f"{self.device_identifier or self.host}_outlet_group_{group_id}")},
            "manufacturer": self._metadata.get("manufacturer") or "Legrand",
            "model": "Xerus Outlet Group",
            "name": group_name,
            "sw_version": self._metadata.get("fw_revision"),
            "configuration_url": f"https://{self.host}",
        }
        if self._metadata:
            primary_identifier = self.device_identifier or self._metadata.get("serial_number") or self.host
            device_info["via_device"] = (DOMAIN, primary_identifier)
        return device_info

    def _collect_children(self, descriptors, label, getter, pdu_id=0, device_info=None, base_attributes=None):
        try:
            children = getter()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read %s list from %s: %s", label, self.host, err)
            return
        for index, child in enumerate(children, start=1):
            context = f"{label} {index}"
            attributes = {**(base_attributes or {})}
            attributes.update(self._device_attributes(label, index, child, pdu_id))
            self._collect_from_device(descriptors, context, child, attributes, device_info)
            self._collect_waveform(descriptors, label, index, child, attributes, device_info)

    def _collect_from_device(self, descriptors, context, device, attributes=None, device_info=None):
        try:
            sensor_struct = device.getSensors()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read sensors for %s on %s: %s", context, self.host, err)
            return
        self._collect_from_struct(descriptors, context, sensor_struct, attributes, device, device_info)

        if self.profile == "full" or context.startswith("Inlet "):
            poles = self._device_poles(device)
            for index, pole in enumerate(poles, start=1):
                line_name = _power_line_name(getattr(pole, "line", None))
                pole_context = f"{context} {line_name}" if line_name else f"{context} Pole {index}"
                pole_attributes = {**(attributes or {}), "power_line": line_name}
                self._collect_from_struct(descriptors, pole_context, pole, pole_attributes, None, device_info)

    def _collect_peripherals(self, descriptors, pdu, pdu_id=0, device_info=None, base_attributes=None):
        inventory = []
        for manager_target, manager in self._peripheral_managers(pdu, pdu_id):
            try:
                slots = manager.getDeviceSlots()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to read peripheral device slots at %s on %s: %s", manager_target, self.host, err)
                continue
            for index, slot in enumerate(slots, start=1):
                try:
                    settings = slot.getSettings()
                    name = settings.name or f"External Sensor {index}"
                    device = slot.getDevice()
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Unable to read peripheral slot %s at %s on %s: %s", index, manager_target, self.host, err)
                    continue
                if getattr(device, "device", None) is not None:
                    type_name, unit_name = "UNKNOWN", "NONE"
                    sensor_name = settings.name or f"External Sensor {index}"
                    sensor_description = getattr(settings, "description", "")
                    inventory.append(
                        {
                            "pdu_id": pdu_id,
                            "slot": index,
                            "name": sensor_name,
                            "configured_name": settings.name,
                            "description": sensor_description,
                            "type": type_name,
                            "unit": unit_name,
                            "target": getattr(device.device, "target", None),
                            "manager_target": manager_target,
                        }
                    )
                    self._add_sensor(
                        descriptors,
                        name,
                        "sensor",
                        device.device,
                        {
                            **(base_attributes or {}),
                            "sensor_name": settings.name,
                            "sensor_configured_name": settings.name,
                            "sensor_description": sensor_description,
                            "sensor_slot": index,
                            "sensor_type": type_name,
                            "peripheral_manager_target": manager_target,
                        },
                        device_info=device_info,
                        type_name=type_name,
                        unit_name=unit_name,
                    )
            if inventory:
                break
        self._external_sensor_inventory_by_pdu[pdu_id] = inventory

    def _peripheral_managers(self, pdu, pdu_id=0):
        """Yield peripheral managers for a primary or linked PDU."""
        tried = set()
        try:
            manager = pdu.getPeripheralDeviceManager()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read peripheral manager from PDU %s on %s: %s", pdu_id, self.host, err)
        else:
            target = getattr(manager, "target", f"pdu:{pdu_id}:manager")
            tried.add(target)
            yield target, manager

        if peripheral is None:
            return
        for target in self._peripheral_manager_targets(pdu_id):
            if target in tried:
                continue
            try:
                manager = peripheral.DeviceManager(target, self.agent)
                manager.getDeviceSlots()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to probe peripheral manager at %s on %s: %s", target, self.host, err)
                continue
            yield target, manager

    def _peripheral_manager_targets(self, pdu_id=0):
        """Return likely peripheral manager resource IDs for a primary or linked PDU."""
        if pdu_id in (0, 1):
            return (
                "/model/peripheraldevicemanager",
                "/model/peripheraldevices",
            )
        return (
            f"/link/{pdu_id}/model/peripheraldevicemanager",
            f"/link/{pdu_id}/model/peripheraldevices",
            f"/model/pdu/{pdu_id}/peripheraldevicemanager",
            f"/model/pdu/{pdu_id}/peripheraldevices",
        )

    def _collect_external_sensor_inventory(self, descriptors, pdu_id=0, device_info=None, attributes=None):
        """Add a summary entity for attached external sensors."""
        suffix = "" if pdu_id in (0, 1) else f"_pdu_{pdu_id}"
        name_prefix = "" if pdu_id in (0, 1) else f"PDU Link {pdu_id} "
        descriptors.append(
            SensorDescriptor(
                key=_slug(f"{self.host}{suffix}_external_sensor_inventory"),
                name=f"{name_prefix}External Sensor Inventory",
                context="External sensors",
                target=f"/model/pdu/{pdu_id}/peripheraldevicemanager",
                kind=SensorKind.INVENTORY,
                field="external_sensor_inventory",
                type_name="INVENTORY",
                asset_field="external_sensor_inventory",
                attributes={"pdu_id": pdu_id, **(attributes or {})},
                device_info=device_info or self.device_info,
            )
        )

    def _collect_modbus_inventory(self, descriptors):
        """Add a summary entity for the optional Xerus Modbus/TCP service."""
        descriptors.append(
            SensorDescriptor(
                key=_slug(f"{self.host}_xerus_modbus_tcp_layout"),
                name="Xerus Modbus TCP Layout",
                context="Xerus Modbus TCP",
                target="modbus://basic-pdu-parameters",
                kind=SensorKind.INVENTORY,
                field="xerus_modbus_layout",
                type_name="INVENTORY",
                asset_field="xerus_modbus_layout",
                attributes={
                    "ldcs_protocol": "modbus_tcp",
                    "modbus_register_block": "basic_pdu_parameters",
                    "modbus_start_address": "0000h",
                    "modbus_register_count": 5,
                },
                device_info=self._rack_or_device_info(),
            )
        )

    def _collect_service_status(self, descriptors):
        """Add a summary entity for PDU protocol and service configuration."""
        descriptors.append(
            SensorDescriptor(
                key=_slug(f"{self.host}_pdu_service_status"),
                name="PDU Service Status",
                context="PDU services",
                target="/net/services",
                kind=SensorKind.SERVICE_STATUS,
                field="service_status",
                type_name="SERVICE_STATUS",
                asset_field="service_status",
                attributes={
                    "ldcs_protocol": "json_rpc",
                    "service_status_sources": [
                        "net.Services",
                        "devsettings.Snmp",
                        "devsettings.Modbus",
                        "security.Security",
                        "tcp_connect",
                    ],
                },
                device_info=self._rack_or_device_info(),
            )
        )

    def _collect_config_snapshot(self, descriptors):
        """Add a diagnostic snapshot entity for PDU configuration."""
        descriptors.append(
            SensorDescriptor(
                key=_slug(f"{self.host}_pdu_config_snapshot"),
                name="PDU Config Snapshot",
                context="PDU configuration",
                target="/event_engine",
                kind=SensorKind.CONFIG_SNAPSHOT,
                field="config_snapshot",
                type_name="CONFIG",
                asset_field="config_snapshot",
                attributes={
                    "ldcs_protocol": "json_rpc",
                    "configuration_sources": [
                        "net.Services",
                        "devsettings.Snmp",
                        "devsettings.Modbus",
                        "security.Security",
                        "event.Engine",
                        "event.DataPushService",
                        "smartlock.DoorAccessControl",
                        "cascading.CascadeManager",
                    ],
                },
                device_info=self._rack_or_device_info(),
            )
        )

    def _collect_asset_logger(self, descriptors):
        try:
            self.asset_logger.getInfo()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read asset strip logger on %s: %s", self.host, err)
            return
        for field, name in (
            ("capacity", "Asset Log Capacity"),
            ("oldestRecord", "Asset Log Oldest Record"),
            ("newestRecord", "Asset Log Newest Record"),
            ("totalEventCount", "Asset Log Total Event Count"),
        ):
            key = _slug(f"{self.host}_asset_log_{field}")
            descriptors.append(
                SensorDescriptor(
                    key=key,
                    name=name,
                    context="Asset logger",
                    target="/model/assetstriplogger",
                    kind=SensorKind.ASSET_LOG,
                    field=field,
                    type_name="ASSET",
                    unit_name=None,
                    asset_field=field,
                )
            )

    def _collect_asset_inventory(self, descriptors, pdu_id=0, device_info=None, attributes=None):
        """Add the visual asset strip inventory entity."""
        suffix = "" if pdu_id in (0, 1) else f"_pdu_{pdu_id}"
        name_prefix = "" if pdu_id in (0, 1) else f"PDU Link {pdu_id} "
        descriptors.append(
            SensorDescriptor(
                key=_slug(f"{self.host}{suffix}_asset_strip_inventory"),
                name=f"{name_prefix}Asset Strip Inventory",
                context="Asset strip",
                target=self._asset_strip_targets(pdu_id)[0],
                kind=SensorKind.ASSET_INVENTORY,
                field="asset_strip_inventory",
                type_name="ASSET",
                unit_name=None,
                asset_field="asset_strip_inventory",
                attributes={
                    "pdu_id": pdu_id,
                    "asset_strip_targets": self._asset_strip_targets(pdu_id),
                    **(attributes or {}),
                },
                device_info=device_info or self.device_info,
            )
        )

    def _asset_inventory_value(self, descriptor):
        """Return rack-unit asset tag occupancy when an asset strip is exposed."""
        attrs = descriptor.attributes or {}
        pdu_id = attrs.get("pdu_id", 0)
        targets = attrs.get("asset_strip_targets")
        strip = self._asset_strip_interface(pdu_id, targets)
        probe_attrs = self._asset_strip_probe_attrs(pdu_id, targets)
        recent_records = self._asset_log_recent_records(pdu_id)
        if strip is None:
            asset_tags = _asset_tags_from_log_records(recent_records)
            return {
                "available": True,
                "value": len(asset_tags),
                "attributes": {
                    "asset_strip_status": "logger_only" if asset_tags else "unsupported",
                    "pdu_id": pdu_id,
                    "rack_unit_count": 42,
                    "asset_tags": asset_tags,
                    **probe_attrs,
                    "asset_log_recent_records": recent_records,
                    "telemetry_source": "json_rpc",
                },
            }
        try:
            state = _enum_name(strip.getState())
            strip_info = strip.getStripInfo()
            tags = strip.getAllTags()
            rack_units = strip.getAllRackUnitInfos()
        except Exception as err:  # noqa: BLE001
            return _error_value(err)
        asset_tags = [_asset_tag_attrs(tag) for tag in tags]
        rack_unit_count = getattr(strip_info, "rackUnitCount", None) or 42
        return {
            "available": True,
            "value": len(asset_tags),
            "attributes": {
                "asset_strip_status": state,
                "pdu_id": pdu_id,
                "rack_unit_count": rack_unit_count,
                "asset_tags": asset_tags,
                "asset_rack_units": [_asset_rack_unit_attrs(unit) for unit in rack_units],
                **probe_attrs,
                "asset_log_recent_records": recent_records,
                "main_tag_count": getattr(strip_info, "mainTagCount", None),
                "blade_tag_count": getattr(strip_info, "bladeTagCount", None),
                "max_main_tag_count": getattr(strip_info, "maxMainTagCount", None),
                "max_blade_tag_count": getattr(strip_info, "maxBladeTagCount", None),
                "blade_overflow": getattr(strip_info, "bladeOverflow", None),
                "component_count": getattr(strip_info, "componentCount", None),
                "cascade_state": _enum_name(getattr(strip_info, "cascadeState", None)),
                "telemetry_source": "json_rpc",
            },
        }

    def _asset_log_recent_records(self, pdu_id=0, count=20):
        """Return recent asset strip logger records for dashboard diagnostics."""
        logger = self._asset_logger_interface(pdu_id)
        try:
            info = logger.getInfo()
            newest = getattr(info, "newestRecord", -1)
            oldest = getattr(info, "oldestRecord", -1)
            total = getattr(info, "totalEventCount", 0) or 0
            capacity = getattr(info, "capacity", count) or count
            if newest < 0 or oldest < 0 or total <= 0:
                return []
            read_count = min(count, total, capacity)
            start = newest - read_count + 1
            if start < 0:
                start = oldest
            _next_id, records = logger.getRecords(start, read_count)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read recent asset strip records for PDU %s on %s: %s", pdu_id, self.host, err)
            return []
        return [_asset_log_record_attrs(record) for record in records]

    def _asset_logger_interface(self, pdu_id=0):
        """Return the primary or linked PDU asset strip logger."""
        if pdu_id in (0, 1):
            return self.asset_logger
        return assetmgrmodel.AssetStripLogger(f"/link/{pdu_id}/model/assetstriplogger", self.agent)

    def _asset_strip_interface(self, pdu_id=0, targets=None):
        """Return the first asset strip target that responds."""
        if pdu_id in self._asset_strips:
            return self._asset_strips[pdu_id]
        probe_errors = []
        for target in targets or self._asset_strip_targets(pdu_id):
            try:
                strip = assetmgrmodel.AssetStrip(target, self.agent)
                strip.getState()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to probe asset strip at %s on %s: %s", target, self.host, err)
                probe_errors.append({"target": target, "error": str(err)})
                continue
            self._asset_strips[pdu_id] = strip
            self._asset_strip_selected_targets[pdu_id] = target
            self._asset_strip_probe_errors[pdu_id] = probe_errors
            return strip
        self._asset_strips[pdu_id] = None
        self._asset_strip_selected_targets[pdu_id] = None
        self._asset_strip_probe_errors[pdu_id] = probe_errors
        return None

    def _asset_strip_probe_attrs(self, pdu_id=0, targets=None):
        """Return asset strip discovery diagnostics for the inventory entity."""
        return {
            "asset_strip_target": self._asset_strip_selected_targets.get(pdu_id),
            "asset_strip_probe_targets": list(targets or self._asset_strip_targets(pdu_id)),
            "asset_strip_probe_errors": self._asset_strip_probe_errors.get(pdu_id, []),
        }

    def _asset_strip_targets(self, pdu_id=0):
        """Return likely asset strip resource IDs for a primary or linked PDU."""
        if pdu_id in (0, 1):
            return (
                "/model/assetstrip/0",
                "/model/assetstrip",
                "/model/assetstrips/0",
                "/model/assetstrips",
                "/model/assetstrip/1",
                "/model/assetstrip/2",
                "/model/assetstrips/1",
                "/model/assetstrips/2",
            )
        return (
            f"/link/{pdu_id}/model/assetstrip/0",
            f"/link/{pdu_id}/model/assetstrip",
            f"/link/{pdu_id}/model/assetstrips/0",
            f"/link/{pdu_id}/model/assetstrips",
            f"/link/{pdu_id}/model/assetstrip/1",
            f"/link/{pdu_id}/model/assetstrip/2",
            f"/link/{pdu_id}/model/assetstrips/1",
            f"/link/{pdu_id}/model/assetstrips/2",
            f"/model/pdu/{pdu_id}/assetstrip/0",
            f"/model/pdu/{pdu_id}/assetstrip",
            f"/model/pdu/{pdu_id}/assetstrips/0",
            f"/model/pdu/{pdu_id}/assetstrips",
            f"/model/pdu/{pdu_id}/assetstrip/1",
            f"/model/pdu/{pdu_id}/assetstrip/2",
            f"/model/pdu/{pdu_id}/assetstrips/1",
            f"/model/pdu/{pdu_id}/assetstrips/2",
        )

    def _collect_alarm_summary(self, descriptors):
        """Add aggregate threshold and event-rule alarm entities."""
        for field, name in (
            ("status", "Alarm Status"),
            ("active_breach_count", "Active Breach Count"),
            ("warning_count", "Warning Sensor Count"),
            ("critical_count", "Critical Sensor Count"),
            ("acknowledgement_required_count", "Acknowledgement Required Alarm Count"),
        ):
            descriptors.append(
                SensorDescriptor(
                    key=self.alarm_summary_key(field),
                    name=name,
                    context="Alarm summary",
                    target="/model/alertedsensormanager",
                    kind=SensorKind.ALARM_SUMMARY,
                    field=field,
                    type_name="ALARM",
                    unit_name=None,
                    asset_field=field,
                )
            )

    def alarm_summary_key(self, field):
        """Return coordinator key for one alarm summary field."""
        return _slug(f"{self.host}_alarm_summary_{field}")

    def _collect_security_summary(self, descriptors):
        """Add rack security diagnostic entities."""
        for field, name in (
            ("status", "Rack Security Status"),
            ("door_access_rule_count", "Door Access Rule Count"),
            ("recent_access_event_count", "Recent Rack Access Event Count"),
        ):
            descriptors.append(
                SensorDescriptor(
                    key=self.security_summary_key(field),
                    name=name,
                    context="Rack security",
                    target="/smartlock/dooraccesscontrol",
                    kind=SensorKind.SECURITY,
                    field=field,
                    type_name="SECURITY",
                    unit_name=None,
                    asset_field=field,
                )
            )

    def security_summary_key(self, field):
        """Return coordinator key for one rack security summary field."""
        return _slug(f"{self.host}_security_summary_{field}")

    def _read_alarm_summary(self, descriptors):
        """Return aggregate threshold breaches and acknowledgement alarms."""
        try:
            counts = self.alerted_sensor_manager.getSensorCounts()
            alerted_sensors = self.alerted_sensor_manager.getAlertedSensors()
            alarms = self.alarm_manager.listAlarms()
        except Exception as err:  # noqa: BLE001
            return {descriptor.key: _error_value(err) for descriptor in descriptors}

        active_breach_count = counts.warned + counts.critical
        status = "critical" if counts.critical else "warning" if counts.warned else "normal"
        values = {
            "status": status,
            "active_breach_count": active_breach_count,
            "warning_count": counts.warned,
            "critical_count": counts.critical,
            "acknowledgement_required_count": len(alarms),
        }
        attrs = {
            "monitored_sensor_count": counts.total,
            "unavailable_sensor_count": counts.unavailable,
            "warning_sensor_count": counts.warned,
            "critical_sensor_count": counts.critical,
            "active_breach_count": active_breach_count,
            "acknowledgement_required_alarm_count": len(alarms),
            "alerted_sensors": [_alerted_sensor_attrs(sensor) for sensor in alerted_sensors],
            "acknowledgement_required_alarms": [_alarm_attrs(alarm) for alarm in alarms],
            "telemetry_source": "json_rpc",
        }
        return {
            descriptor.key: {
                "available": True,
                "value": values[descriptor.asset_field],
                "attributes": attrs if descriptor.asset_field == "status" else {"telemetry_source": "json_rpc"},
            }
            for descriptor in descriptors
        }

    def _read_security_summary(self, descriptors):
        """Return smartlock, keypad, and card-reader security summary details."""
        values, attrs = self._security_snapshot()
        return {
            descriptor.key: {
                "available": True,
                "value": values[descriptor.asset_field],
                "attributes": attrs if descriptor.asset_field == "status" else {"telemetry_source": "json_rpc"},
            }
            for descriptor in descriptors
        }

    def _track_security_state_events(self, data):
        """Track rack access events from polled door, handle, and lock state sensors."""
        now = datetime.now(timezone.utc).isoformat()
        for descriptor in self.sensor_descriptors:
            if descriptor.kind != SensorKind.STATE or descriptor.type_name not in {
                "DOOR_STATE",
                "DOOR_LOCK_STATE",
                "DOOR_HANDLE_LOCK",
            }:
                continue
            value = data.get(descriptor.key)
            if not value or not value.get("available"):
                continue
            current = _enum_name(value.get("value"))
            previous = self._security_state_last.get(descriptor.key)
            self._security_state_last[descriptor.key] = current
            if previous is None or previous == current:
                continue
            self._security_events.insert(
                0,
                {
                    "timestamp": now,
                    "event": _security_event_label(descriptor.type_name, current),
                    "sensor": descriptor.name,
                    "context": descriptor.context,
                    "sensor_type": descriptor.type_name,
                    "previous": previous,
                    "current": current,
                    "source": "state_polling",
                },
            )
        self._security_events = self._security_events[:40]

    def _security_snapshot(self):
        """Read smartlock security details when the PDU exposes them."""
        door_access = self._security_interface(
            "door_access",
            smartlock.DoorAccessControl if smartlock else None,
            (
                "/smartlock/dooraccesscontrol",
                "/smartlock/dooraccesscontrol/0",
                "/model/smartlock/dooraccesscontrol",
                "/model/smartlock/dooraccesscontrol/0",
                "/model/dooraccesscontrol",
                "/security/dooraccesscontrol",
            ),
            "getDoorAccessRules",
        )
        keypad_manager = self._security_interface(
            "keypad_manager",
            smartlock.KeypadManager if smartlock else None,
            (
                "/smartlock/keypadmanager",
                "/model/smartlock/keypadmanager",
                "/model/keypadmanager",
            ),
            "getKeypads",
        )
        card_reader_manager = self._security_interface(
            "card_reader_manager",
            smartcard.CardReaderManager if smartcard else None,
            (
                "/smartcard/cardreadermanager",
                "/model/smartcard/cardreadermanager",
                "/model/cardreadermanager",
            ),
            "getCardReaders",
        )

        unsupported = []
        rules = {}
        keypads = []
        card_readers = []

        if door_access is None:
            unsupported.append("door_access_control")
        else:
            try:
                rules = door_access.getDoorAccessRules()
            except Exception as err:  # noqa: BLE001
                unsupported.append(f"door_access_rules: {err}")

        if keypad_manager is not None:
            try:
                keypads = keypad_manager.getKeypads()
            except Exception as err:  # noqa: BLE001
                unsupported.append(f"keypads: {err}")

        if card_reader_manager is not None:
            try:
                card_readers = card_reader_manager.getCardReaders()
            except Exception as err:  # noqa: BLE001
                unsupported.append(f"card_readers: {err}")

        rule_list = _door_access_rules_attrs(rules)
        recent_events = list(self._security_events)
        local_security = _local_security_status(self._security_state_last.values())
        status = local_security or ("unsupported" if door_access is None else "normal")
        values = {
            "status": status,
            "door_access_rule_count": len(rule_list),
            "recent_access_event_count": len(recent_events),
        }
        attrs = {
            "door_access_rules": rule_list,
            "door_access_rule_count": len(rule_list),
            "keypad_count": len(keypads),
            "card_reader_count": len(card_readers),
            "recent_access_events": recent_events,
            "recent_access_event_count": len(recent_events),
            "door_lock_sensor_states": list(self._security_state_last.values()),
            "security_event_source": "door_state_polling",
            "unsupported_security_features": unsupported,
            "telemetry_source": "json_rpc",
        }
        return values, attrs

    def _security_interface(self, cache_key, interface_class, targets, probe_method):
        """Return the first smartlock interface target that responds."""
        if interface_class is None:
            return None
        if cache_key in self._security_interfaces:
            return self._security_interfaces[cache_key]
        for target in targets:
            try:
                interface = interface_class(target, self.agent)
                getattr(interface, probe_method)()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to probe %s at %s on %s: %s", cache_key, target, self.host, err)
                continue
            self._security_interfaces[cache_key] = interface
            return interface
        self._security_interfaces[cache_key] = None
        return None

    def _collect_from_struct(self, descriptors, context, struct, attributes=None, device=None, device_info=None):
        for field in getattr(struct, "elements", []):
            sensor = getattr(struct, field, None)
            self._add_sensor(descriptors, context, field, sensor, attributes, device, device_info)

    def _add_sensor(
        self,
        descriptors,
        context,
        field,
        sensor,
        attributes=None,
        device=None,
        device_info=None,
        type_name=None,
        unit_name=None,
    ):
        if not self._profile_includes(context, field):
            return

        if isinstance(sensor, sensors.Switch):
            kind = SensorKind.STATE
        elif isinstance(sensor, sensors.NumericSensor):
            kind = SensorKind.NUMERIC
        elif isinstance(sensor, sensors.StateSensor):
            kind = SensorKind.STATE
        else:
            return

        target = sensor.target
        key = _slug(f"{self.host}_{target}_{field}")
        if key in self._sensors_by_key:
            return

        if type_name is None and unit_name is None:
            type_name, unit_name = _sensor_type_names(sensor)
        name = _pretty_name(context, field, type_name, attributes)
        descriptor = SensorDescriptor(
            key=key,
            name=name,
            context=context,
            target=target,
            kind=kind,
            field=field,
            type_name=type_name,
            unit_name=unit_name,
            attributes=attributes,
            device_info=device_info,
        )
        descriptors.append(descriptor)
        self._sensors_by_key[key] = sensor
        if _is_outlet_state_descriptor(descriptor) and device is not None:
            self._outlet_state_devices_by_key[key] = device

    def _is_controllable_state_descriptor(self, descriptor):
        """Return true when a state sensor can be controlled with setState."""
        if not _is_switch_backed_state_descriptor(descriptor) or _is_outlet_state_descriptor(descriptor):
            return False
        sensor = self._sensors_by_key.get(descriptor.key)
        if sensor is None:
            return False
        if descriptor.type_name not in {
            "CONTACT_CLOSURE",
            "DRY_CONTACT",
            "ON_OFF_SENSOR",
            "POWERED_DRY_CONTACT",
            "DOOR_LOCK_STATE",
            "DOOR_HANDLE_LOCK",
            "UNKNOWN",
        }:
            return False
        if not _looks_controllable_state_descriptor(descriptor):
            return False
        if isinstance(sensor, sensors.Switch):
            self._controllable_state_switches[descriptor.key] = sensor
        return True

    def _device_attributes(self, label, index, device, pdu_id=0):
        """Return useful settings and protection details for one PDU child."""
        try:
            metadata = device.getMetaData()
        except Exception:  # noqa: BLE001
            metadata = None
        try:
            settings = device.getSettings()
        except Exception:  # noqa: BLE001
            settings = None

        attributes = {
            "pdu_id": pdu_id,
            "device_label": getattr(metadata, "label", None),
            "configured_name": getattr(settings, "name", ""),
            "display_name": getattr(settings, "name", "") or getattr(metadata, "label", None),
            "description": getattr(settings, "description", ""),
        }
        rating = getattr(metadata, "rating", None)
        if rating is not None:
            attributes.update(
                {
                    "rated_current_a": getattr(rating, "decimalCurrent", None),
                    "rated_min_voltage_v": getattr(rating, "minVoltage", None),
                    "rated_max_voltage_v": getattr(rating, "maxVoltage", None),
                }
            )
        if label == "Outlet":
            attributes.update(self._outlet_protection_attributes(device))
            attributes["waveform_supported"] = bool(getattr(metadata, "hasWaveformSupport", False))
            if pdu_id in (0, 1):
                self._outlet_details[str(index)] = attributes
        elif label == "Inlet":
            lines = [
                line
                for pole in self._device_poles(device)
                if (line := _power_line_name(getattr(pole, "line", None)))
            ]
            phases = [line for line in lines if line in {"L1", "L2", "L3"}]
            attributes["waveform_supported"] = bool(getattr(metadata, "hasWaveformSupport", False))
            attributes["power_lines"] = lines
            attributes["phase_count"] = len(phases)
            attributes["supply_type"] = "three_phase" if len(phases) == 3 else "single_phase"
        elif label == "OCP":
            attributes["ocp_label"] = getattr(metadata, "label", None)
            attributes["ocp_poles"] = [
                _power_line_name(getattr(pole, "line", None))
                for pole in self._device_poles(device)
            ]
        return attributes

    def _device_poles(self, device):
        """Return cached electrical poles for a PDU child."""
        target = getattr(device, "target", None)
        if target not in self._poles_by_target:
            try:
                self._poles_by_target[target] = device.getPoles()
            except Exception:  # noqa: BLE001
                self._poles_by_target[target] = []
        return self._poles_by_target[target]

    def _outlet_protection_attributes(self, outlet):
        """Return the OCP protecting an outlet."""
        try:
            _inlet, ocp, poles = outlet.getIOP()
        except Exception:  # noqa: BLE001
            return {}
        target = getattr(ocp, "target", None)
        if target in self._ocp_details:
            return {**self._ocp_details[target], "ocp_poles": [_json_enum(getattr(pole, "line", None)) for pole in poles]}
        try:
            metadata = ocp.getMetaData() if ocp is not None else None
            settings = ocp.getSettings() if ocp is not None else None
        except Exception:  # noqa: BLE001
            return {}
        rating = getattr(metadata, "rating", None)
        details = {
            "ocp_target": target,
            "ocp_label": getattr(metadata, "label", None),
            "ocp_name": getattr(settings, "name", ""),
            "ocp_rated_current_a": getattr(rating, "decimalCurrent", None),
        }
        self._ocp_details[target] = details
        return {**details, "ocp_poles": [_json_enum(getattr(pole, "line", None)) for pole in poles]}

    def _collect_waveform(self, descriptors, label, index, device, attributes, device_info=None):
        """Add inlet power-quality and outlet inrush waveform diagnostics."""
        if not attributes.get("waveform_supported"):
            return
        if label == "Inlet" and hasattr(device, "getWaveform"):
            self._add_waveform(
                descriptors,
                name=f"Inlet {index} Power Quality Waveform",
                context=f"Inlet {index}",
                target=device.target,
                method=device.getWaveform,
                attributes=attributes,
                device_info=device_info,
            )
            if hasattr(device, "getPoleWaveform"):
                for pole in self._device_poles(device):
                    line_name = _power_line_name(getattr(pole, "line", None))
                    if line_name not in {"L1", "L2", "L3"}:
                        continue
                    self._add_waveform(
                        descriptors,
                        name=f"Inlet {index} {line_name} Power Quality Waveform",
                        context=f"Inlet {index} {line_name}",
                        target=f"{device.target}/{line_name}",
                        method=lambda line=pole.line: device.getPoleWaveform(line),
                        attributes={**attributes, "power_line": line_name},
                        device_info=device_info,
                    )
            return
        elif label == "Outlet" and index == 1 and hasattr(device, "getInrushWaveform"):
            name = f"Outlet {index} Inrush Waveform"
            method = device.getInrushWaveform
        else:
            return
        self._add_waveform(
            descriptors,
            name=name,
            context=f"{label} {index}",
            target=device.target,
            method=method,
            attributes=attributes,
            device_info=device_info,
        )

    def _add_waveform(self, descriptors, name, context, target, method, attributes, device_info=None):
        """Add one cached waveform diagnostic entity."""
        key = _slug(f"{self.host}_{target}_waveform")
        descriptors.append(
            SensorDescriptor(
                key=key,
                name=name,
                context=context,
                target=target,
                kind=SensorKind.WAVEFORM,
                type_name="WAVEFORM",
                attributes=attributes,
                device_info=device_info,
            )
        )
        self._waveform_sources[key] = method

    def _read_waveforms(self, descriptors):
        """Return cached waveform captures, refreshing them periodically."""
        now = monotonic()
        if not self._waveform_cache or now - self._last_waveform_refresh >= WAVEFORM_REFRESH_INTERVAL:
            for descriptor in descriptors:
                method = self._waveform_sources.get(descriptor.key)
                if method is None:
                    continue
                try:
                    waveform = method()
                except Exception as err:  # noqa: BLE001
                    self._waveform_cache[descriptor.key] = _error_value(err)
                    continue
                self._waveform_cache[descriptor.key] = self._waveform_value(waveform)
            self._last_waveform_refresh = now
        return {
            descriptor.key: self._waveform_cache.get(
                descriptor.key,
                {"available": True, "value": "empty", "attributes": {"telemetry_source": "json_rpc"}},
            )
            for descriptor in descriptors
        }

    def _read_inventory(self, descriptors):
        """Return inventory summary entities."""
        data = {}
        for descriptor in descriptors:
            if descriptor.asset_field == "external_sensor_inventory":
                pdu_id = (descriptor.attributes or {}).get("pdu_id", 0)
                inventory = self._external_sensor_inventory_by_pdu.get(pdu_id, [])
                sensors_by_type = {}
                for sensor in inventory:
                    sensor_type = sensor.get("type") or "UNKNOWN"
                    sensors_by_type[sensor_type] = sensors_by_type.get(sensor_type, 0) + 1
                data[descriptor.key] = {
                    "available": True,
                    "value": len(inventory),
                    "attributes": {
                        "pdu_id": pdu_id,
                        "external_sensor_count": len(inventory),
                        "external_sensor_type_counts": sensors_by_type,
                        "external_sensors": inventory,
                        "telemetry_source": "json_rpc",
                    },
                }
            elif descriptor.asset_field == "xerus_modbus_layout":
                value = self.modbus.read_layout()
                value.setdefault("attributes", {}).update(descriptor.attributes or {})
                data[descriptor.key] = value
        return data

    def _read_service_status(self, descriptors):
        """Return protocol and service status diagnostics."""
        status = self._service_status_value()
        return {
            descriptor.key: {
                "available": status["available"],
                "value": status["value"],
                "attributes": {
                    **(descriptor.attributes or {}),
                    **status["attributes"],
                },
            }
            for descriptor in descriptors
        }

    def _read_config_snapshot(self, descriptors):
        """Return full PDU configuration snapshot diagnostics."""
        snapshot = self._config_snapshot_value()
        return {
            descriptor.key: {
                "available": snapshot["available"],
                "value": snapshot["value"],
                "attributes": {
                    **(descriptor.attributes or {}),
                    **snapshot["attributes"],
                },
            }
            for descriptor in descriptors
        }

    def _config_snapshot_value(self):
        """Return cached PDU configuration snapshot details."""
        now = monotonic()
        if (
            self._config_snapshot_cache is not None
            and now - self._last_config_snapshot_refresh < SERVICE_STATUS_REFRESH_INTERVAL
        ):
            return self._config_snapshot_cache

        service_value = self._service_status_value()
        services = service_value.get("attributes", {}).get("services", {})
        event_config = self._event_engine_config()
        datapush_config = self._datapush_config()
        security_values, security_attrs = self._security_snapshot()
        link_units = self._link_statuses or self._link_unit_statuses()
        topology = {
            "mode": "pdu_link" if link_units else "standalone_or_separate_ha_entries",
            "rack_name": self.rack_name,
            "rack_role": self.rack_role,
            "rack_position": self.rack_position,
            "primary": self._metadata,
            "link_units": link_units,
        }
        counts = {
            "enabled_service_count": service_value.get("attributes", {}).get("configured_service_count", 0),
            "event_rule_count": len(event_config.get("rules", [])),
            "enabled_event_rule_count": sum(1 for rule in event_config.get("rules", []) if rule.get("enabled")),
            "event_action_count": len(event_config.get("actions", [])),
            "datapush_entry_count": len(datapush_config.get("entries", [])),
            "door_access_rule_count": len(security_attrs.get("door_access_rules", [])),
            "linked_pdu_count": len(topology["link_units"]),
        }
        self._config_snapshot_cache = {
            "available": True,
            "value": (
                f"{counts['enabled_service_count']} services, "
                f"{counts['enabled_event_rule_count']}/{counts['event_rule_count']} rules, "
                f"{counts['datapush_entry_count']} data push"
            ),
            "attributes": {
                "telemetry_source": "json_rpc",
                "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
                "configuration_counts": counts,
                "topology": topology,
                "services": services,
                "network_services": service_value.get("attributes", {}).get("network_services", {}),
                "data_push_entries": datapush_config.get("entries", []),
                "data_push_errors": datapush_config.get("errors", []),
                "managed_mqtt_datapush": self._mqtt_datapush_status,
                "recent_mqtt_events": list(self._mqtt_events),
                "recent_mqtt_event_count": self._mqtt_event_count,
                "event_action_types": event_config.get("action_types", []),
                "event_actions": event_config.get("actions", []),
                "event_rules": event_config.get("rules", []),
                "event_config_errors": event_config.get("errors", []),
                "door_access_rules": security_attrs.get("door_access_rules", []),
                "door_access_rule_count": security_values.get("door_access_rule_count"),
                "security_unsupported": security_attrs.get("unsupported_security_interfaces", []),
            },
        }
        self._last_config_snapshot_refresh = now
        return self._config_snapshot_cache

    def _service_status_value(self):
        """Return cached PDU service configuration and reachability details."""
        now = monotonic()
        if (
            self._service_status_cache is not None
            and now - self._last_service_status_refresh < SERVICE_STATUS_REFRESH_INTERVAL
        ):
            return self._service_status_cache

        services = self._network_service_settings()
        snmp = self._snmp_settings()
        modbus = self._modbus_settings()
        ssh = self._ssh_settings()

        service_status = {
            "json_rpc": {
                "configured": True,
                "reachable": True,
                "source": "active_sdk_session",
                "detail": "JSON-RPC authenticated successfully",
            },
            "http": self._tcp_service_status("http", services, 80),
            "https": self._tcp_service_status("https", services, 443),
            "ssh": {
                **self._tcp_service_status("ssh", services, 22),
                "password_auth": ssh.get("allow_password_auth"),
                "public_key_auth": ssh.get("allow_public_key_auth"),
                "settings_source": ssh.get("source"),
                "settings_error": ssh.get("error"),
            },
            "modbus_tcp": {
                **self._tcp_service_status("modbus", services, self.modbus.port),
                "readonly": modbus.get("tcp_readonly"),
                "settings_source": modbus.get("source"),
                "settings_error": modbus.get("error"),
            },
            "modbus_rtu": {
                "configured": modbus.get("serial_enabled"),
                "reachable": None,
                "source": modbus.get("source"),
                "detail": "Modbus/RTU serial gateway setting",
                "baudrate": modbus.get("serial_baudrate"),
                "parity": modbus.get("serial_parity"),
                "stopbits": modbus.get("serial_stopbits"),
                "readonly": modbus.get("serial_readonly"),
                "error": modbus.get("error"),
            },
            "snmp_v1_v2c": {
                "configured": snmp.get("v2_enabled"),
                "reachable": None,
                "source": snmp.get("source"),
                "detail": "SNMP is UDP; configuration is read via JSON-RPC",
                "sys_name": snmp.get("sys_name"),
                "sys_location": snmp.get("sys_location"),
                "error": snmp.get("error"),
            },
            "snmp_v3": {
                "configured": snmp.get("v3_enabled"),
                "reachable": None,
                "source": snmp.get("source"),
                "detail": "SNMPv3 configuration is read via JSON-RPC",
                "error": snmp.get("error"),
            },
            "prometheus": self._http_endpoint_status(
                "prometheus",
                f"https://{self.host}/cgi-bin/dump_prometheus.cgi?include_names=1",
            ),
            "redfish": self._http_endpoint_status(
                "redfish",
                f"https://{self.host}/redfish/v1/",
            ),
            "mqtt_datapush": {
                "configured": self.mqtt_datapush_enabled or bool(self.mqtt_datapush_config.get("enabled")),
                "reachable": None,
                "source": "home_assistant_mqtt_subscription",
                "detail": f"Home Assistant refresh topic: {self.mqtt_topic}",
                "managed": self.mqtt_datapush_enabled,
                "last_message_time": self._mqtt_datapush_status.get("last_message_time"),
                "last_topic": self._mqtt_datapush_status.get("last_topic"),
                "message_count": self._mqtt_event_count,
                "provisioning": self._mqtt_datapush_status,
            },
        }

        configured_count = sum(1 for item in service_status.values() if item.get("configured") is True)
        reachable_count = sum(1 for item in service_status.values() if item.get("reachable") is True)
        self._service_status_cache = {
            "available": True,
            "value": f"{reachable_count}/{len(service_status)} reachable",
            "attributes": {
                "telemetry_source": "json_rpc",
                "service_count": len(service_status),
                "configured_service_count": configured_count,
                "reachable_service_count": reachable_count,
                "services": service_status,
                "network_services": services,
                "recent_mqtt_events": list(self._mqtt_events),
            },
        }
        self._last_service_status_refresh = now
        return self._service_status_cache

    def _network_service_settings(self):
        """Return enabled TCP service settings from Xerus."""
        if net is None:
            return {}
        try:
            service_settings = net.Services("/net/services", self.agent).getSettings()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read network service settings on %s: %s", self.host, err)
            return {"_error": str(err)}
        return {
            str(getattr(item, "service", "")).lower(): {
                "configured": bool(getattr(item, "enable", False)),
                "port": int(getattr(item, "port", 0) or 0),
                "source": "net.Services",
            }
            for item in service_settings
            if getattr(item, "service", None)
        }

    def _snmp_settings(self):
        """Return SNMP settings from Xerus when exposed by the SDK."""
        if devsettings is None or not hasattr(devsettings, "Snmp"):
            return {"source": "unavailable", "error": "raritan.rpc.devsettings.Snmp unavailable"}
        try:
            cfg = devsettings.Snmp("/snmp", self.agent).getConfiguration()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read SNMP settings on %s: %s", self.host, err)
            return {"source": "devsettings.Snmp", "error": str(err)}
        return {
            "source": "devsettings.Snmp",
            "v2_enabled": bool(getattr(cfg, "v2enable", False)),
            "v3_enabled": bool(getattr(cfg, "v3enable", False)),
            "sys_name": getattr(cfg, "sysName", ""),
            "sys_location": getattr(cfg, "sysLocation", ""),
            "sys_contact": getattr(cfg, "sysContact", ""),
        }

    def _modbus_settings(self):
        """Return Modbus settings from Xerus when exposed by the SDK."""
        if devsettings is None or not hasattr(devsettings, "Modbus"):
            return {"source": "unavailable", "error": "raritan.rpc.devsettings.Modbus unavailable"}
        try:
            settings = devsettings.Modbus("/modbus", self.agent).getSettings()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read Modbus settings on %s: %s", self.host, err)
            return {"source": "devsettings.Modbus", "error": str(err)}
        tcp = getattr(settings, "tcp", None)
        serial = getattr(settings, "serial", None)
        return {
            "source": "devsettings.Modbus",
            "tcp_readonly": getattr(tcp, "readonly", None),
            "serial_enabled": bool(getattr(serial, "enabled", False)) if serial is not None else None,
            "serial_baudrate": getattr(serial, "baudrate", None),
            "serial_parity": _enum_name(getattr(serial, "parity", None)),
            "serial_stopbits": getattr(serial, "stopbits", None),
            "serial_readonly": getattr(serial, "readonly", None),
            "primary_unit_id": getattr(settings, "primaryUnitId", None),
        }

    def _ssh_settings(self):
        """Return SSH authentication settings from Xerus when exposed by the SDK."""
        if security is None or not hasattr(security, "Security"):
            return {"source": "unavailable", "error": "raritan.rpc.security.Security unavailable"}
        try:
            settings = security.Security("/security", self.agent).getSSHSettings()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read SSH settings on %s: %s", self.host, err)
            return {"source": "security.Security", "error": str(err)}
        return {
            "source": "security.Security",
            "allow_password_auth": bool(getattr(settings, "allowPasswordAuth", False)),
            "allow_public_key_auth": bool(getattr(settings, "allowPublicKeyAuth", False)),
        }

    def _tcp_service_status(self, service_name, services, default_port):
        """Return combined configured/reachable state for one TCP service."""
        configured = None
        port = default_port
        service = services.get(service_name) if isinstance(services, dict) else None
        if isinstance(service, dict):
            configured = service.get("configured")
            port = service.get("port") or default_port
        reachable = _tcp_reachable(self.host, port)
        return {
            "configured": configured,
            "reachable": reachable,
            "port": port,
            "source": service.get("source") if isinstance(service, dict) else "tcp_connect",
            "detail": "TCP service setting plus Home Assistant reachability",
        }

    def _http_endpoint_status(self, name, url):
        """Return whether an HTTPS service endpoint responds."""
        try:
            response = requests.get(
                url,
                auth=(self.username, self.password),
                verify=self.verify_ssl,
                timeout=5,
            )
            reachable = 200 <= response.status_code < 500
            return {
                "configured": reachable,
                "reachable": reachable,
                "source": "http_get",
                "status_code": response.status_code,
                "detail": f"{name} endpoint responded",
            }
        except Exception as err:  # noqa: BLE001
            return {
                "configured": None,
                "reachable": False,
                "source": "http_get",
                "error": str(err),
                "detail": f"{name} endpoint did not respond",
            }

    def _event_engine_config(self):
        """Return configured Xerus event actions and rules."""
        errors = []
        engine = event.Engine("/event_engine", self.agent)
        try:
            actions = engine.listActions()
        except Exception as err:  # noqa: BLE001
            actions = []
            errors.append(f"listActions: {err}")
        try:
            action_types = list(engine.listActionTypes())
        except Exception as err:  # noqa: BLE001
            action_types = []
            errors.append(f"listActionTypes: {err}")
        try:
            rules = engine.listRules()
        except Exception as err:  # noqa: BLE001
            rules = []
            errors.append(f"listRules: {err}")
        actions_by_id = {str(getattr(action, "id", "")): _event_action_attrs(action) for action in actions}
        return {
            "actions": list(actions_by_id.values()),
            "action_types": action_types,
            "rules": [_event_rule_attrs(rule, actions_by_id) for rule in rules],
            "errors": errors,
        }

    def _datapush_config(self):
        """Return configured Xerus data push entries."""
        errors = []
        try:
            service = event.DataPushService("/datapush", self.agent)
            entries = service.listEntries()
        except Exception as err:  # noqa: BLE001
            return {"entries": [], "errors": [str(err)]}

        result = []
        for entry_id, settings in _iter_map(entries):
            status = None
            try:
                _ret, status = service.getEntryStatus(int(entry_id))
            except Exception as err:  # noqa: BLE001
                errors.append(f"getEntryStatus {entry_id}: {err}")
            result.append(_datapush_entry_attrs(entry_id, settings, status))
        return {"entries": result, "errors": errors}

    def _waveform_value(self, waveform):
        """Return a JSON-safe Home Assistant value for an SDK waveform."""
        voltage = list(waveform.voltage)
        current = list(waveform.current)
        return {
            "available": True,
            "value": "captured" if voltage or current else "empty",
            "attributes": {
                "sample_rate_hz": waveform.sampleRate,
                "voltage_samples": voltage,
                "current_samples": current,
                "sample_count": max(len(voltage), len(current)),
                "telemetry_source": "json_rpc",
            },
        }

    def _profile_includes(self, context, field):
        if self.profile == "full":
            return True

        if "Pole" in context:
            return False

        if not _is_electrical_context(context):
            return True

        if self.profile == "basic":
            if context == "PDU":
                return field in {"activeEnergy", "activePower", "apparentPower", "current", "lineFrequency", "powerFactor", "voltage"}
            if context.startswith("Outlet group"):
                return field in {"activeEnergy", "activePower", "apparentPower", "powerFactor", "state", "outletState"}
            if context.startswith("Inlet"):
                return field in BASIC_FIELDS
            if context.startswith("Outlet"):
                return field in {"activePower", "outletState"}
            if context.startswith("OCP"):
                return field in {"current", "trip"}
            return field in {"state"}

        if self.profile == "power":
            if field in POWER_SKIP_FIELDS:
                return False
            return True

        return False


def _sensor_type_names(sensor):
    try:
        type_spec = sensor.getTypeSpec()
    except Exception:  # noqa: BLE001
        return None, None
    return SENSOR_TYPE_NAMES.get(type_spec.type, str(type_spec.type)), UNIT_NAMES.get(
        type_spec.unit, str(type_spec.unit)
    )


def _is_electrical_context(context):
    return context == "PDU" or context.startswith(
        ("Inlet", "Outlet", "Outlet group", "OCP", "Transfer switch", "Power meter")
    )


def _pretty_name(context, field, type_name, attributes=None):
    field_name = re.sub(r"(?<!^)(?=[A-Z])", " ", field).replace("_", " ").title()
    if field_name.lower() == "sensor" and type_name:
        field_name = type_name.replace("_", " ").title()
    display_name = (attributes or {}).get("display_name") or (attributes or {}).get("sensor_configured_name")
    if display_name and display_name != context:
        return f"{context} {display_name} {field_name}"
    return f"{context} {field_name}"


def _slug(value):
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def _iter_map(value):
    """Yield items from SDK maps, Python dicts, or key/value pair sequences."""
    if isinstance(value, dict):
        yield from value.items()
        return
    for item in value or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            yield item[0], item[1]


def _reading_status_attrs(reading):
    status = getattr(reading, "status", None)
    if status is None:
        return {}
    return {
        "above_upper_critical": getattr(status, "aboveUpperCritical", False),
        "above_upper_warning": getattr(status, "aboveUpperWarning", False),
        "below_lower_warning": getattr(status, "belowLowerWarning", False),
        "below_lower_critical": getattr(status, "belowLowerCritical", False),
    }


def _is_outlet_state_descriptor(descriptor):
    return descriptor.context.startswith("Outlet ") and descriptor.field == "outletState"


def _is_contact_state_descriptor(descriptor):
    return descriptor.type_name in {
        "CONTACT_CLOSURE",
        "DRY_CONTACT",
        "ON_OFF_SENSOR",
        "POWERED_DRY_CONTACT",
    }


def _is_ocp_trip_descriptor(descriptor):
    return descriptor.context.startswith("OCP ") and descriptor.field == "trip"


def _is_rack_door_state_descriptor(descriptor):
    return descriptor.type_name in {"DOOR_STATE", "DOOR_LOCK_STATE", "DOOR_HANDLE_LOCK"}


def _is_switch_backed_state_descriptor(descriptor):
    """Return true for regular state sensors and SDK switch-backed state targets."""
    if descriptor.kind == SensorKind.STATE:
        return True
    return "/sensors/switch" in descriptor.target or "_sensors_switch_" in _slug(descriptor.target)


def _looks_controllable_state_descriptor(descriptor):
    """Return true for state sensors that should be offered as controls."""
    lowered = " ".join(
        str(value or "").lower()
        for value in (
            descriptor.name,
            descriptor.context,
            descriptor.field,
            descriptor.type_name,
            (descriptor.attributes or {}).get("sensor_name"),
            (descriptor.attributes or {}).get("sensor_configured_name"),
            (descriptor.attributes or {}).get("sensor_description"),
        )
    )
    return any(
        token in lowered
        for token in (
            "control",
            "switch",
            "dry contact",
            "dry_contact",
            "powered dry contact",
            "powered_dry_contact",
            "contact closure",
            "contact_closure",
            "led",
            "light",
            "beeper",
            "lock",
            "handle",
            "door_handle_lock",
            "door_lock_state",
        )
    )


def _requires_state_label(descriptor):
    return (
        _is_outlet_state_descriptor(descriptor)
        or _is_contact_state_descriptor(descriptor)
        or _is_ocp_trip_descriptor(descriptor)
        or _is_rack_door_state_descriptor(descriptor)
    )


def _is_primary_descriptor(descriptor):
    return (descriptor.attributes or {}).get("pdu_id", 0) in (0, 1)


def _outlet_state_value(state):
    """Return a display-friendly outlet state with detailed flags as attributes."""
    available = bool(getattr(state, "available", True))
    power_state = getattr(state, "powerState", getattr(state, "value", None))
    attributes = {
        "outlet_power_state": _outlet_power_state_label(power_state),
        "switch_on_in_progress": bool(getattr(state, "switchOnInProgress", False)),
        "cycle_in_progress": bool(getattr(state, "cycleInProgress", False)),
        "load_shed": bool(getattr(state, "isLoadShed", False)),
        "suspended": bool(getattr(state, "isSuspended", False)),
        "service_mode": bool(getattr(state, "inServiceMode", False)),
        "has_inrush_waveform": bool(getattr(state, "hasInrushWaveform", False)),
        "last_power_state_change": _timestamp(getattr(state, "lastPowerStateChange", None)),
        "telemetry_source": "json_rpc",
    }
    if not available:
        return {"available": False, "value": None, "attributes": attributes}
    return {
        "available": True,
        "value": _outlet_state_label(state),
        "attributes": attributes,
    }


def _outlet_state_label(state):
    if getattr(state, "cycleInProgress", False):
        return "Cycle"
    if getattr(state, "switchOnInProgress", False):
        return "Switching On"
    if getattr(state, "isLoadShed", False):
        return "Load Shed"
    if getattr(state, "isSuspended", False):
        return "Suspended"
    if getattr(state, "inServiceMode", False):
        power_label = _outlet_power_state_label(getattr(state, "powerState", getattr(state, "value", None)))
        return f"Service Mode {power_label}" if power_label else "Service Mode"
    return _outlet_power_state_label(getattr(state, "powerState", getattr(state, "value", None))) or "Unknown"


def _outlet_power_state_label(value):
    if value is None:
        return None
    name = _enum_name(value)
    if name in {"ps_on", "on", "1", "true"}:
        return "On"
    if name in {"ps_off", "off", "0", "false"}:
        return "Off"
    return name.replace("_", " ").title() if name else None


def _binary_state_value(state, source):
    """Return a display-friendly binary state."""
    available = bool(getattr(state, "available", True))
    raw_value = getattr(state, "value", None)
    if not available:
        return {
            "available": False,
            "value": None,
            "attributes": {"raw_state": _json_safe(raw_value), "state_source": source, "telemetry_source": "json_rpc"},
        }
    return {
        "available": True,
        "value": _binary_state_label(raw_value),
        "attributes": {"raw_state": _json_safe(raw_value), "state_source": source, "telemetry_source": "json_rpc"},
    }


def _ocp_trip_state_value(state):
    value = _binary_state_value(state, "ocp_trip")
    if value["value"] == "On":
        value["value"] = "Normal"
    elif value["value"] == "Off":
        value["value"] = "Tripped"
    return value


def _rack_security_state_value(state, type_name):
    """Return display-friendly rack door and lock state labels."""
    available = bool(getattr(state, "available", True))
    raw_value = getattr(state, "value", None)
    if not available:
        return {
            "available": False,
            "value": None,
            "attributes": {
                "raw_state": _json_safe(raw_value),
                "state_source": "rack_security",
                "telemetry_source": "json_rpc",
            },
        }
    return {
        "available": True,
        "value": _rack_security_state_label(raw_value, type_name),
        "attributes": {
            "raw_state": _json_safe(raw_value),
            "state_source": "rack_security",
            "telemetry_source": "json_rpc",
        },
    }


def _rack_security_state_label(value, type_name):
    name = _enum_name(value)
    if type_name == "DOOR_STATE":
        if name in {"0", "false", "open", "opened"}:
            return "Open"
        if name in {"1", "true", "closed", "close"}:
            return "Closed"
    if type_name in {"DOOR_LOCK_STATE", "DOOR_HANDLE_LOCK"}:
        if name in {"0", "false", "open", "opened", "unlocked", "unlock"}:
            return "Unlocked"
        if name in {"1", "true", "closed", "close", "locked", "lock"}:
            return "Locked"
    return name.replace("_", " ").title() if name else "Unknown"


def _binary_state_label(value):
    if value is None:
        return "Unknown"
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, (int, float)):
        return "On" if value else "Off"
    name = _enum_name(value)
    if name in {"on", "closed", "close", "active", "1", "true"}:
        return "On"
    if name in {"off", "open", "inactive", "0", "false"}:
        return "Off"
    return name.replace("_", " ").title() if name else "Unknown"


def _minmax_attrs(minmax):
    """Return JSON-safe minimum and maximum reading details."""
    valid = getattr(minmax, "valid", False)
    minimum = getattr(minmax, "minReading", None)
    minimum_at = _timestamp(getattr(minmax, "minReadingTimestamp", None))
    maximum = getattr(minmax, "maxReading", None)
    maximum_at = _timestamp(getattr(minmax, "maxReadingTimestamp", None))
    observed_since = _timestamp(getattr(minmax, "observedSince", None))
    return {
        "extrema_supported": True,
        "extrema_valid": valid,
        "minimum_recorded_value": minimum,
        "minimum_recorded_at": minimum_at,
        "maximum_recorded_value": maximum,
        "maximum_recorded_at": maximum_at,
        "extrema_observed_since": observed_since,
        "extrema_last_read_at": datetime.now(timezone.utc).isoformat(),
        "minimum_reading": minimum,
        "minimum_reading_timestamp": minimum_at,
        "maximum_reading": maximum,
        "maximum_reading_timestamp": maximum_at,
    }


def _minmax_error_attrs(err):
    """Return explicit extrema support details when a sensor rejects min/max."""
    return {
        "extrema_supported": False,
        "extrema_valid": False,
        "minimum_recorded_value": None,
        "minimum_recorded_at": None,
        "maximum_recorded_value": None,
        "maximum_recorded_at": None,
        "extrema_observed_since": None,
        "extrema_last_read_at": datetime.now(timezone.utc).isoformat(),
        "extrema_error": str(err),
    }


def _alerted_sensor_attrs(sensor_data):
    """Return JSON-safe details for an actively alerted sensor."""
    return {
        "sensor_target": getattr(sensor_data.sensor, "target", None),
        "parent_target": getattr(sensor_data.parent, "target", None),
        "alert_state": _enum_name(sensor_data.alertState),
    }


def _alarm_attrs(alarm):
    """Return JSON-safe acknowledgement-required alarm details."""
    return {
        "id": alarm.id,
        "name": alarm.name,
        "action_id": alarm.actionId,
        "alerts": [
            {
                "event_condition": alert.eventCondition,
                "message": alert.message,
                "first_appearance": _timestamp(alert.firstAppearance),
                "last_appearance": _timestamp(alert.lastAppearance),
                "count": alert.numberAlerts,
            }
            for alert in alarm.alerts
        ],
    }


def _event_action_attrs(action):
    """Return JSON-safe event action details with sensitive arguments redacted."""
    return {
        "id": str(getattr(action, "id", "")),
        "name": getattr(action, "name", ""),
        "type": getattr(action, "type", ""),
        "is_system": bool(getattr(action, "isSystem", False)),
        "arguments": _redacted_key_values(getattr(action, "arguments", [])),
    }


def _event_rule_attrs(rule, actions_by_id):
    """Return JSON-safe event rule details."""
    action_ids = [str(action_id) for action_id in getattr(rule, "actionIds", []) or []]
    return {
        "id": str(getattr(rule, "id", "")),
        "name": getattr(rule, "name", ""),
        "enabled": bool(getattr(rule, "isEnabled", False)),
        "system": bool(getattr(rule, "isSystem", False)),
        "auto_rearm": bool(getattr(rule, "isAutoRearm", False)),
        "has_matched": bool(getattr(rule, "hasMatched", False)),
        "action_ids": action_ids,
        "actions": [
            {
                "id": action_id,
                "name": actions_by_id.get(action_id, {}).get("name"),
                "type": actions_by_id.get(action_id, {}).get("type"),
            }
            for action_id in action_ids
        ],
        "condition": _condition_attrs(getattr(rule, "condition", None)),
        "arguments": _redacted_key_values(getattr(rule, "arguments", [])),
    }


def _condition_attrs(condition):
    """Return concise event-rule condition details."""
    if condition is None:
        return {}
    nested = [_condition_attrs(item) for item in getattr(condition, "conditions", []) or []]
    return {
        "negate": bool(getattr(condition, "negate", False)),
        "operation": _enum_name(getattr(condition, "operation", None)),
        "match_type": _enum_name(getattr(condition, "matchType", None)),
        "event_id": list(getattr(condition, "eventId", []) or []),
        "conditions": nested,
    }


def _datapush_entry_attrs(entry_id, settings, status):
    """Return JSON-safe data push entry details with credentials redacted."""
    mqtt_settings = getattr(settings, "mqttSettings", None)
    return {
        "id": entry_id,
        "url": _redact_url(getattr(settings, "url", "")),
        "type": _enum_name(getattr(settings, "type", None)),
        "use_auth": bool(getattr(settings, "useAuth", False)),
        "username": "set" if getattr(settings, "username", "") else "",
        "password": "redacted" if getattr(settings, "password", "") else "",
        "allow_off_time_range_certs": bool(getattr(settings, "allowOffTimeRangeCerts", False)),
        "item_count": len(getattr(settings, "items", []) or []),
        "items": list(getattr(settings, "items", []) or [])[:40],
        "mqtt_topic_prefix": getattr(mqtt_settings, "topicPrefix", "") if mqtt_settings else "",
        "status": _json_safe(status) if status is not None else None,
    }


def _matching_datapush_entry_id(entries, settings):
    """Return an existing Data Push entry matching URL, type, and topic prefix."""
    desired_url = getattr(settings, "url", "")
    desired_type = getattr(settings, "type", None)
    desired_topic = getattr(getattr(settings, "mqttSettings", None), "topicPrefix", "")
    for entry_id, current in _iter_map(entries):
        current_topic = getattr(getattr(current, "mqttSettings", None), "topicPrefix", "")
        if (
            getattr(current, "url", "") == desired_url
            and getattr(current, "type", None) == desired_type
            and current_topic == desired_topic
        ):
            return entry_id
    return None


def _mqtt_topic_prefix(value):
    """Return a normalized MQTT topic prefix ending with a slash."""
    prefix = str(value or "").strip().strip("/")
    if not prefix:
        return ""
    return f"{prefix}/"


def _mqtt_payload_summary(payload):
    """Return a compact dashboard-safe summary of an MQTT payload."""
    if isinstance(payload, dict):
        keys = list(payload.keys())[:8]
        summary = {"keys": keys}
        for key in ("event", "type", "name", "sensor", "state", "value", "severity", "timestamp"):
            if key in payload:
                summary[key] = _json_safe(payload[key])
        return summary
    if isinstance(payload, list):
        return {"items": len(payload), "first": _json_safe(payload[0]) if payload else None}
    text = str(payload)
    return text[:500]


def _redacted_key_values(values):
    """Return SDK KeyValue arguments while hiding secrets."""
    result = []
    for item in values or []:
        key = str(getattr(item, "key", ""))
        value = getattr(item, "value", "")
        lowered = key.lower()
        if any(token in lowered for token in ("password", "secret", "token", "credential", "pin", "card", "uid")):
            value = "redacted"
        result.append({"key": key, "value": _json_safe(value)})
    return result


def _redact_url(value):
    """Hide inline credentials in a configured URL."""
    if not value:
        return value
    return re.sub(r"(://)([^/@:]+)(?::[^/@]*)?@", r"\1redacted@", str(value))


def _asset_tag_attrs(tag):
    """Return JSON-safe asset tag details for dashboard rack occupancy."""
    tag_id = (
        getattr(tag, "id", None)
        or getattr(tag, "tagId", None)
        or getattr(tag, "epc", None)
        or getattr(tag, "rawId", "")
    )
    name = (
        getattr(tag, "name", None)
        or getattr(tag, "assetName", None)
        or getattr(tag, "label", None)
        or getattr(tag, "userLabel", None)
    )
    return {
        "tag_id": tag_id,
        "name": name,
        "configured_name": name,
        "rack_unit_number": getattr(tag, "rackUnitNumber", None),
        "ru": (getattr(tag, "rackUnitNumber", 0) or 0) + 1,
        "slot_number": getattr(tag, "slotNumber", None),
        "raw_id": getattr(tag, "rawId", ""),
        "family": getattr(tag, "familyDesc", ""),
        "programmable": getattr(tag, "programmable", None),
        "description": getattr(tag, "description", None),
    }


def _asset_rack_unit_attrs(unit):
    """Return JSON-safe rack unit details from an asset strip."""
    settings = getattr(unit, "settings", None)
    return {
        "rack_unit_number": getattr(unit, "rackUnitNumber", None),
        "ru": (getattr(unit, "rackUnitNumber", 0) or 0) + 1,
        "rack_unit_position": getattr(unit, "rackUnitPosition", None),
        "rack_unit_relative_position": getattr(unit, "rackUnitRelativePosition", None),
        "type": _enum_name(getattr(unit, "type", None)),
        "size": getattr(unit, "size", None),
        "asset_strip_cascade_position": getattr(unit, "assetStripCascadePosition", None),
        "asset_strip_number_of_rack_units": getattr(unit, "assetStripNumberOfRackUnits", None),
        "led_operation_mode": _enum_name(getattr(settings, "opmode", None)),
        "led_mode": _enum_name(getattr(settings, "mode", None)),
        "led_color": _json_safe(getattr(settings, "color", None)),
    }


def _asset_log_record_attrs(record):
    """Return JSON-safe asset logger details."""
    return {
        "timestamp": _timestamp(getattr(record, "timestamp", None)),
        "type": _enum_name(getattr(record, "type", None)),
        "asset_strip_number": getattr(record, "assetStripNumber", None),
        "rack_unit_number": getattr(record, "rackUnitNumber", None),
        "ru": (getattr(record, "rackUnitNumber", 0) or 0) + 1,
        "rack_unit_position": getattr(record, "rackUnitPosition", None),
        "slot_number": getattr(record, "slotNumber", None),
        "tag_id": getattr(record, "tagId", None),
        "parent_blade_id": getattr(record, "parentBladeId", None),
        "state": _enum_name(getattr(record, "state", None)),
    }


def _asset_tags_from_log_records(records):
    """Derive current tag occupancy from asset logger connect/disconnect records."""
    tags = {}
    for record in records:
        tag_id = record.get("tag_id")
        if not tag_id:
            continue
        event_type = record.get("type")
        if event_type == "asset_tag_disconnected":
            tags.pop(tag_id, None)
            continue
        if event_type != "asset_tag_connected":
            continue
        rack_unit_number = record.get("rack_unit_number")
        tags[tag_id] = {
            "tag_id": tag_id,
            "raw_id": tag_id,
            "name": tag_id,
            "configured_name": tag_id,
            "rack_unit_number": rack_unit_number,
            "ru": (rack_unit_number or 0) + 1 if rack_unit_number is not None and rack_unit_number >= 0 else None,
            "rack_unit_position": record.get("rack_unit_position"),
            "slot_number": record.get("slot_number"),
            "asset_strip_number": record.get("asset_strip_number"),
            "parent_blade_id": record.get("parent_blade_id"),
            "last_seen_at": record.get("timestamp"),
            "source": "asset_strip_logger",
        }
    return list(tags.values())


def _security_event_label(type_name, current):
    """Return a concise rack access event label."""
    if type_name == "DOOR_STATE":
        return "door_opened" if "open" in current else "door_closed"
    if type_name == "DOOR_LOCK_STATE":
        return "door_unlocked" if "unlock" in current else "door_locked"
    if type_name == "DOOR_HANDLE_LOCK":
        return "handle_unlocked" if "unlock" in current else "handle_locked"
    return "security_state_changed"


def _local_security_status(states):
    """Return a status from locally polled door and lock state sensors."""
    values = [str(value).lower() for value in states if value is not None]
    if any("open" in value for value in values):
        return "door_open"
    if any("unlock" in value for value in values):
        return "unlocked"
    if values:
        return "normal"
    return None


def _door_access_rules_attrs(rules):
    """Return redacted JSON-safe door access rules."""
    if isinstance(rules, dict):
        items = rules.items()
    else:
        items = enumerate(rules or [])
    return [
        {
            "id": rule_id,
            "name": getattr(rule, "name", ""),
            "door_handle_locks": _json_safe(getattr(rule, "doorHandleLocks", [])),
            "card_condition_1": _redact_security_condition(getattr(rule, "cardCondition1", None)),
            "card_condition_2": _redact_security_condition(getattr(rule, "cardCondition2", None)),
            "keypad_condition_1": _redact_security_condition(getattr(rule, "keypadCondition1", None)),
            "keypad_condition_2": _redact_security_condition(getattr(rule, "keypadCondition2", None)),
            "conditions_timeout": getattr(rule, "conditionsTimeout", None),
            "absolute_time": _json_safe(getattr(rule, "absoluteTime", None)),
            "periodic_time": _json_safe(getattr(rule, "periodicTime", None)),
        }
        for rule_id, rule in items
    ]


def _redact_security_condition(condition):
    """Return a JSON-safe smartlock condition without PINs or card IDs."""
    value = _json_safe(condition)
    if isinstance(value, dict):
        for key in list(value):
            if "pin" in key.lower() or "card" in key.lower() or "uid" in key.lower():
                value[key] = "redacted"
    return value


def _json_safe(value):
    """Return SDK structs, enums, and interfaces as JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, datetime):
        return _timestamp(value)
    if hasattr(value, "target"):
        return getattr(value, "target")
    fields = getattr(value, "elements", None)
    if fields:
        return {field: _json_safe(getattr(value, field, None)) for field in fields}
    return _enum_name(value)


def _enum_name(value):
    """Return the concise final component of an SDK enumeration."""
    return str(value).rsplit(".", 1)[-1].lower()


def _json_enum(value):
    """Return an SDK enum as concise JSON-safe text."""
    return _enum_name(value) if value is not None else None


def _power_line_name(value):
    """Return a display-safe electrical line name."""
    return _json_enum(value).upper() if value is not None else None


def _timestamp(value):
    """Return an ISO timestamp when an SDK time value is present."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _tcp_reachable(host, port, timeout=2):
    """Return whether a TCP port accepts a connection."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _error_value(err):
    return {
        "available": False,
        "value": None,
        "attributes": {"error": str(err)},
    }
