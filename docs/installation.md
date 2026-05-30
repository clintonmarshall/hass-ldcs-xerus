# Installation

## HACS Custom Repository

1. Open HACS in Home Assistant.
2. Open **Custom repositories**.
3. Paste the GitHub repository URL.
4. Select category **Integration**.
5. Install **Legrand Data Center Solutions**.
6. Restart Home Assistant.
7. Add the integration from **Settings -> Devices & services -> Add integration -> Legrand Data Center Solutions**.

## Manual Installation

Copy this folder:

```text
custom_components/ldcs
```

to:

```text
/config/custom_components/ldcs
```

Restart Home Assistant and add the integration from the UI.

## Optional Frontend Cards

The custom Lovelace cards are optional. Copy files from `www/` to:

```text
/config/www/
```

Then add Lovelace resources:

```text
/local/raritan-waveform-card.js
/local/raritan-cooling-card.js
/local/raritan-rack-visual-card.js
/local/raritan-outlet-load-card.js
```

Use resource type `module`.

## First Device

Use the smallest useful profile first:

```text
host: <PDU IP or hostname>
username: admin
password: <your password>
verify_ssl: false
profile: basic
scan_interval: 30
```

After the device is added, Home Assistant will create sensors, switches, buttons, and diagnostics based on what the device exposes.
