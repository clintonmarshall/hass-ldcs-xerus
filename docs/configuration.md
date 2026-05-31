# Configuration

## Fields

### Product Selection

- `product_type`: what you are adding: Xerus rack PDU, USystems RDHx cooling, or rack/dashboard only.

### Xerus Rack PDU

- `host`: IP address or DNS name of the Xerus device.
- `username`: Xerus account username.
- `password`: Xerus account password.
- `verify_ssl`: enable only if the device has a certificate trusted by Home Assistant.
- `profile`: discovery breadth.
- `scan_interval`: polling interval in seconds.

### USystems RDHx Cooling

- `host`: IP address or DNS name of the RDHx controller.
- `modbus_port`: Modbus TCP port, usually `502`.
- `modbus_slave_id`: Modbus slave ID.
- `scan_interval`: polling interval in seconds. Native Modbus telemetry is planned as the next adapter.

### Rack Metadata

- `rack_name`: rack or containment name.
- `rack_role`: device role within the rack, such as left PDU rail, right PDU rail, or cooling.
- `rack_position`: free-form rack position notes.
- `create_dashboard`: store dashboard generation intent with the config entry.

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
