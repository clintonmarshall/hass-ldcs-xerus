# Dashboards

The dashboard files in `examples/` are examples from a working Rack 02 proof of concept. They contain real entity IDs from that environment and should not be installed blindly on another Home Assistant instance.

Use them as design references for:

- rack overview
- power and phase balance
- outlet mimic
- outlet load extrema
- power-quality waveform capture
- rack security
- cooling/RDHx visualization
- asset strip occupancy

## Optional Cards

The visual cards in `www/` are plain Lovelace custom elements:

- `custom:raritan-waveform-card`
- `custom:raritan-cooling-card`
- `custom:raritan-rack-visual-card`
- `custom:raritan-outlet-load-card`

They expect entity IDs to be passed in the card configuration.

## Future Dashboard Generator

The current `tools/generate_rack02_dashboard.py` script is Rack 02-specific. The next production step is a generic dashboard generator that reads Home Assistant entity registry/device metadata and asks for rack placement.
