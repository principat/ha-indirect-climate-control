#!/usr/bin/env python3
"""Every requirement with status 'beschlossen' needs tests on every listed level.

Tests mark themselves with @pytest.mark.req("FR-XYZ-01"); the level is the folder
(tests/unit, tests/integration, tests/e2e).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQ_FILE = Path("docs/spec/functional/03-requirements.md")
ROW = re.compile(r"^\|\s*((?:FR|NF)-[A-Z]+-\d+)\s*\|(.+)\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$")
MARK = re.compile(r"""req\(\s*["']((?:FR|NF)-[A-Z]+-\d+)["']\s*\)""")
LEVELS = ("unit", "integration", "e2e")


def requirements() -> dict[str, tuple[str, set[str]]]:
    reqs: dict[str, tuple[str, set[str]]] = {}
    for line in REQ_FILE.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line)
        if m:
            levels = {x.strip() for x in m.group(4).split(",") if x.strip()}
            reqs[m.group(1)] = (m.group(3), levels)
    return reqs


def coverage() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for level in LEVELS:
        for path in Path("tests", level).rglob("test_*.py"):
            for rid in MARK.findall(path.read_text(encoding="utf-8")):
                found.setdefault(rid, set()).add(level)
    return found


def main() -> int:
    reqs, found = requirements(), coverage()
    problems: list[str] = []
    for rid in sorted(found):
        if rid not in reqs:
            problems.append(f"{rid}: Test verweist auf unbekannte Anforderung")
    for rid, (status, levels) in sorted(reqs.items()):
        if status != "beschlossen":
            continue
        missing = sorted(levels - found.get(rid, set()))
        if missing:
            problems.append(f"{rid}: fehlende Testebene(n): {', '.join(missing)}")
    decided = sum(1 for s, _ in reqs.values() if s == "beschlossen")
    print(f"{decided} beschlossene Anforderungen, {len(problems)} Lücken.")
    if problems:
        print("\n".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
