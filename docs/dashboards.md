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

Generated dashboards use bundled copies served by the integration from
`/ldcs_static/` and register them as Lovelace module resources.

## Dashboard Generator

When `create_dashboard` is enabled in the setup flow, LDCS creates or updates a
storage-mode Lovelace dashboard for the rack using the currently registered LDCS
entities.

`tools/generate_current_rack_dashboard.py` remains as an offline POC helper for
the active single-rack dashboard from the Home Assistant entity registry.

`tools/generate_rack02_dashboard.py` remains as a historical Rack 02-specific reference.
