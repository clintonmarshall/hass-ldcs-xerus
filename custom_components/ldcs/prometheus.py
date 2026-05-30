"""Prometheus telemetry support for Raritan Xerus devices."""

from __future__ import annotations

import json
import math
import re

import requests
from urllib3.exceptions import InsecureRequestWarning

PROMETHEUS_PATH = "/cgi-bin/dump_prometheus.cgi?include_names=1"

FIELD_METRICS = {
    "activeEnergy": "raritan_pdu_activeenergy_watthour_total",
    "activePower": "raritan_pdu_activepower_watt",
    "apparentPower": "raritan_pdu_apparentpower_voltampere",
    "current": "raritan_pdu_current_ampere",
    "lineFrequency": "raritan_pdu_linefrequency_hertz",
    "outletState": "raritan_pdu_outletstate",
    "powerFactor": "raritan_pdu_powerfactor",
    "state": "raritan_pdu_outletstate",
    "voltage": "raritan_pdu_voltage_volt",
}

PERIPHERAL_METRICS = {
    "CONTACT_CLOSURE": "raritan_pdu_peripheral_contact",
    "DOOR_STATE": "raritan_pdu_peripheral_doorstate",
    "DRY_CONTACT": "raritan_pdu_peripheral_drycontact",
    "HUMIDITY": "raritan_pdu_peripheral_relativehumidity_percent",
    "ON_OFF_SENSOR": "raritan_pdu_peripheral_contact",
    "POWERED_DRY_CONTACT": "raritan_pdu_peripheral_powereddrycontact",
    "TEMPERATURE": "raritan_pdu_peripheral_temperature_degreecelsius",
}

_SAMPLE_RE = re.compile(
    r"^(?P<metric>[a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(?P<labels>.*)\})?\s+(?P<value>\S+)"
)
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"])*)"')


class PrometheusCollector:
    """Fetch and query the native Xerus Prometheus feed."""

    def __init__(self, host, username, password, verify_ssl=False):
        """Initialize the collector."""
        self.url = f"https://{host}{PROMETHEUS_PATH}"
        self.auth = (username, password)
        self.verify_ssl = verify_ssl
        if not verify_ssl:
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    def read(self):
        """Return parsed samples grouped by metric name."""
        response = requests.get(
            self.url,
            auth=self.auth,
            verify=self.verify_ssl,
            timeout=10,
        )
        response.raise_for_status()
        return _parse_samples(response.text)

    @staticmethod
    def value_for_descriptor(samples, descriptor):
        """Return the matching sample for an existing JSON-RPC descriptor."""
        if descriptor.context == "PDU":
            return None

        metric = FIELD_METRICS.get(descriptor.field)
        if descriptor.field == "sensor":
            metric = PERIPHERAL_METRICS.get(descriptor.type_name)
        if metric is None:
            return None

        candidates = samples.get(metric, [])
        required = _context_labels(descriptor.context)
        if descriptor.field != "sensor" and not required:
            return None
        for sample in candidates:
            labels = sample["labels"]
            if any(labels.get(key) != value for key, value in required.items()):
                continue
            if "poleline" in labels and "Pole" not in descriptor.context:
                continue
            if descriptor.field == "sensor":
                sensor_name = labels.get("sensorname")
                if sensor_name and sensor_name != descriptor.context:
                    continue
            return sample
        return None

    @staticmethod
    def outlet_states(samples):
        """Return outlet state samples indexed by outlet ID."""
        states = {}
        for sample in samples.get("raritan_pdu_outletstate", []):
            outlet_id = sample["labels"].get("outletid")
            if outlet_id is not None:
                states[outlet_id] = sample
        return states


def _context_labels(context):
    """Convert SDK discovery context into native feed labels."""
    match = re.match(r"^Inlet (\d+)", context)
    if match:
        labels = {"inletid": f"I{match.group(1)}"}
        pole = re.search(r" Pole (\d+)", context)
        if pole:
            labels["poleline"] = f"L{pole.group(1)}"
        return labels

    match = re.match(r"^Outlet (\d+)", context)
    if match:
        return {"outletid": match.group(1)}

    return {}


def _parse_samples(text):
    """Parse the subset of Prometheus text exposition used by Xerus."""
    samples = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE_RE.match(line)
        if match is None:
            continue
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        labels = {
            key: json.loads(f'"{raw_value}"')
            for key, raw_value in _LABEL_RE.findall(match.group("labels") or "")
        }
        samples.setdefault(match.group("metric"), []).append(
            {
                "available": math.isfinite(value),
                "value": value if math.isfinite(value) else None,
                "labels": labels,
            }
        )
    return samples
