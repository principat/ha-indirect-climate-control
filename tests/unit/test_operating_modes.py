"""FR-OFS-01, FR-FAN-01, FR-OPM-01 to FR-OPM-06: heating offset, fan boost and the four operating modes."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.climate_control.core.buffer import (
    allocate,
    buffer_soc,
    power_steps,
    room_steps,
)
from custom_components.climate_control.core.config import Parameters
from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode, OperatingMode, Season
from custom_components.climate_control.core.planner_model import planner_inputs

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)
NIGHT = datetime(2026, 1, 15, 23, 0, tzinfo=UTC)
NOON = datetime(2026, 1, 15, 12, 30, tzinfo=UTC)
HEAT = Season.HEAT
OPTIMIZED = OperatingMode.HEMS_OPTIMIZED
BUFFER = OperatingMode.HEMS_BUFFER
MANUFACTURER = OperatingMode.MANUFACTURER
CYCLE = OperatingMode.MANUFACTURER_CYCLE


@pytest.mark.req("FR-OFS-01")
def test_the_heating_offset_is_taken_off_the_reading_and_the_setpoint_is_not_raised() -> None:
    cfg = installation(room("a"), heat_offset_k=2.0)
    at_setpoint = Controller(cfg).step(T0, plan(0), states({"a": 23.0}))
    assert at_setpoint.temperatures == {"a": 21.0}  # 23 reported, 2 of it is the offset
    assert at_setpoint.soc_pct == pytest.approx(50.0)  # the room stands on its setpoint
    running = Controller(cfg).step(T0, plan(2000), states({"a": 21.0}))
    command = running.commands["a"]
    assert command.mode is Mode.HEAT and command.target_c == 21.0  # not raised by the offset


@pytest.mark.req("FR-OFS-01")
def test_there_is_no_heating_offset_while_cooling() -> None:
    cfg = installation(room("a"), heat_offset_k=2.0)
    result = Controller(cfg).step(T0, plan(0), states({"a": 23.0}), season=Season.COOL)
    assert result.temperatures == {"a": 23.0}


@pytest.mark.req("FR-OFS-01")
def test_the_heating_offset_is_a_parameter_with_the_start_value_2() -> None:
    assert Parameters().heat_offset_k == 2.0
    assert Parameters.from_mapping({"heat_offset_k": 1.5}).heat_offset_k == 1.5
    with pytest.raises(ValueError, match="offset"):
        Parameters(heat_offset_k=-1.0).validate()


@pytest.mark.req("FR-FAN-01")
def test_only_a_unit_that_heats_under_our_control_is_boosted() -> None:
    cold = states({"a": 19.0, "b": 19.0, "c": 19.0})
    running = Controller(installation()).step(T0, plan(2000), cold)
    heating = [c for c in running.commands.values() if c.mode is Mode.HEAT]
    assert heating and all(c.boost for c in heating)
    assert not any(c.boost for c in running.commands.values() if c.mode is not Mode.HEAT)
    hot = states({"a": 24.0, "b": 24.0, "c": 24.0})
    cooling = Controller(installation()).step(T0, plan(2000), hot, season=Season.COOL)
    assert any(c.mode is Mode.COOL for c in cooling.commands.values())
    assert not any(c.boost for c in cooling.commands.values())


@pytest.mark.req("FR-FAN-01")
def test_the_manufacturer_control_never_boosts() -> None:
    result = Controller(installation()).step(
        T0, plan(2000), states({"a": 19.0, "b": 19.0, "c": 19.0}), operating=MANUFACTURER, local_now=T0
    )
    assert all(c.mode is Mode.HEAT and not c.boost for c in result.commands.values())


@pytest.mark.req("FR-FAN-01")
def test_the_fan_levels_are_optional_per_unit() -> None:
    r = room("a")
    assert r.fan_heat is None and r.fan_neutral is None
    assert replace(r, fan_heat="high").fan_heat == "high"


@pytest.mark.req("FR-OPM-01")
def test_there_are_four_modes_and_a_change_starts_fresh() -> None:
    assert [m.value for m in OperatingMode] == [
        "hems_optimized",
        "hems_buffer",
        "manufacturer",
        "manufacturer_cycle",
    ]
    ctrl = Controller(installation(room("a")))
    assert ctrl.step(T0, plan(2000), states({"a": 19.0})).running  # the default mode follows the plan
    t1 = T0 + MIN
    switched = ctrl.step(t1, plan(2000, t1), states({"a": 19.0}, Mode.HEAT), operating=MANUFACTURER)
    assert switched.operating is MANUFACTURER
    assert not switched.running and switched.requested_w == 0
    t2 = T0 + 2 * MIN
    back = ctrl.step(t2, plan(2000, t2), states({"a": 19.0}, Mode.HEAT), operating=OPTIMIZED)
    assert back.operating is OPTIMIZED and back.running


@pytest.mark.req("FR-OPM-01")
@pytest.mark.parametrize("mode", list(OperatingMode))
def test_an_open_window_takes_the_room_out_of_every_mode(mode: OperatingMode) -> None:
    cfg = installation(room("a"), room("b"))
    result = Controller(cfg).step(
        T0, plan(2000), states({"a": 19.0, "b": 19.0}, a=True), operating=mode, local_now=T0
    )
    assert result.commands["a"].mode is Mode.FAN
    assert result.commands["b"].mode is Mode.HEAT or mode is OPTIMIZED  # the optimized plant may serve none


@pytest.mark.req("FR-OPM-02")
def test_the_manufacturer_control_passes_the_setpoints_through() -> None:
    cfg = installation(room("a", setpoint=21.0), room("b", setpoint=19.0))
    cold = states({"a": 20.0, "b": 20.0})
    day = Controller(cfg).step(T0, plan(3000), cold, operating=MANUFACTURER, local_now=T0)
    assert {rid: (c.mode, c.target_c) for rid, c in day.commands.items()} == {
        "a": (Mode.HEAT, 21.0),
        "b": (Mode.HEAT, 19.0),
    }
    assert not day.running and day.requested_w == 0 and not day.fallback  # the plan is not followed
    night = Controller(cfg).step(T0, plan(3000), cold, operating=MANUFACTURER, local_now=NIGHT)
    assert [night.commands[r].target_c for r in ("a", "b")] == [20.0, 18.0]  # night setback 1


@pytest.mark.req("FR-OPM-02")
def test_the_manufacturer_control_mirrors_the_night_setback_when_cooling() -> None:
    cfg = installation(room("a", setpoint=24.0))
    result = Controller(cfg).step(
        T0, None, states({"a": 25.0}), season=Season.COOL, operating=MANUFACTURER, local_now=NIGHT
    )
    assert (result.commands["a"].mode, result.commands["a"].target_c) == (Mode.COOL, 25.0)


@pytest.mark.req("FR-OPM-02")
def test_the_manufacturer_control_leaves_no_buffer_to_the_planner() -> None:
    cfg = installation(room("a"))
    assert planner_inputs(cfg, NOON, HEAT, MANUFACTURER).capacity_kwh == 0.0
    assert planner_inputs(cfg, NOON, HEAT, CYCLE).capacity_kwh == 0.0
    assert planner_inputs(cfg, NOON, HEAT, OPTIMIZED).capacity_kwh > 0.0


@pytest.mark.req("FR-OPM-03")
def test_standby_lowers_the_setpoint_while_heating_and_it_returns_with_the_load() -> None:
    cfg = installation(room("a", setpoint=21.0))
    ctrl = Controller(cfg)
    st = states({"a": 20.0})

    def step(minutes: int, power: float | None) -> tuple[float | None, bool]:
        result = ctrl.step(T0 + minutes * MIN, None, st, outdoor_power_w=power, operating=CYCLE, local_now=T0)
        return result.commands["a"].target_c, result.standby

    assert step(0, 500.0) == (21.0, False)  # below the stop threshold of 650 W, but not for long enough
    assert step(4, 500.0) == (21.0, False)
    assert step(5, 500.0) == (20.0, True)  # 5 minutes: standby, the setpoint moves away by 1
    assert step(6, 700.0) == (21.0, False)  # the outdoor unit works again
    assert step(7, None) == (21.0, False)  # without a measurement there is never standby


@pytest.mark.req("FR-OPM-03")
def test_standby_raises_the_setpoint_while_cooling() -> None:
    ctrl = Controller(installation(room("a", setpoint=24.0)))
    st = states({"a": 25.0})
    for minutes in (0, 5):
        result = ctrl.step(
            T0 + minutes * MIN,
            None,
            st,
            season=Season.COOL,
            outdoor_power_w=100.0,
            operating=CYCLE,
            local_now=T0,
        )
    assert result.standby and result.commands["a"].target_c == 25.0


@pytest.mark.req("FR-OPM-03")
def test_without_the_cycle_optimization_standby_changes_nothing() -> None:
    ctrl = Controller(installation(room("a", setpoint=21.0)))
    st = states({"a": 20.0})
    for minutes in (0, 5, 10):
        result = ctrl.step(
            T0 + minutes * MIN, None, st, outdoor_power_w=100.0, operating=MANUFACTURER, local_now=T0
        )
    assert result.commands["a"].target_c == 21.0


@pytest.mark.req("FR-OPM-04")
def test_the_cooldown_starts_when_the_run_ends_and_ends_with_the_next_run() -> None:
    ctrl = Controller(installation(room("a")))
    temps = {"a": 20.0}
    first = ctrl.step(T0, plan(2000), states(temps))
    assert first.running and first.cooldown_left_s == 0
    later = T0 + 10 * MIN  # after the minimum run time
    stopped = ctrl.step(later, plan(0, later), states(temps, Mode.HEAT))
    assert not stopped.running and stopped.cooldown_left_s == 3600
    mid = later + 30 * MIN
    assert ctrl.step(mid, plan(0, mid), states(temps)).cooldown_left_s == pytest.approx(1800)
    done = later + 61 * MIN
    assert ctrl.step(done, plan(0, done), states(temps)).cooldown_left_s == 0
    again = done + MIN
    assert ctrl.step(again, plan(2000, again), states(temps)).cooldown_left_s == 0


@pytest.mark.req("FR-OPM-04")
def test_the_cooldown_adds_a_small_surcharge_to_the_charge_cost_of_the_windows_it_covers() -> None:
    cfg = installation(room("a"))
    base = planner_inputs(cfg, NOON)
    cooling = planner_inputs(cfg, NOON, HEAT, OPTIMIZED, 3600.0)  # until 13:30
    pairs = zip(cooling.charge_cost_forecast, base.charge_cost_forecast, strict=True)
    extra = [c[1] - b[1] for c, b in pairs]
    assert extra[:2] == [pytest.approx(0.001)] * 2  # the windows from 12:00 and from 13:00
    assert all(e == pytest.approx(0.0) for e in extra[2:])
    assert cooling.charge_cost == pytest.approx(base.charge_cost + 0.001)
    assert planner_inputs(cfg, NOON, HEAT, OPTIMIZED, 0.0) == base
    # a tie breaker only: smaller than the difference of any two real prices
    assert Parameters().cooldown_surcharge <= 0.001


@pytest.mark.req("FR-OPM-05")
def test_the_buffer_soc_adds_the_buffer_ranges_of_the_rooms() -> None:
    a, b = room("a", setpoint=21.0), room("b", setpoint=22.0)  # buffer range 2 each
    assert buffer_soc([(a, 22.0), (b, 22.0)], HEAT, 0.0) == pytest.approx(25.0)  # 1 of 4
    assert buffer_soc([(a, 23.0), (b, 24.0)], HEAT, 0.0) == pytest.approx(100.0)
    assert buffer_soc([(a, 19.0), (b, 22.0)], HEAT, 0.0) == pytest.approx(0.0)  # below the setpoint: 0
    assert buffer_soc([(a, 30.0), (b, 30.0)], HEAT, 0.0) == pytest.approx(100.0)  # beyond the range: full
    assert buffer_soc([(a, 20.0), (b, 20.0)], Season.COOL, 0.0) == pytest.approx(75.0)  # mirrored


@pytest.mark.req("FR-OPM-05")
def test_the_night_setback_is_the_part_of_the_buffer_below_the_setpoint() -> None:
    a = room("a", setpoint=21.0)  # setback 1 below, range 2 above: the scale is 3 wide
    assert buffer_soc([(a, 20.0)], HEAT, 1.0) == pytest.approx(0.0)  # at the lowered setpoint
    assert buffer_soc([(a, 21.0)], HEAT, 1.0) == pytest.approx(100 / 3)  # at the setpoint: a third
    assert buffer_soc([(a, 23.0)], HEAT, 1.0) == pytest.approx(100.0)
    assert buffer_soc([(a, 18.0)], HEAT, 1.0) == pytest.approx(0.0)  # below the scale
    assert buffer_soc([(a, 21.0)], Season.COOL, 1.0) == pytest.approx(100 / 3)  # mirrored


@pytest.mark.req("FR-OPM-05")
def test_the_buffer_control_keeps_the_comfort_setpoint_and_reports_the_buffer_scale() -> None:
    cfg = installation(room("a", setpoint=21.0), room("b", setpoint=22.0))
    ctrl = Controller(cfg)
    day = ctrl.step(T0, plan(0), states({"a": 22.0, "b": 22.0}), operating=BUFFER, local_now=T0)
    assert day.soc_pct == pytest.approx(50.0)  # scales of 3: 2 + 1 of 6, the setback is part of it
    assert {rid: (c.mode, c.target_c) for rid, c in day.commands.items()} == {
        "a": (Mode.HEAT, 21.0),
        "b": (Mode.HEAT, 22.0),
    }
    warm = states({"a": 22.0, "b": 22.0})
    night = Controller(cfg).step(T0, plan(0), warm, operating=BUFFER, local_now=NIGHT)
    # the reserve below the setpoint is not used at night
    assert [night.commands[r].target_c for r in ("a", "b")] == [20.0, 21.0]
    inputs = planner_inputs(cfg, NOON, HEAT, BUFFER)
    # by day the lowest point in use is the setpoint: a third of the scale (setback 1, range 2)
    assert (inputs.min_charge_pct, inputs.undercharge_pct) == (33.33, 33.33)
    assert (inputs.max_charge_pct, inputs.overcharge_pct) == (100.0, 100.0)
    assert inputs.capacity_kwh == pytest.approx(3.5 * 3.0)  # energy per K times the scale (setback + range)
    # at night the setback may be used: the lowest point is 0 %
    at_night = planner_inputs(cfg, NIGHT, HEAT, BUFFER)
    assert (at_night.min_charge_pct, at_night.undercharge_pct) == (0.0, 0.0)
    values = dict(inputs.min_charge_forecast)
    assert values[NOON.replace(minute=0)] == 33.33


@pytest.mark.req("FR-OPM-05")
def test_the_buffer_control_charges_nothing_without_a_plan_and_has_no_fallback() -> None:
    ctrl = Controller(installation(room("a")))
    for minutes in (0, 30):
        result = ctrl.step(T0 + minutes * MIN, None, states({"a": 20.0}), operating=BUFFER, local_now=T0)
    assert not result.fallback and not result.running
    assert result.commands["a"].target_c == 21.0 and result.plan_missing_s == 30 * 60


@pytest.mark.req("FR-OPM-05")
def test_the_buffer_control_heats_with_the_raised_fan_level() -> None:
    result = Controller(installation(room("a"))).step(
        T0, plan(0), states({"a": 20.0}), operating=BUFFER, local_now=T0
    )
    assert result.commands["a"].mode is Mode.HEAT and result.commands["a"].boost


@pytest.mark.req("FR-OPM-06")
def test_the_maximum_power_is_spread_over_the_buffer_steps() -> None:
    assert room_steps(room("a"), HEAT) == 4  # range 2 in steps of 0.5
    assert room_steps(replace(room("a"), step=5.0), HEAT) == 1  # at least one step
    assert power_steps(1300.0, 3300.0, 12) == 5  # one step is 275 W, 1300 / 275 = 4.7
    assert power_steps(100.0, 3300.0, 12) == 1  # a request is at least one step
    assert power_steps(5000.0, 3300.0, 12) == 12  # never more than all steps
    assert power_steps(0.0, 3300.0, 12) == 0


@pytest.mark.req("FR-OPM-06")
def test_the_steps_are_distributed_round_robin_up_to_the_capacity_of_each_room() -> None:
    rooms = [("a", 4), ("b", 4), ("c", 4)]
    assert allocate(rooms, 5, 0) == {"a": 2, "b": 2, "c": 1}
    assert allocate(rooms, 5, 1) == {"a": 1, "b": 2, "c": 2}  # another room begins
    full = allocate([("a", 0), ("b", 4), ("c", 4)], 5, 0)
    assert full == {"a": 0, "b": 3, "c": 2}  # a full room is skipped
    assert allocate([("a", 1), ("b", 1)], 5, 0) == {"a": 1, "b": 1}  # no more than the capacity
    assert allocate([], 3, 0) == {}


@pytest.mark.req("FR-OPM-06")
def test_the_requested_power_raises_the_setpoints_in_steps() -> None:
    ctrl = Controller(installation())
    result = ctrl.step(
        T0, plan(1300), states({"a": 21.0, "b": 21.0, "c": 21.0}), operating=BUFFER, local_now=T0
    )
    assert result.running and result.requested_w == 1300
    assert sum(result.steps.values()) == 5
    raised = sorted(c.target_c - 21.0 for c in result.commands.values() if c.target_c is not None)
    assert raised == [0.5, 1.0, 1.0]  # 5 steps of 0.5: 1 + 2 + 2


@pytest.mark.req("FR-OPM-06")
def test_a_room_with_a_full_buffer_takes_no_step_and_the_next_period_starts_elsewhere() -> None:
    ctrl = Controller(installation())
    temps = {"a": 23.0, "b": 21.0, "c": 21.0}  # a is at the end of its buffer range
    result = ctrl.step(T0, plan(1300), states(temps), operating=BUFFER, local_now=T0)
    assert result.commands["a"].target_c == 21.0
    assert sorted(result.commands[r].target_c or 0.0 for r in ("b", "c")) == [22.0, 22.5]
    t1 = T0 + MIN
    at_setpoint = states({"a": 21.0, "b": 21.0, "c": 21.0})
    off = ctrl.step(t1, plan(0, t1), at_setpoint, operating=BUFFER, local_now=t1)
    assert not off.running and all(c.target_c == 21.0 for c in off.commands.values())
    t2 = T0 + 2 * MIN
    on = ctrl.step(t2, plan(1300, t2), at_setpoint, operating=BUFFER, local_now=t2)
    assert on.commands["b"].target_c == 21.5  # the period started at another room: b gets the single step
    assert on.commands["a"].target_c == 22.0 and on.commands["c"].target_c == 22.0


@pytest.mark.req("FR-OPM-06")
def test_the_soc_follows_the_measured_temperature_not_the_steps() -> None:
    ctrl = Controller(installation())
    cold = states({"a": 21.0, "b": 21.0, "c": 21.0})
    soc = ctrl.step(T0, plan(3300), cold, operating=BUFFER, local_now=T0).soc_pct
    assert soc == pytest.approx(100 / 3, abs=0.01)  # at the setpoint: a third, whatever the steps are


@pytest.mark.req("FR-OPM-05")
def test_the_minimum_soc_for_the_planner_follows_from_the_setback_and_the_buffer_range() -> None:
    wide = installation(replace(room("a"), band_up=3.0, limit_up=3.0))  # buffer 3, setback 1 (default)
    assert planner_inputs(wide, NOON, HEAT, BUFFER).min_charge_pct == 25.0  # 1 of 4, not a fixed third
    deeper = installation(room("a"), night_setback_k=2.0)  # buffer 2, setback 2
    assert planner_inputs(deeper, NOON, HEAT, BUFFER).min_charge_pct == 50.0
