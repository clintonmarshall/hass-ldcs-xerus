#!/usr/bin/env python3
"""Create a Home Assistant custom-component zip for manual installs."""

from __future__ import annotations

from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "raritan_px4"
OUTPUT = ROOT / "dist" / "raritan_px4_custom_component.zip"


def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(COMPONENT.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            archive.write(path, path.relative_to(ROOT))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
