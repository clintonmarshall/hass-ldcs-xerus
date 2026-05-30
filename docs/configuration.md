# Configuration

## Fields

- `host`: IP address or DNS name of the Xerus device.
- `username`: Xerus account username.
- `password`: Xerus account password.
- `verify_ssl`: enable only if the device has a certificate trusted by Home Assistant.
- `profile`: discovery breadth.
- `scan_interval`: polling interval in seconds.

## Profiles

### basic

Recommended for production-like POC use and fleets.

Includes common PDU, inlet, outlet, OCP, environmental, asset, alarm, security, waveform, and Redfish outlet control surfaces.

### power

Adds broader power telemetry while avoiding some of the noisiest fields.

### full

Discovers every exposed sensor. Useful for reverse engineering and model validation. Large fleets can create many thousands of entities.

## MQTT Datapush

MQTT is used as a refresh trigger. Xerus datapush can publish bursts of sensor data; the integration debounces those messages and asks Home Assistant to refresh the device.

The integration listens to:

```text
raritan/<device-host-slug>/#
raritan/#
```

## Prometheus

The integration prefers matching Prometheus feed values when available because they are efficient for polling. JSON-RPC remains the source for discovery, metadata, controls, alarms, extrema, and fallback readings.

## Redfish

Redfish is used for outlet power switches where the device advertises compatible `PowerEquipment` outlet controls.
