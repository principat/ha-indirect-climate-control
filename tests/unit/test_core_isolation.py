"""NF-TEST-01 / architecture: the core must not depend on the platform."""

import re
from pathlib import Path

import pytest


@pytest.mark.req("NF-TEST-01")
def test_core_does_not_import_homeassistant() -> None:
    core = Path("custom_components/climate_control/core")
    offenders = [
        str(p)
        for p in core.rglob("*.py")
        if re.search(r"^\s*(from|import)\s+homeassistant", p.read_text(encoding="utf-8"), re.M)
    ]
    assert offenders == []
