#!/usr/bin/env python3
"""Fail if the functional spec mentions technology (keeps WHAT and HOW separate)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN = [
    r"home assistant",
    r"\bhacs\b",
    r"\bpython\b",
    r"pytest",
    r"\byaml\b",
    r"\bjson\b",
    r"docker",
    r"devcontainer",
    r"\bentit",
    r"custom_component",
    r"config[ _]entry",
    r"\bmqtt\b",
    r"\brest\b",
    r"\bapi\b",
    r"\bclimate\.",
    r"\bsensor\.",
    r"input_\w+",
    r"\bautomation\.",
    r"\bscript\.",
    r"blueprint",
    r"semantic[- ]release",
    r"github",
]
PATTERN = re.compile("|".join(FORBIDDEN), re.IGNORECASE)


def main(root: Path = Path("docs/spec/functional")) -> int:
    bad: list[str] = []
    for path in sorted(root.glob("*.md")):
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in PATTERN.finditer(line):
                bad.append(f"{path}:{no}: Technologiebegriff '{m.group(0)}'")
    if bad:
        print("\n".join(bad))
        print(f"\n{len(bad)} Verstoß/Verstöße: Fachspec muss technologiefrei sein.")
        return 1
    print("Fachspec ist technologiefrei.")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])) if len(sys.argv) > 1 else main())
