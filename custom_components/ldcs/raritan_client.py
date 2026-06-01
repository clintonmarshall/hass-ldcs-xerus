"""Small synchronous client wrapper around the official Raritan SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
import re
from threading import RLock
from time import monotonic

from raritan import rpc
from raritan.rpc.BulkRequestHelper import perform_bulk
from raritan.rpc import assetmgrmodel, event, pdumodel, sensors

try:
    from raritan.rpc import cascading
except ImportError:
    cascading = None

try:
    from raritan.rpc import smartcard, smartlock
except ImportError:
    smartcard = None
    smartlock = None

from .prometheus import PrometheusCollector
from .redfish import RedfishClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

BULK_CHUNK_SIZE = 100
METADATA_REFRESH_INTERVAL = 300
MINMAX_REFRESH_INTERVAL = 300
WAVEFORM_REFRESH_INTERVAL = 300

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
    ):
        """Initialize the client."""
        self.host = host
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.profile = profile
        self.device_identifier = device_identifier
        self.agent = None
        self.pdu = None
        self.cascade_manager = None
        self.asset_logger = None
        self.alerted_sensor_manager = None
        self.alarm_manager = None
        self.prometheus = PrometheusCollector(host, username, password, verify_ssl)
        self.redfish = RedfishClient(host, username, password, verify_ssl)
        self._lock = RLock()
        self.sensor_descriptors: list[SensorDescriptor] = []
        self._descriptors_by_key: dict[str, SensorDescriptor] = {}
        self._sensors_by_key = {}
        self._metadata = {}
        self._waveform_sources = {}
        self._waveform_cache = {}
        self._last_waveform_refresh = 0.0
        self._minmax_cache = {}
        self._last_minmax_refresh = 0.0
        self._security_interfaces = {}
        self._security_state_last = {}
        self._security_events = []
        self._asset_strip = None
        self._outlet_state_devices_by_key = {}
        self._outlet_details = {}
        self._ocp_details = {}
        self._poles_by_target = {}
        self._last_discovery = 0.0

    @property
    def device_info(self):
        """Return Home Assistant device info."""
        return self._device_info_for_metadata(self._metadata, 0)

    def _device_info_for_metadata(self, metadata, link_id=0):
        """Return Home Assistant device info for the primary or a linked PDU."""
        serial = metadata.get("serial_number") or f"{self.host}-link-{link_id}"
        if link_id in (0, 1):
            identifier = self.device_identifier or serial or self.host
            name = metadata.get("name") or metadata.get("model") or f"Xerus device {self.host}"
        else:
            identifier = serial or f"{self.device_identifier or self.host}-link-{link_id}"
            name = metadata.get("name") or metadata.get("model") or f"Linked Xerus PDU {link_id}"
        return {
            "identifiers": {(DOMAIN, identifier)},
            "manufacturer": metadata.get("manufacturer") or "Legrand",
            "model": metadata.get("model"),
            "name": name,
            "sw_version": metadata.get("fw_revision"),
            "configuration_url": f"https://{self.host}",
        }

    @property
    def mqtt_topic(self):
        """Return the dedicated MQTT topic wildcard for this PDU."""
        return f"raritan/{_slug(self.host)}/#"

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
                self._waveform_sources = {}
                self._outlet_state_devices_by_key = {}
                self._outlet_details = {}
                self._ocp_details = {}
                self._poles_by_target = {}
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
                self._collect_peripherals(descriptors)
                self._collect_asset_logger(descriptors)
                self._collect_asset_inventory(descriptors)
                self._collect_alarm_summary(descriptors)
                self._collect_security_summary(descriptors)
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
            asset_inventory = self._asset_inventory_value()
            for descriptor in asset_inventory_descriptors:
                data[descriptor.key] = asset_inventory

        if alarm_descriptors:
            data.update(self._read_alarm_summary(alarm_descriptors))

        self._track_security_state_events(data)

        if security_descriptors:
            data.update(self._read_security_summary(security_descriptors))

        if waveform_descriptors:
            data.update(self._read_waveforms(waveform_descriptors))

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
                if not isinstance(response, Exception):
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
        statuses = self._link_unit_statuses()
        for link_id in range(2, 9):
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
            return {}
        try:
            status = self.cascade_manager.getStatus()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read PDU Link status on %s: %s", self.host, err)
            return {}
        result = {}
        for unit in getattr(status, "linkUnits", []) or []:
            link_id = getattr(unit, "linkId", getattr(unit, "id", None))
            if link_id is None:
                continue
            result[int(link_id)] = _json_safe(unit)
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

    def _collect_children(self, descriptors, label, getter, pdu_id=0, device_info=None, base_attributes=None):
        try:
            children = getter()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read %s list from %s: %s", label, self.host, err)
            return
        for index, child in enumerate(children, start=1):
            context = f"{label} {index}"
            attributes = {**(base_attributes or {})}
            if not (label == "Outlet" and index != 1):
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

    def _collect_peripherals(self, descriptors):
        try:
            manager = self.pdu.getPeripheralDeviceManager()
            slots = manager.getDeviceSlots()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to read peripheral device slots on %s: %s", self.host, err)
            return

        for index, slot in enumerate(slots, start=1):
            try:
                settings = slot.getSettings()
                name = settings.name or f"Peripheral {index}"
                device = slot.getDevice()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to read peripheral slot %s on %s: %s", index, self.host, err)
                continue
            if getattr(device, "device", None) is not None:
                self._add_sensor(
                    descriptors,
                    name,
                    "sensor",
                    device.device,
                    {
                        "sensor_name": settings.name,
                        "sensor_description": getattr(settings, "description", ""),
                        "sensor_slot": index,
                    },
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

    def _collect_asset_inventory(self, descriptors):
        """Add the visual asset strip inventory entity."""
        descriptors.append(
            SensorDescriptor(
                key=_slug(f"{self.host}_asset_strip_inventory"),
                name="Asset Strip Inventory",
                context="Asset strip",
                target="/model/assetstrip/0",
                kind=SensorKind.ASSET_INVENTORY,
                field="asset_strip_inventory",
                type_name="ASSET",
                unit_name=None,
                asset_field="asset_strip_inventory",
            )
        )

    def _asset_inventory_value(self):
        """Return rack-unit asset tag occupancy when an asset strip is exposed."""
        strip = self._asset_strip_interface()
        if strip is None:
            return {
                "available": True,
                "value": 0,
                "attributes": {
                    "asset_strip_status": "unsupported",
                    "rack_unit_count": 42,
                    "asset_tags": [],
                    "telemetry_source": "json_rpc",
                },
            }
        try:
            state = _enum_name(strip.getState())
            strip_info = strip.getStripInfo()
            tags = strip.getAllTags()
        except Exception as err:  # noqa: BLE001
            return _error_value(err)
        asset_tags = [_asset_tag_attrs(tag) for tag in tags]
        rack_unit_count = getattr(strip_info, "rackUnitCount", None) or 42
        return {
            "available": True,
            "value": len(asset_tags),
            "attributes": {
                "asset_strip_status": state,
                "rack_unit_count": rack_unit_count,
                "asset_tags": asset_tags,
                "main_tag_count": getattr(strip_info, "mainTagCount", None),
                "blade_tag_count": getattr(strip_info, "bladeTagCount", None),
                "max_main_tag_count": getattr(strip_info, "maxMainTagCount", None),
                "max_blade_tag_count": getattr(strip_info, "maxBladeTagCount", None),
                "blade_overflow": getattr(strip_info, "bladeOverflow", None),
                "telemetry_source": "json_rpc",
            },
        }

    def _asset_strip_interface(self):
        """Return the first asset strip target that responds."""
        if self._asset_strip is not None:
            return self._asset_strip
        for target in (
            "/model/assetstrip/0",
            "/model/assetstrip",
            "/model/assetstrips/0",
            "/model/assetstrip/1",
            "/model/assetstrip/2",
        ):
            try:
                strip = assetmgrmodel.AssetStrip(target, self.agent)
                strip.getState()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Unable to probe asset strip at %s on %s: %s", target, self.host, err)
                continue
            self._asset_strip = strip
            return strip
        return None

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

    def _add_sensor(self, descriptors, context, field, sensor, attributes=None, device=None, device_info=None):
        if not self._profile_includes(context, field):
            return

        if isinstance(sensor, sensors.NumericSensor):
            kind = SensorKind.NUMERIC
        elif isinstance(sensor, sensors.StateSensor):
            kind = SensorKind.STATE
        else:
            return

        target = sensor.target
        key = _slug(f"{self.host}_{target}_{field}")
        if key in self._sensors_by_key:
            return

        type_name, unit_name = _sensor_type_names(sensor)
        name = _pretty_name(context, field, type_name)
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
        ("Inlet", "Outlet", "OCP", "Transfer switch", "Power meter")
    )


def _pretty_name(context, field, type_name):
    field_name = re.sub(r"(?<!^)(?=[A-Z])", " ", field).replace("_", " ").title()
    if field_name.lower() == "sensor" and type_name:
        field_name = type_name.replace("_", " ").title()
    return f"{context} {field_name}"


def _slug(value):
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


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


def _requires_state_label(descriptor):
    return (
        _is_outlet_state_descriptor(descriptor)
        or _is_contact_state_descriptor(descriptor)
        or _is_ocp_trip_descriptor(descriptor)
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
    return {
        "extrema_valid": getattr(minmax, "valid", False),
        "minimum_reading": getattr(minmax, "minReading", None),
        "minimum_reading_timestamp": _timestamp(getattr(minmax, "minReadingTimestamp", None)),
        "maximum_reading": getattr(minmax, "maxReading", None),
        "maximum_reading_timestamp": _timestamp(getattr(minmax, "maxReadingTimestamp", None)),
        "extrema_observed_since": _timestamp(getattr(minmax, "observedSince", None)),
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


def _asset_tag_attrs(tag):
    """Return JSON-safe asset tag details for dashboard rack occupancy."""
    return {
        "rack_unit_number": getattr(tag, "rackUnitNumber", None),
        "ru": (getattr(tag, "rackUnitNumber", 0) or 0) + 1,
        "slot_number": getattr(tag, "slotNumber", None),
        "raw_id": getattr(tag, "rawId", ""),
        "family": getattr(tag, "familyDesc", ""),
        "programmable": getattr(tag, "programmable", None),
    }


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


def _error_value(err):
    return {
        "available": False,
        "value": None,
        "attributes": {"error": str(err)},
    }
