# Legrand Data Center Solutions Home Assistant Integration

## Direction

This package is the first public shape of the Legrand Data Center Solutions
Home Assistant integration. The Home Assistant domain is:

```text
ldcs
```

Xerus-based rack PDUs are the first supported platform. Future Legrand products
should be added as platform adapters behind a shared rack/device model instead
of turning the Xerus client into a catch-all implementation.

The package should model a rack as a composition of products:

- Xerus-based Raritan and Server Technology PDUs
- USystems cooling devices such as ColdLogik RDHx
- Starline Critical Power Monitors and busway tap-off meters
- Future Legrand products with a supported local protocol

## Why Start With LDCS

There are no public installs to preserve, so the first GitHub release should
use the broader LDCS identity from the beginning. That avoids publishing a
product-specific domain, entity namespace, config flow, and HACS package name
that would later need migration.

## Proposed Structure

```text
custom_components/ldcs/
  __init__.py
  config_flow.py
  coordinator.py
  const.py
  diagnostics.py
  manifest.json
  sensor.py
  binary_sensor.py
  switch.py
  button.py
  models.py
  entity_descriptions.py
  adapters/
    base.py
    xerus.py
    xerus_prometheus.py
    xerus_redfish.py
    xerus_mqtt.py
    usystems_modbus.py
    starline_modbus.py
  profiles/
    usystems_rdhx.py
    starline_cpm.py
```

## Shared Model

Every adapter should return the same normalized snapshot:

```python
@dataclass
class DeviceSnapshot:
    identity: DeviceIdentity
    measurements: dict[str, Measurement]
    alarms: dict[str, AlarmState]
    controls: dict[str, ControlState]
    topology: DeviceTopology
```

The topology should carry rack-facing context:

- rack name
- rack side or rail
- device role: PDU, cooling, busway feed, busway tap-off, sensor strip
- electrical lines: L1, L2, L3, neutral
- OCP and outlet relationships
- cooling zones, fans, valves, and leak detection points

This gives dashboards one stable vocabulary even when telemetry comes from
JSON-RPC, Prometheus, MQTT, Redfish, or Modbus.

## Protocol Adapters

### Xerus

Retain the current hybrid approach:

- JSON-RPC for discovery, metadata, alarms, thresholds, and waveform capture
- Prometheus for efficient metric polling
- MQTT push as a refresh signal
- Redfish for outlet switching

### USystems RDHx

Use a dedicated Modbus TCP adapter with product profiles. The existing Home
Assistant YAML proves the register map and is a good source for the initial
profile.

Read contiguous register blocks in bulk and decode them into normalized
measurements. Do not create one TCP request per entity.

Initial normalized groups:

- temperatures
- fan speed, command, and feedback
- valve request and feedback
- setpoints and operating limits
- unit state and lifetime
- alarms
- maintenance warnings

Keep writes disabled initially. Add opt-in controls after read-only telemetry
and alarm handling are verified.

### Starline CPM

Start with a Modbus TCP profile because the CPM supports standard monitoring
protocols and exposes electrical metering suitable for the existing rack
summary model.

Initial normalized groups:

- phase voltage and current
- active, apparent, and reactive power
- energy
- power factor
- neutral current where fitted
- breaker state
- temperature
- alarm state

## Home Assistant Devices

Create a Home Assistant device for each physical product. Where useful, create
child devices linked with `via_device`:

- PDU
  - inlet
  - OCP or breaker
  - outlet bank
- RDHx
  - cooling controller
  - leak detector
- Starline CPM
  - busway feed
  - monitored tap-off

Use stable hardware identifiers or serial numbers where available. For Modbus
devices without serial discovery, derive a stable identifier from product
family, host, port, and slave ID.

## Config Flow

Add devices through the UI:

1. Select product family.
2. Enter transport settings.
3. Test the connection.
4. Detect or select the product profile.
5. Assign optional rack metadata.

Connection fields belong in `ConfigEntry.data`. Rack placement, scan interval,
discovery profile, and opt-in controls belong in `ConfigEntry.options`.

## Implementation Path

1. Publish the current Xerus PDU support under the `ldcs` integration domain.
2. Refactor the Xerus client into an adapter behind a shared device snapshot.
3. Add the USystems RDHx profile from the validated YAML register map.
4. Run the new RDHx adapter read-only beside the YAML configuration.
5. Compare values and alarms, then remove the YAML Modbus include.
6. Add Starline CPM once its model and register map are available.
7. Generate rack dashboards from normalized topology rather than product names.

## Existing USystems Prototype

The current YAML prototype already covers:

- main and alternate temperature inputs
- fan and valve telemetry
- read-only setpoints and limits
- unit clock and lifetime
- global, leak, temperature, fan, valve, and maintenance alarm bits

The next implementation should preserve these entity names during migration
where practical, while grouping them under a USystems RDHx Home Assistant
device.
