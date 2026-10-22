import json
from pathlib import Path

import pytest


@pytest.mark.req("NF-REL-01")
def test_semantic_release_is_configured() -> None:
    rc = json.loads(Path(".releaserc.json").read_text(encoding="utf-8"))
    names = [p if isinstance(p, str) else p[0] for p in rc["plugins"]]
    for plugin in (
        "@semantic-release/commit-analyzer",
        "@semantic-release/release-notes-generator",
        "@semantic-release/changelog",
        "@semantic-release/exec",
        "@semantic-release/git",
        "@semantic-release/github",
    ):
        assert plugin in names
    assert "semantic-release" in Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
