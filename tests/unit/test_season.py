"""FR-SEAS-01/02: heating is the default, cooling mirrors the whole control."""

from dataclasses import replace
from datetime import timedelta

import pytest

from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.diagnostics import room_diagnostics
from custom_components.climate_control.core.model import Mode, Season
from custom_components.climate_control.core.planner_model import planner_inputs
from custom_components.climate_control.core.soc import deviation_to_soc

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)
HOT = {"a": 25.0, "b": 22.0, "c": 21.0}  # setpoint 21 in every room, a is 4 beyond it (limit 3)


def _cool(ctrl: Controller, temps: dict[str, float], kw: float, minutes: float = 0, mode: Mode = Mode.FAN):  # noqa: ANN202
    t = T0 + minutes * MIN
    return ctrl.step(t, plan(kw * 1000, t), states(temps, mode), season=Season.COOL)


def _confirmed(ctrl: Controller, temps: dict[str, float], mode: Mode):  # noqa: ANN202
    """Jumps above the outlier limit count after the next cycle confirms them (FR-SOC-02)."""
    for minutes in (3, 4):
        t = T0 + minutes * MIN
        result = ctrl.step(t, plan(0, t), states(temps, mode))
    return result


def _modes(result) -> dict[str, Mode]:  # noqa: ANN001
    return {rid: c.mode for rid, c in result.commands.items()}


@pytest.mark.req("FR-SEAS-01")
def test_heating_is_the_default() -> None:
    result = Controller(installation()).step(T0, plan(2000), states({"a": 20.0, "b": 20.0, "c": 20.0}))
    assert result.season is Season.HEAT
    assert Mode.HEAT in _modes(result).values() and Mode.COOL not in _modes(result).values()


@pytest.mark.req("FR-SEAS-01")
def test_season_values_point_in_the_direction_of_the_season() -> None:
    assert Season.HEAT.sign == 1 and Season.HEAT.mode is Mode.HEAT and Season.HEAT.opposite is Mode.COOL
    assert Season.COOL.sign == -1 and Season.COOL.mode is Mode.COOL and Season.COOL.opposite is Mode.HEAT


@pytest.mark.req("FR-SEAS-01")
def test_changing_the_season_starts_a_new_state() -> None:
    ctrl = Controller(installation())
    cold = {"a": 20.0, "b": 20.0, "c": 20.0}
    assert ctrl.step(T0, plan(1500), states(cold)).running
    # one minute later the switch turns to cooling: the heating run and its minimum run time are gone
    later = T0 + MIN
    result = ctrl.step(later, plan(0, later), states(cold), season=Season.COOL)
    assert not result.running and result.season is Season.COOL
    assert Mode.HEAT not in _modes(result).values()


@pytest.mark.req("FR-SEAS-01")
def test_heating_and_cooling_never_run_together() -> None:
    ctrl = Controller(installation())
    # units are still heating when the season turns: they go neutral first (FR-MODE-01), then cool
    first = ctrl.step(T0, plan(1500), states(HOT, Mode.HEAT), season=Season.COOL)
    assert set(_modes(first).values()) == {Mode.FAN}
    second = ctrl.step(T0 + MIN, plan(1500, T0 + MIN), states(HOT, Mode.FAN), season=Season.COOL)
    assert Mode.COOL in _modes(second).values() and Mode.HEAT not in _modes(second).values()


@pytest.mark.req("FR-SEAS-02")
def test_soc_is_the_mirrored_deviation_when_cooling() -> None:
    cfg = installation()
    # 3 above the setpoint is 3 on the discharged side while cooling: 40 % - 3 x 6.67 %
    result = _cool(Controller(cfg), {"a": 24.0, "b": 24.0, "c": 24.0}, 0)
    assert result.soc_pct == pytest.approx(20.0)
    # the same temperatures heating are 3 above the setpoint, on the charged side
    heating = Controller(cfg).step(T0, plan(0), states({"a": 24.0, "b": 24.0, "c": 24.0}))
    assert heating.soc_pct == pytest.approx(60.0)
    assert (
        deviation_to_soc(-1.0, cfg.params)
        > deviation_to_soc(0.0, cfg.params)
        > deviation_to_soc(1.0, cfg.params)
    )


@pytest.mark.req("FR-SEAS-02")
def test_worst_room_is_the_warmest_against_its_setpoint_when_cooling() -> None:
    result = _cool(Controller(installation()), HOT, 0)
    assert result.worst_room == "a"
    assert result.soc_pct == pytest.approx(13.33, abs=0.01)  # 4 above: 40 % - 4 x 6.67 %


@pytest.mark.req("FR-SEAS-02")
def test_cooling_serves_the_largest_deviation_first_and_steps_the_setpoint_down() -> None:
    warm = {
        "a": 23.0,
        "b": 22.0,
        "c": 21.0,
    }  # +2, +1, 0 against the setpoint: nobody beyond the absolute limit
    result = _cool(Controller(installation()), warm, 1.1)
    assert result.running and result.requested_w == 1300
    assert result.served == ("a", "b")  # 2 x 700 W >= 1300 W, a (+2) before b (+1)
    assert result.commands["a"].mode is Mode.COOL and result.commands["a"].target_c == 22.0
    assert result.commands["b"].target_c == 21.0
    assert result.commands["c"].mode is Mode.FAN  # not served: neutral


@pytest.mark.req("FR-SEAS-02")
def test_cooling_target_never_goes_below_the_absolute_limit_below_the_setpoint() -> None:
    cfg = installation(room("a", setpoint=21), room("b"), room("c"))
    # absolute limit below the setpoint is 3: the room is already there
    result = _cool(Controller(cfg), {"a": 18.0, "b": 22.0, "c": 22.0}, 1.5)
    assert "a" not in result.served and result.commands["a"].mode is Mode.FAN  # at the limit: not eligible
    near = _cool(Controller(cfg), {"a": 18.5, "b": 18.5, "c": 18.5}, 1.5)
    assert "a" in near.served
    assert near.commands["a"].target_c == 18.0  # 18.5 - 1 step would pass the limit: held at it


@pytest.mark.req("FR-SEAS-02")
def test_absolute_limit_above_the_setpoint_cools_even_without_a_plan() -> None:
    result = _cool(Controller(installation()), {"a": 25.0, "b": 21.0, "c": 21.0}, 0)
    assert not result.running
    assert result.commands["a"].mode is Mode.COOL and result.commands["a"].target_c == 21.0
    assert result.commands["b"].mode is Mode.FAN
    at_limit = _cool(Controller(installation()), {"a": 24.0, "b": 21.0, "c": 21.0}, 0)
    assert at_limit.commands["a"].mode is Mode.FAN  # 3 above is the limit itself, not beyond it


@pytest.mark.req("FR-SEAS-02")
def test_undercooled_room_is_heated_only_when_no_unit_cools_and_after_the_wait() -> None:
    ctrl = Controller(installation())
    temps = {"a": 18.0, "b": 21.0, "c": 21.0}  # 3 below the setpoint
    assert Mode.HEAT not in _modes(_cool(ctrl, temps, 0, 0)).values()
    assert Mode.HEAT not in _modes(_cool(ctrl, temps, 0, 59)).values()
    result = _cool(ctrl, temps, 0, 61)
    assert result.commands["a"].mode is Mode.HEAT and result.commands["a"].target_c == 21.0
    # while a unit cools the undercooled room is left alone
    busy = _cool(Controller(installation()), {"a": 18.0, "b": 24.0, "c": 21.0}, 1.5, 0)
    assert Mode.COOL in _modes(busy).values()
    later = _cool(Controller(installation()), {"a": 18.0, "b": 24.0, "c": 21.0}, 1.5, 61)
    assert later.commands["a"].mode is not Mode.HEAT


@pytest.mark.req("FR-SEAS-02")
def test_fallback_cools_step_by_step_with_standard_setpoints() -> None:
    ctrl = Controller(installation())
    temps = {"a": 23.0, "b": 22.0, "c": 21.0}
    ctrl.step(T0, None, states(temps), season=Season.COOL)  # waiting starts
    waiting = ctrl.step(T0 + 5 * MIN, None, states(temps), season=Season.COOL)
    assert not waiting.fallback and Mode.COOL not in _modes(waiting).values()
    first = ctrl.step(T0 + 10 * MIN, None, states(temps), season=Season.COOL)
    assert first.fallback
    cooled = {rid: c for rid, c in first.commands.items() if c.mode is Mode.COOL}
    assert set(cooled) == {"a"} and cooled["a"].target_c == 21.0  # largest deviation first
    later = ctrl.step(T0 + 12 * MIN, None, states(temps, Mode.COOL), season=Season.COOL)
    assert {rid for rid, c in later.commands.items() if c.mode is Mode.COOL} >= {"a", "b"}


@pytest.mark.req("FR-SEAS-02")
def test_planner_receives_the_bands_with_the_sides_swapped_when_cooling() -> None:
    bands = {"band_down": 1.0, "band_up": 2.0, "limit_down": 2.0, "limit_up": 4.0}
    cfg = installation(*(replace(r, **bands) for r in installation().rooms))
    t = T0.replace(hour=14)  # day
    heat = planner_inputs(cfg, t, Season.HEAT)
    cool = planner_inputs(cfg, t, Season.COOL)
    assert heat.capacity_kwh == cool.capacity_kwh
    assert heat.min_charge_pct == pytest.approx(
        33.33, abs=0.01
    )  # 40 % - 1 x 6.67 % (discharge side is below)
    assert cool.min_charge_pct == pytest.approx(
        26.67, abs=0.01
    )  # 40 % - 2 x 6.67 % (discharge side is above)
    assert heat.undercharge_pct == pytest.approx(26.67, abs=0.01)
    assert cool.undercharge_pct == pytest.approx(13.33, abs=0.01)
    assert heat.max_charge_pct == pytest.approx(53.33, abs=0.01)
    assert cool.max_charge_pct == pytest.approx(46.67, abs=0.01)
    assert heat.overcharge_pct == pytest.approx(66.67, abs=0.01)
    assert cool.overcharge_pct == pytest.approx(53.33, abs=0.01)
    night = planner_inputs(cfg, T0.replace(hour=23), Season.COOL)
    assert night.min_charge_pct == pytest.approx(
        20.0, abs=0.01
    )  # the setback relaxes the discharge side by 1
    assert (night.max_charge_pct, night.overcharge_pct) == (cool.max_charge_pct, cool.overcharge_pct)


@pytest.mark.req("FR-SEAS-02")
def test_diagnostics_are_mirrored_when_cooling() -> None:
    cfg = installation(room("a"))
    heat = room_diagnostics(cfg, {"a": 20.0}, Season.HEAT)["a"]
    cool = room_diagnostics(cfg, {"a": 23.0}, Season.COOL)["a"]
    assert heat.deviation_k == 1.0
    assert cool.deviation_k == 2.0  # 2 too warm = 2 to go
    assert cool.heat_demand_kwh == pytest.approx(3.5 * 2.0)
    assert cool.storage_kwh == pytest.approx(3.5 * (3 + 2))  # down to the absolute limit below the setpoint


@pytest.mark.req("FR-PLAN-02")
def test_minimum_run_time_is_not_used_when_every_room_is_at_its_absolute_limit() -> None:
    ctrl = Controller(installation())
    cold = {"a": 20.0, "b": 20.0, "c": 20.0}
    assert ctrl.step(T0, plan(1500), states(cold)).running
    full = {"a": 24.0, "b": 24.0, "c": 24.0}  # 3 above the setpoint: the limit above is reached everywhere
    result = _confirmed(ctrl, full, Mode.HEAT)
    assert not result.running and set(_modes(result).values()) == {Mode.FAN}


@pytest.mark.req("FR-PLAN-02")
def test_minimum_run_time_does_not_heat_a_room_at_its_absolute_limit() -> None:
    ctrl = Controller(installation())
    cold = {"a": 20.0, "b": 20.0, "c": 20.0}
    assert ctrl.step(T0, plan(1500), states(cold)).running
    mixed = {"a": 24.0, "b": 20.0, "c": 20.0}  # only a is full
    result = _confirmed(ctrl, mixed, Mode.HEAT)
    assert result.running and "a" not in result.served
    assert result.commands["a"].mode is Mode.FAN


@pytest.mark.req("FR-PLAN-02")
def test_minimum_run_time_is_not_used_in_cooling_when_every_room_reached_the_limit_below() -> None:
    ctrl = Controller(installation())
    assert _cool(ctrl, HOT, 1.5).running
    cold = {"a": 18.0, "b": 18.0, "c": 18.0}  # the absolute limit below a setpoint of 21 is 18
    _cool(ctrl, cold, 0, 3, Mode.COOL)  # a jump above 2 is an outlier until the next cycle confirms it
    result = _cool(ctrl, cold, 0, 4, Mode.COOL)
    assert not result.running
