#!/usr/bin/env python3
"""Write the release version (called by semantic-release prepareCmd)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main(version: str) -> None:
    manifest = Path("custom_components/climate_control/manifest.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = version
    manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pyproject = Path("pyproject.toml")
    text = pyproject.read_text(encoding="utf-8")
    pyproject.write_text(
        re.sub(r'^version = ".*?"', f'version = "{version}"', text, count=1, flags=re.M),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(sys.argv[1])
