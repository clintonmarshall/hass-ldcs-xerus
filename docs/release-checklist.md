# Release Checklist

Before publishing a GitHub release:

1. Update `custom_components/ldcs/manifest.json` version.
2. Update README status and known limitations.
3. Run local validation:

```bash
python -m compileall -q custom_components/ldcs tools
node --check www/raritan-waveform-card.js
node --check www/raritan-cooling-card.js
node --check www/raritan-rack-visual-card.js
node --check www/raritan-outlet-load-card.js
python -m json.tool hacs.json > /dev/null
python -m json.tool custom_components/ldcs/manifest.json > /dev/null
python -m json.tool custom_components/ldcs/strings.json > /dev/null
```

4. Install in a test Home Assistant instance via HACS custom repository.
5. Add one PDU in `basic` profile.
6. Confirm sensors, switches, buttons, alarm summary, extrema, and logs.
7. Optionally build a manual-install zip:

```bash
python tools/package_release.py
```

8. Tag the release:

```bash
git tag v0.6.2
git push origin v0.6.2
```
