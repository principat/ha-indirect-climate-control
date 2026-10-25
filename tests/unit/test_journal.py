"""FR-OBS-01: operating data is recorded when something changes."""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from custom_components.climate_control.core.journal import CommandRecord, Journal, UnitRecord
from custom_components.climate_control.record_file import append_records

from .helpers import T0

CONTEXT = {"season": "heat", "soc_pct": 40.0, "planned_w": 1500.0, "requested_w": 1300.0, "fallback": False}
FAN = UnitRecord("fan_only", 20.0, None, "auto")


@pytest.mark.req("FR-OBS-01")
def test_the_first_cycle_records_the_starting_state() -> None:
    rows = Journal().record(T0, False, {"a": FAN, "b": FAN}, CONTEXT)
    assert [r["event"] for r in rows] == ["plant", "unit", "unit"]
    assert rows[0]["running"] is False and rows[0]["soc_pct"] == 40.0
    assert rows[1] == {"time": T0.isoformat(), "event": "unit", "unit": "a", **FAN.__dict__}


@pytest.mark.req("FR-OBS-01")
def test_nothing_changed_nothing_recorded() -> None:
    journal = Journal()
    journal.record(T0, False, {"a": FAN}, CONTEXT)
    assert journal.record(T0 + timedelta(minutes=1), False, {"a": FAN}, CONTEXT) == []


@pytest.mark.req("FR-OBS-01")
def test_start_and_stop_carry_the_reasons_and_each_changed_unit_is_recorded_alone() -> None:
    journal = Journal()
    journal.record(T0, False, {"a": FAN, "b": FAN}, CONTEXT)
    heat = UnitRecord("heat", 20.0, 21.0, "auto")
    later = T0 + timedelta(minutes=5)
    started = journal.record(later, True, {"a": heat, "b": FAN}, {**CONTEXT, "season": "cool"})
    assert [(r["event"], r.get("unit")) for r in started] == [("plant", None), ("unit", "a")]
    assert started[0]["running"] is True and started[0]["season"] == "cool"
    assert started[1]["mode"] == "heat" and started[1]["target_c"] == 21.0 and started[1]["fan"] == "auto"
    warmer = UnitRecord("heat", 20.5, 21.0, "auto")  # the device temperature moved: recorded
    assert [
        r["unit"]
        for r in journal.record(later + timedelta(minutes=5), True, {"a": warmer, "b": FAN}, CONTEXT)
    ] == ["a"]
    stopped = journal.record(later + timedelta(minutes=15), False, {"a": warmer, "b": FAN}, CONTEXT)
    assert [r["event"] for r in stopped] == ["plant"] and stopped[0]["running"] is False


@pytest.mark.req("FR-OBS-01")
def test_the_outdoor_power_is_recorded_when_it_moves() -> None:
    journal = Journal()
    first = journal.record(T0, True, {"a": FAN}, CONTEXT, 1210.4)
    assert [r["event"] for r in first] == ["plant", "power", "unit"]
    assert first[1] == {"time": T0.isoformat(), "event": "power", "power_w": 1210.4}
    minute = timedelta(minutes=1)
    assert journal.record(T0 + minute, True, {"a": FAN}, CONTEXT, 1225.0) == []  # 15 W: inside the step
    moved = journal.record(T0 + 2 * minute, True, {"a": FAN}, CONTEXT, 1235.0)  # 25 W since the last record
    assert moved == [{"time": (T0 + 2 * minute).isoformat(), "event": "power", "power_w": 1235.0}]
    spike = journal.record(T0 + 3 * minute, True, {"a": FAN}, CONTEXT, 1970.0)
    assert [r["power_w"] for r in spike] == [1970.0]
    assert journal.record(T0 + 4 * minute, True, {"a": FAN}, CONTEXT, None) == []  # no reading: nothing


@pytest.mark.req("FR-OBS-01")
def test_the_command_of_the_control_is_recorded_when_it_changes() -> None:
    journal = Journal()
    minute = timedelta(minutes=1)
    serve = {"a": CommandRecord("heat", 19.5, 1), "b": CommandRecord("fan_only", None, 0)}
    first = journal.record(T0, True, {"a": FAN, "b": FAN}, CONTEXT, None, serve)
    assert [(r["event"], r.get("unit")) for r in first] == [
        ("plant", None),
        ("command", "a"),
        ("command", "b"),
        ("unit", "a"),
        ("unit", "b"),
    ]
    assert first[1] == {
        "time": T0.isoformat(),
        "event": "command",
        "unit": "a",
        "mode": "heat",
        "target_c": 19.5,
        "steps": 1,
    }
    assert journal.record(T0 + minute, True, {"a": FAN, "b": FAN}, CONTEXT, None, serve) == []
    handover = {"a": CommandRecord("heat", 19.5, 1), "b": CommandRecord("heat", 20.0, 1)}
    changed = journal.record(T0 + 2 * minute, True, {"a": FAN, "b": FAN}, CONTEXT, None, handover)
    assert [(r["event"], r["unit"]) for r in changed] == [("command", "b")]  # only the changed order
    assert changed[0]["mode"] == "heat" and changed[0]["target_c"] == 20.0 and changed[0]["steps"] == 1


@pytest.mark.req("FR-OBS-01")
def test_the_file_has_one_json_line_per_record_and_a_limited_size(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "entry.jsonl"
    rows = [{"time": "t", "event": "unit", "unit": "a", "mode": "heat"}]
    append_records(path, rows, max_bytes=200)
    append_records(path, rows, max_bytes=200)
    assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == rows * 2
    for _ in range(10):
        append_records(path, rows, max_bytes=200)
    assert path.stat().st_size <= 200 + 100  # rotated: the full file moved on, a new one started
    assert path.with_suffix(".jsonl.1").exists()
    assert len(list(path.parent.iterdir())) == 2  # never more than the current and the previous file
