import subprocess
import sys

import pytest


@pytest.mark.req("NF-SPEC-01")
def test_functional_spec_is_technology_free() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_spec_separation.py"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout
