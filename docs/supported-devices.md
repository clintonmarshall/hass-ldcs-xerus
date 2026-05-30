# Supported Devices

## Tested POC Scope

- Raritan PX4 / Xerus virtual PDUs running firmware/API family `4.3.13`
- Server Technology / Legrand Xerus-style telemetry exposed through compatible APIs
- Redfish outlet switching where supported by the target device

## Expected Xerus Features

The integration can use these device features when exposed:

- JSON-RPC
- Prometheus feed
- MQTT datapush
- Redfish outlet power control
- asset strip logger and asset strip interfaces
- alarm manager and alerted sensor manager
- waveform capture

## Roadmap

Planned broader Legrand data-center support:

- USystems RDHx cooling through a native Modbus profile
- Starline busway / CPM monitoring through Modbus or other local protocols
- rack-level topology and dashboard generation

Those roadmap devices are not yet first-class setup flows in this beta.
