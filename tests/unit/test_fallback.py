from datetime import timedelta

import pytest

from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode, RoomState

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)
DELAY = 10  # minutes, default wait before the fallback
STEP = 2  # minutes, default interval of the stepwise fallback


def _three_groups() -> Controller:
    """Three rooms of different nominal power = three power classes, all equally cold."""
    return Controller(installation(room("a", power=500), room("b", power=700), room("c", power=900)))


def _heating(result) -> set[str]:  # noqa: ANN001
    return {rid for rid, c in result.commands.items() if c.mode == Mode.HEAT}


@pytest.mark.req("FR-SAFE-04")
def test_units_stay_unchanged_while_waiting_for_the_planner() -> None:
    ctrl = _three_groups()
    temps = {"a": 20.0, "b": 20.0, "c": 20.0}
    for minute in (0, 1, 5, DELAY - 1):
        result = ctrl.step(T0 + minute * MIN, None, states(temps))
        assert not result.fallback
        assert result.plan_missing_s == minute * 60
        assert {c.mode for c in result.commands.values()} == {Mode.FAN}  # nothing is switched
    running = {rid: RoomState(Mode.HEAT, 20.0) for rid in temps}
    result = ctrl.step(T0 + 4 * MIN, None, running)
    assert {c.mode for c in result.commands.values()} == {Mode.HEAT}  # running units stay on


@pytest.mark.req("FR-SAFE-04")
def test_plan_returning_within_the_wait_changes_nothing() -> None:
    ctrl = _three_groups()
    temps = {"a": 23.0, "b": 23.0, "c": 23.0}
    ctrl.step(T0, None, states(temps))
    back = T0 + 5 * MIN
    result = ctrl.step(back, plan(0, back), states(temps))
    assert not result.fallback and result.plan_missing_s == 0
    # a new failure starts the wait again, it does not continue the old one
    result = ctrl.step(back + MIN, None, states(temps))
    assert result.plan_missing_s == 0 and not result.fallback
    result = ctrl.step(back + (1 + DELAY - 1) * MIN, None, states(temps))
    assert not result.fallback


@pytest.mark.req("FR-SAFE-04")
def test_fallback_switches_groups_to_heating_step_by_step() -> None:
    ctrl = _three_groups()
    temps = {"a": 20.0, "b": 20.0, "c": 20.0}
    ctrl.step(T0, None, states(temps))
    seen = []
    for offset in (0, STEP, 2 * STEP, 3 * STEP):
        result = ctrl.step(T0 + (DELAY + offset) * MIN, None, states(temps))
        assert result.fallback
        seen.append(_heating(result))
    assert seen == [
        {"a"},
        {"a", "b"},
        {"a", "b", "c"},
        {"a", "b", "c"},
    ]  # configured order on equal deviation
    result = ctrl.step(T0 + (DELAY + STEP) * MIN, None, states(temps))
    assert result.commands["b"].target_c == 21.0  # standard setpoint


@pytest.mark.req("FR-SAFE-04")
def test_fallback_starts_with_the_largest_deviation() -> None:
    ctrl = _three_groups()
    temps = {"a": 20.0, "b": 18.0, "c": 20.0}
    ctrl.step(T0, None, states(temps))
    result = ctrl.step(T0 + DELAY * MIN, None, states(temps))
    assert _heating(result) == {"b"}


@pytest.mark.req("FR-SAFE-04")
def test_fallback_keeps_units_that_already_run() -> None:
    ctrl = _three_groups()
    temps = {"a": 20.0, "b": 20.0, "c": 20.0}
    current = {
        "a": RoomState(Mode.FAN, 20.0),
        "b": RoomState(Mode.HEAT, 20.0),
        "c": RoomState(Mode.FAN, 20.0),
    }
    ctrl.step(T0, None, current)
    result = ctrl.step(T0 + DELAY * MIN, None, current)
    assert result.commands["b"].mode == Mode.HEAT  # not switched off while the ramp starts with a
    assert result.commands["a"].mode == Mode.HEAT and result.commands["c"].mode == Mode.FAN
    assert set(temps) == set(result.commands)


@pytest.mark.req("FR-SAFE-04")
def test_stale_plan_waits_like_a_missing_plan() -> None:
    ctrl = _three_groups()
    temps = {"a": 20.0, "b": 20.0, "c": 20.0}
    old = plan(2000, now=T0 - 2 * timedelta(hours=1))  # older than the maximum plan age
    first = ctrl.step(T0, old, states(temps))
    assert not first.fallback and first.plan_missing_s == 0
    result = ctrl.step(T0 + DELAY * MIN, old, states(temps))
    assert result.fallback and _heating(result) == {"a"}


@pytest.mark.req("FR-SAFE-02")
def test_hard_minimum_heats_at_once_while_waiting_and_in_fallback() -> None:
    ctrl = _three_groups()
    temps = {"a": 20.0, "b": 20.0, "c": 18.0}  # c is below the hard minimum (21 - 2 K)
    result = ctrl.step(T0, None, states(temps))
    assert not result.fallback and _heating(result) == {"c"}
    result = ctrl.step(T0 + DELAY * MIN, None, states(temps))
    assert _heating(result) == {"c"}  # the ramp starts with the largest deviation, which is c
    result = ctrl.step(T0 + (DELAY + STEP) * MIN, None, states(temps))
    assert _heating(result) == {"a", "c"}


@pytest.mark.req("FR-SAFE-01")
def test_open_window_room_is_not_switched_on_by_the_ramp() -> None:
    ctrl = _three_groups()
    temps = {"a": 20.0, "b": 20.0, "c": 20.0}
    ctrl.step(T0, None, states(temps, a=True))
    result = ctrl.step(T0 + (DELAY + 6) * MIN, None, states(temps, a=True))
    assert result.commands["a"].mode == Mode.FAN and _heating(result) == {"b", "c"}


@pytest.mark.req("FR-SAFE-04")
def test_waiting_and_step_intervals_are_parameters() -> None:
    ctrl = Controller(
        installation(room("a", power=500), room("b", power=700), fallback_delay_s=120, fallback_step_s=30)
    )
    temps = {"a": 20.0, "b": 20.0}
    ctrl.step(T0, None, states(temps))
    assert not ctrl.step(T0 + timedelta(seconds=119), None, states(temps)).fallback
    assert _heating(ctrl.step(T0 + timedelta(seconds=120), None, states(temps))) == {"a"}
    assert _heating(ctrl.step(T0 + timedelta(seconds=150), None, states(temps))) == {"a", "b"}
