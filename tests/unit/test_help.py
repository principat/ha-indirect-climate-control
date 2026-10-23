import json
from dataclasses import fields
from pathlib import Path

import pytest

from custom_components.climate_control.core.config import Parameters
from custom_components.climate_control.help import (
    PARAMETER_GROUPS,
    ROOM_HELP,
    USER_HELP,
    help_section_key,
    split_help,
)

BASE = Path("custom_components/climate_control")
FILES = [BASE / "strings.json", BASE / "translations" / "en.json", BASE / "translations" / "de.json"]
OPTIONS_HELP = tuple(f.name for f in fields(Parameters))


def _forms(data: dict) -> list[tuple[str, dict, tuple[str, ...]]]:  # type: ignore[type-arg]
    room = data["config_subentries"]["room"]["step"]
    return [
        ("user", data["config"]["step"]["user"], USER_HELP),
        ("reconfigure", data["config"]["step"]["reconfigure"], USER_HELP),
        ("room", room["user"], ROOM_HELP),
        ("room reconfigure", room["reconfigure"], tuple(f for f in ROOM_HELP if f != "entity_id")),
        *((f"options {g}", data["options"]["step"][g], names) for g, names in PARAMETER_GROUPS.items()),
    ]


@pytest.mark.req("FR-CFG-03")
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_non_trivial_field_has_a_help_text(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for name, step, help_fields in _forms(data):
        sections = step["sections"]
        for field in help_fields:
            section = sections[help_section_key(field)]
            assert field in step["data"], (name, field)
            assert len(section["description"]) >= 60, (name, field)
            assert section["name"] and section["data"]["help_expanded"], (name, field)
        assert set(sections) == {help_section_key(f) for f in help_fields}, name


@pytest.mark.req("FR-CFG-03")
def test_translations_have_identical_structure() -> None:
    def keys(node: object, prefix: str = "") -> set[str]:
        if isinstance(node, dict):
            return set().union(*(keys(v, f"{prefix}/{k}") for k, v in node.items())) | {prefix}
        return {prefix}

    reference = keys(json.loads(FILES[0].read_text(encoding="utf-8")))
    for path in FILES[1:]:
        assert keys(json.loads(path.read_text(encoding="utf-8"))) == reference, path.name


@pytest.mark.req("FR-CFG-03")
def test_help_switch_toggles_when_any_section_differs() -> None:
    values, expanded = split_help({"a": 1, "help_a": {"help_expanded": False}, "help_b": {}}, False)
    assert values == {"a": 1} and expanded is False
    assert (
        split_help({"help_a": {"help_expanded": True}, "help_b": {"help_expanded": False}}, False)[1] is True
    )
    assert split_help({"help_a": {"help_expanded": False}}, True)[1] is False
    assert split_help({"help_text": "not a section"}, True) == ({"help_text": "not a section"}, True)


@pytest.mark.req("FR-CFG-03")
def test_parameters_are_grouped_completely_and_once() -> None:
    grouped = [name for names in PARAMETER_GROUPS.values() for name in names]
    assert sorted(grouped) == sorted(OPTIONS_HELP)
    for path in FILES:
        menu = json.loads(path.read_text(encoding="utf-8"))["options"]["step"]["init"]["menu_options"]
        assert set(menu) == {"plan", *PARAMETER_GROUPS}, path.name
