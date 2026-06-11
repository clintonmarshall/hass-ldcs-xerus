# Supported Devices

## Tested POC Scope

- Raritan PX4 and compatible Xerus virtual PDUs running firmware/API family `4.3.13`
- Server Technology / Legrand Xerus-style telemetry exposed through compatible APIs
- Redfish outlet switching where supported by the target device
- Xerus Modbus/TCP basic layout diagnostics where the Modbus service is enabled
- USystems RDHx cooling through the native LDCS Modbus profile

## Expected Xerus Features

The integration can use these device features when exposed:

- JSON-RPC
- Prometheus feed
- MQTT datapush
- Redfish outlet power control
- Modbus/TCP basic PDU parameter block
- asset strip logger and asset strip interfaces
- alarm manager and alerted sensor manager
- waveform capture

## Roadmap

Planned broader Legrand data-center support:

- Starline busway / CPM monitoring through Modbus or other local protocols
- rack-level topology and dashboard generation

Starline is not yet a first-class setup flow in this beta.
