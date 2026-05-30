# Legrand Data Center Home Assistant Integration

## Recommendation

Evolve the current `raritan_px4` prototype into a new `legrand_datacenter`
custom integration. Keep protocol-specific clients behind a shared device model
instead of adding Modbus handling directly to `RaritanClient`.

The package should model a rack as a composition of products:

- Xerus-based Raritan and Server Technology PDUs
- USystems cooling devices such as ColdLogik RDHx
- Starline Critical Power Monitors and busway tap-off meters
- Future Legrand products with a supported local protocol

## Why Rename Now

The current domain is product-specific:

```text
raritan_px4
```

The planned scope is a Legrand data-center system rather than one PDU family:

```text
legrand_datacenter
```

Renaming early avoids publishing a broad integration with PX4 terminology baked
into entity IDs, MQTT topics, diagnostics, documentation, and config flows.

## Proposed Structure

```text
custom_components/legrand_datacenter/
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

## Migration

1. Freeze `raritan_px4` feature development after the current phase support.
2. Scaffold `legrand_datacenter` with the shared model and Xerus adapter.
3. Add entity-registry migration for existing PX4 entity IDs where possible.
4. Add the USystems RDHx profile from the validated YAML register map.
5. Run the new RDHx adapter read-only beside the YAML configuration.
6. Compare values and alarms, then remove the YAML Modbus include.
7. Add Starline CPM once its model and register map are available.
8. Generate rack dashboards from normalized topology rather than product names.

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

