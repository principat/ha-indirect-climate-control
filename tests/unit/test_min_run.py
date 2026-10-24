from datetime import timedelta

import pytest

from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)
COLD = {"a": 20.0, "b": 20.0, "c": 20.0}


def _step(ctrl: Controller, minutes: float, kw: float):  # noqa: ANN202
    t = T0 + minutes * MIN
    return ctrl.step(t, plan(kw * 1000, t), states(COLD))


@pytest.mark.req("FR-PLAN-02")
def test_started_plant_runs_for_the_minimum_run_time_even_if_the_plan_drops() -> None:
    ctrl = Controller(installation())
    assert _step(ctrl, 0, 1.5).running
    for minute in (1, 3, 9.9):
        result = _step(ctrl, minute, 0.0)
        assert result.running and result.requested_w == 1300  # held at Pmin
        assert result.served and Mode.HEAT in {c.mode for c in result.commands.values()}
    result = _step(ctrl, 10, 0.0)
    assert not result.running and result.requested_w == 0
    assert {c.mode for c in result.commands.values()} == {Mode.FAN}


@pytest.mark.req("FR-PLAN-02")
def test_timer_runs_from_the_start_and_is_not_extended_by_load_changes() -> None:
    ctrl = Controller(installation())
    assert _step(ctrl, 0, 1.5).running
    for minute, kw in ((2, 0.0), (4, 3.0), (6, 0.2), (8, 2.0)):  # the plan jumps up and down
        assert _step(ctrl, minute, kw).running
    # 10 minutes after the start the plan decides again, whatever happened in between
    assert not _step(ctrl, 10, 0.0).running


@pytest.mark.req("FR-PLAN-02")
def test_there_is_no_minimum_pause_and_the_timer_restarts_at_every_start() -> None:
    ctrl = Controller(installation())
    assert _step(ctrl, 0, 1.5).running
    assert not _step(ctrl, 10, 0.0).running
    assert _step(ctrl, 10.2, 1.5).running  # restart right after the stop is allowed
    assert _step(ctrl, 15, 0.0).running  # the new run time counts from the restart (10.2 min)
    assert _step(ctrl, 20.1, 0.0).running
    assert not _step(ctrl, 20.3, 0.0).running


@pytest.mark.req("FR-PLAN-02")
def test_plan_between_the_thresholds_is_not_a_start_and_zero_does_not_hold() -> None:
    ctrl = Controller(installation())
    assert not _step(ctrl, 0, 1.0).running  # below the start threshold (1040 W)
    assert not _step(ctrl, 1, 0.0).running  # nothing to hold, the timer never started


@pytest.mark.req("FR-PLAN-02")
def test_minimum_run_time_is_a_parameter() -> None:
    ctrl = Controller(installation(room("a"), min_run_s=0))
    assert _step(ctrl, 0, 1.5).running
    assert not _step(ctrl, 1, 0.0).running  # 0 = off, back to the plain hysteresis


@pytest.mark.req("FR-PLAN-02")
def test_held_plant_serves_at_least_pmin_worth_of_rooms() -> None:
    cfg = installation(room("a", power=700), room("b", power=700), room("c", power=700))
    ctrl = Controller(cfg)
    first = _step(ctrl, 0, 3.0)
    assert len(first.served) == 3  # 3300 W requested: all rooms
    held = _step(ctrl, 3, 0.0)
    assert held.requested_w == 1300 and len(held.served) == 3  # one tier of equal deviation


@pytest.mark.req("FR-SAFE-04")
def test_fallback_ends_the_run_and_the_next_start_counts_fresh() -> None:
    ctrl = Controller(installation())
    assert _step(ctrl, 0, 1.5).running
    t_fallback = T0 + 40 * MIN
    result = ctrl.step(t_fallback, None, states(COLD))  # planner gone: waiting first
    assert not result.fallback
    t_fb = t_fallback + 10 * MIN
    assert ctrl.step(t_fb, None, states(COLD)).fallback
    assert not ctrl.running
    back = t_fb + 3 * MIN
    assert ctrl.step(back, plan(1500, back), states(COLD)).running  # new start
    assert ctrl.step(back + 5 * MIN, plan(0, back), states(COLD)).running  # held for 10 minutes
    assert not ctrl.step(back + 10 * MIN, plan(0, back), states(COLD)).running
