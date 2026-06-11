# Legrand Data Center Solutions for Home Assistant

Beta Home Assistant custom integration for Legrand Data Center Solutions products.

The integration domain is `ldcs`. Xerus-based rack PDUs are the first supported platform because they provide a strong common base across Raritan, Server Technology, and related Legrand power products. The package is intentionally shaped as a broader LDCS integration so it can grow into USystems RDHx cooling, Starline power monitoring, Modbus devices, Redfish-capable products, MQTT datapush workflows, and other datacenter protocols without carrying an old product-specific identity.

## Current Capabilities

- Guided UI setup for Xerus rack PDUs, USystems RDHx cooling, and rack/dashboard entries.
- Rack metadata capture: rack name, rack role, rack position, and generated rack dashboards.
- Xerus JSON-RPC discovery using the official `raritan` Python SDK.
- Prometheus-backed telemetry polling where available, with JSON-RPC fallback.
- MQTT datapush wake-up support for faster refresh after Xerus events.
- Redfish outlet switching where supported by the PDU.
- Optional Xerus Modbus/TCP layout diagnostics for BMS/fallback planning.
- Numeric sensors with PDU-maintained min/max readings and timestamps.
- Button to reset all numeric sensor minimum/maximum values on a PDU.
- Alarm summary sensors from Xerus alerted sensor and alarm managers.
- Rack security diagnostics from door, handle, lock, and smartlock/rule polling where exposed.
- Power-quality waveform capture and local Lovelace waveform visualization.
- Asset strip inventory diagnostics where the Xerus asset strip interface is exposed.

## Installation With HACS

This is intended for HACS custom repository installation while it is in beta.

1. In Home Assistant, open HACS.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add this repository URL.
4. Choose category **Integration**.
5. Install **Legrand Data Center Solutions**.
6. Restart Home Assistant.
7. Go to **Settings -> Devices & services -> Add integration**.
8. Search for **Legrand Data Center Solutions**.
9. Choose **Xerus rack PDU**, **USystems RDHx cooling**, or **Rack/dashboard only**.

See [docs/installation.md](docs/installation.md) for manual install and generated dashboard behavior.

## Discovery Profiles

- `basic`: recommended for fleets. Inlet summary, outlet active power/state, environmental sensors, OCP state, asset/alarm/security summaries.
- `power`: broader electrical telemetry without the heaviest pole-level detail.
- `full`: all discovered sensors. Useful for exploration, but can create many entities.

For large fleets, start with `basic`.

## Bundled Lovelace Cards

This repo includes local visual cards in [`www/`](www/) and bundles copies inside
the integration package for generated dashboards:

- `raritan-waveform-card.js`
- `raritan-cooling-card.js`
- `raritan-rack-visual-card.js`
- `raritan-outlet-load-card.js`

When dashboard generation is enabled, LDCS serves them from `/ldcs_static/` and
registers them as Lovelace module resources.

## Status

This is a beta/POC package. It is useful now for Xerus-based PDU testing, but it is not yet a polished HACS default-store integration.

Known beta edges:

- Dashboard examples are environment-specific and should be treated as patterns.
- Smartlock event history varies by Xerus model/firmware; door and lock state transitions are tracked by polling.
- USystems RDHx native Modbus telemetry uses the host, port, and slave ID entered in the setup flow.
- Xerus Modbus/TCP support is diagnostic/read-only in this beta.
- Starline support is currently a roadmap item, not a native integration setup flow.

## Project Direction

Short term: make the Xerus PDU platform solid and HACS-installable.

Medium term: add normalized rack/dashboard models for cooling, rack security, asset occupancy, and power quality.

Long term: grow this into a broader Legrand Data Center Solutions integration with protocol adapters for Xerus, RDHx Modbus, Starline, Redfish-capable products, and related local protocols.

See [docs/architecture.md](docs/architecture.md).

New to publishing on GitHub? See [docs/github-publishing.md](docs/github-publishing.md).

## License

MIT. See [LICENSE](LICENSE).
