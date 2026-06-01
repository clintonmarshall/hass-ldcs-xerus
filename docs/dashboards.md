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

`tools/generate_current_rack_dashboard.py` builds the active single-rack dashboard from the Home Assistant entity registry. It is intended for the current POC rack where one primary Xerus PDU exposes a linked PDU plus optional USystems RDHx telemetry.

`tools/generate_rack02_dashboard.py` remains as a historical Rack 02-specific reference.
