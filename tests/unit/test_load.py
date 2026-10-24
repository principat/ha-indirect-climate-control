"""FR-LOAD-01/02: load control on temperature events, power per step learned per indoor unit."""

from dataclasses import replace
from datetime import timedelta

import pytest

from custom_components.climate_control.core.config import InstallationConfig
from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.distribution import rank
from custom_components.climate_control.core.load import (
    LoadControl,
    LoadModel,
    expected_load_w,
    start_power_w,
)
from custom_components.climate_control.core.model import Mode, RoomState, Season

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)
IDLE_W = 20.0


def rooms4(**per_room: float) -> InstallationConfig:
    return installation(*(room(f"r{i}", power=700.0) for i in range(1, 5)), **per_room)


def ranked(cfg: InstallationConfig, deviations: dict[str, float] | None = None, rooms=None):  # noqa: ANN001, ANN202
    """The tiers of the units as the controller hands them over: by deviation, then class (FR-DIST-01/02)."""
    dev = deviations or {}
    return rank(
        [(r, dev.get(r.id, 0.0)) for r in (cfg.rooms if rooms is None else rooms)],
        cfg.params.tie_band_k,
        cfg.class_order,
    )


class Plant:
    """Outdoor unit that follows the sum of true power per step with a lag, sampled once per cycle."""

    def __init__(
        self, ctl: LoadControl, cfg: InstallationConfig, true_w: dict[str, float], alpha: float = 0.6
    ) -> None:
        self.ctl, self.cfg, self.true_w, self.alpha = ctl, cfg, true_w, alpha
        self.power = IDLE_W
        self.now = T0

    def cycle(self, requested_w: float, disturbed: bool = False) -> dict[str, int]:
        target = IDLE_W + expected_load_w(self.ctl.steps, self.true_w, self.cfg.p_min_w)
        self.power += (target - self.power) * self.alpha
        self.now += MIN
        self.ctl.feed(self.now, self.power, self.cfg)
        return self.ctl.update(self.now, self.cfg, Season.HEAT, requested_w, ranked(self.cfg), disturbed)


def expected(ctl: LoadControl, cfg: InstallationConfig) -> float:
    return ctl.expected_w


@pytest.mark.req("FR-LOAD-02")
def test_the_start_value_is_the_power_range_divided_by_twice_the_number_of_units() -> None:
    assert start_power_w(installation(*(room(f"r{i}") for i in range(7)))) == pytest.approx(2000 / 14)
    assert start_power_w(rooms4()) == 250.0
    model = LoadModel()
    assert model.power("r1", 250.0) == 250.0  # nothing learned yet


@pytest.mark.req("FR-LOAD-01")
def test_the_expected_load_reaches_the_request_within_the_dead_band() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    for requested in (1300.0, 2000.0, 3000.0):
        steps = ctl.update(T0, cfg, Season.HEAT, requested, ranked(cfg))
        assert abs(ctl.expected_w - requested) <= 130 + 250 / 2  # the step size bounds the accuracy
        assert sum(steps.values()) >= 2  # never below the minimum stage
        assert ctl.expected_w == pytest.approx(
            expected_load_w(steps, {r.id: 250.0 for r in cfg.rooms}, 1300.0)
        )
    assert expected_load_w({"a": 1, "b": 1}, {"a": 250.0, "b": 250.0}, 1300.0) == 1300.0  # two steps are Pmin
    assert expected_load_w({"a": 3, "b": 1}, {"a": 400.0, "b": 100.0}, 1300.0) == pytest.approx(
        1300.0 + 325 * 2
    )
    assert expected_load_w({}, {}, 1300.0) == 0.0


@pytest.mark.req("FR-LOAD-01")
def test_nothing_changes_inside_the_dead_band() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    first = ctl.update(T0, cfg, Season.HEAT, 2000.0, ranked(cfg))
    again = ctl.update(T0 + MIN, cfg, Season.HEAT, 2000.0 + 100, ranked(cfg))  # 100 W is inside 130 W
    assert again == first
    moved = ctl.update(T0 + 2 * MIN, cfg, Season.HEAT, 2000.0 + 300, ranked(cfg))
    assert sum(moved.values()) > sum(first.values())


@pytest.mark.req("FR-LOAD-01")
def test_the_room_with_the_largest_deviation_is_served_first_and_the_power_class_only_decides_a_tie() -> None:
    cfg = installation(
        room("big1", power=900.0),
        room("small", power=500.0),
        room("big2", power=900.0),
        room("mid", power=700.0),
    )
    ctl = LoadControl()
    steps = ctl.update(T0, cfg, Season.HEAT, 1300.0, ranked(cfg, {"small": 3.0}))
    # the minimum stage needs two units: the neediest room and the first of the rest (all equal)
    assert steps == {"small": 1, "big1": 1}
    tie = LoadControl().update(T0, cfg, Season.HEAT, 1300.0, ranked(cfg))
    assert tie == {"big1": 1, "big2": 1}  # all equal: the class group (one class, configured order) decides


@pytest.mark.req("FR-LOAD-01")
def test_the_rooms_are_brought_to_one_level_and_then_rise_together() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    behind = ctl.update(T0, cfg, Season.HEAT, 2050.0, ranked(cfg, {"r1": 3.0}))  # r1 is 2 K further behind
    assert behind["r1"] >= 3 and behind["r1"] > max(n for rid, n in behind.items() if rid != "r1")
    # r1 has caught up: the units without steps join before r1 gets more
    even = ctl.update(T0 + MIN, cfg, Season.HEAT, 3050.0, ranked(cfg))
    assert even["r1"] == behind["r1"] and sum(even.values()) > sum(behind.values())
    assert min(even.get(rid, 0) for rid in ("r2", "r3", "r4")) >= 1


@pytest.mark.req("FR-LOAD-01")
def test_lowering_takes_the_fullest_room_first() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    ctl.update(T0, cfg, Season.HEAT, 2800.0, ranked(cfg))
    before = dict(ctl.steps)
    fill = {"r1": 2.0, "r2": 2.0, "r3": 2.0, "r4": -1.0}
    after = ctl.update(T0 + MIN, cfg, Season.HEAT, 2000.0, ranked(cfg, fill))
    assert after.get("r4", 0) < before["r4"]  # r4 is the fullest
    assert all(after.get(rid, 0) == before[rid] for rid in ("r1", "r2", "r3")) or sum(after.values()) < sum(
        before.values()
    )


@pytest.mark.req("FR-LOAD-01")
def test_more_units_join_only_when_the_setpoints_of_the_served_ones_are_used_up() -> None:
    cfg = rooms4()
    limited = tuple(
        replace(r, limit_up=1.0, band_up=1.0, step=0.5) for r in cfg.rooms
    )  # at most 2 steps per unit
    cfg = replace(cfg, rooms=limited)
    ctl = LoadControl()
    small = ctl.update(T0, cfg, Season.HEAT, 1000.0, ranked(cfg))
    assert len(small) == 2 and max(small.values()) <= 2
    big = ctl.update(T0 + MIN, cfg, Season.HEAT, 3000.0, ranked(cfg))
    assert len(big) == 4 and all(n == 2 for n in big.values())  # all four units at their limit of 2 steps


@pytest.mark.req("FR-LOAD-01")
def test_lowering_stops_at_two_steps_spread_over_two_units() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    ctl.update(T0, cfg, Season.HEAT, 3000.0, ranked(cfg))
    for minute in range(1, 6):
        steps = ctl.update(T0 + minute * MIN, cfg, Season.HEAT, 0.0, ranked(cfg))  # the plan drops to nothing
    assert sum(steps.values()) == 2 and len(steps) == 2  # the floor: two power steps on two units
    assert all(n == 1 for n in steps.values())


@pytest.mark.req("FR-LOAD-01")
def test_more_than_two_units_may_be_reduced_to_two() -> None:
    cfg = rooms4()
    limited = tuple(replace(r, limit_up=1.0, band_up=1.0) for r in cfg.rooms)
    cfg = replace(cfg, rooms=limited)
    ctl = LoadControl()
    full = ctl.update(T0, cfg, Season.HEAT, 3000.0, ranked(cfg))
    assert len(full) == 4
    lowered = ctl.update(T0 + MIN, cfg, Season.HEAT, 500.0, ranked(cfg))
    assert len(lowered) == 2 and sum(lowered.values()) >= 2


@pytest.mark.req("FR-LOAD-01")
def test_units_that_are_no_longer_eligible_lose_their_steps() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    ctl.update(T0, cfg, Season.HEAT, 2000.0, ranked(cfg))
    served = set(ctl.steps)
    gone = sorted(served)[0]
    remaining = [r for r in cfg.rooms if r.id != gone]
    steps = ctl.update(T0 + MIN, cfg, Season.HEAT, 2000.0, ranked(cfg, rooms=remaining))
    assert gone not in steps and sum(steps.values()) > 0


@pytest.mark.req("FR-LOAD-01")
def test_the_controller_sets_the_setpoint_beyond_the_device_temperature_by_the_steps() -> None:
    cfg = rooms4()
    ctrl = Controller(cfg)
    result = ctrl.step(T0, plan(2000), states({f"r{i}": 20.0 for i in range(1, 5)}))
    assert result.steps and sum(result.steps.values()) >= 2
    for rid, n in result.steps.items():
        assert result.commands[rid].mode is Mode.HEAT
        assert result.commands[rid].target_c == pytest.approx(
            20.0 - 2.0 + n * 0.5
        )  # above the start threshold
    idle = [rid for rid in (f"r{i}" for i in range(1, 5)) if rid not in result.steps]
    assert all(result.commands[rid].mode is Mode.FAN for rid in idle)
    assert result.expected_w == pytest.approx(
        expected_load_w(result.steps, {r: 250.0 for r in result.steps}, 1300.0)
    )


@pytest.mark.req("FR-LOAD-01")
def test_the_step_size_is_set_per_unit() -> None:
    cfg = installation(replace(room("a"), step=1.0), room("b"))
    ctrl = Controller(cfg)
    result = ctrl.step(T0, plan(1500), states({"a": 20.0, "b": 20.0}))
    assert result.commands["a"].target_c == pytest.approx(20.0 - 2.0 + result.steps["a"] * 1.0)
    assert result.commands["b"].target_c == pytest.approx(20.0 - 2.0 + result.steps["b"] * 0.5)


@pytest.mark.req("FR-LOAD-02")
def test_the_power_per_step_is_learned_per_unit_from_the_settled_outdoor_power() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    true_w = {"r1": 500.0, "r2": 400.0, "r3": 600.0, "r4": 500.0}
    plant = Plant(ctl, cfg, true_w)
    for requested in (1300, 2000, 1500, 2600, 1300, 3000, 1500, 2500, 1300, 2800, 1600) * 3:
        for _ in range(10):  # the power settles in a few cycles after each change of the request
            plant.cycle(float(requested))
    learned = {rid: item.learned_w for rid, item in ctl.model.units.items() if item.learned_w is not None}
    assert learned, "nothing learned"
    for rid, value in learned.items():
        assert value == pytest.approx(
            true_w[rid], rel=0.35
        )  # the scaling of a pair is shared, so only roughly
    assert all(item.estimates >= 1 for item in ctl.model.units.values())
    assert all(item.last_estimate_w is not None for item in ctl.model.units.values())


@pytest.mark.req("FR-LOAD-02")
def test_the_first_three_estimates_replace_the_start_value_by_their_median() -> None:
    model = LoadModel()
    for value in (300.0, 600.0, 500.0):
        assert model.power("r1", 250.0) == 250.0  # still the start value
        model.update_unit("r1", value, T0)
    assert model.power("r1", 250.0) == 500.0
    model.update_unit("r1", 1000.0, T0)  # a later estimate moves the value slowly and by at most a quarter
    assert model.power("r1", 250.0) == pytest.approx(500.0 + 0.2 * 500.0)
    model.update_unit("r1", 10000.0, T0)
    assert model.power("r1", 250.0) <= 600.0 * 1.25 + 1e-9


@pytest.mark.req("FR-LOAD-02")
def test_a_second_adjustment_while_waiting_disturbs_the_observation() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    plant = Plant(ctl, cfg, {r.id: 500.0 for r in cfg.rooms})
    for _ in range(4):
        plant.cycle(1300.0)  # idle: the means before the adjustment
    plant.cycle(2500.0)  # adjustment: an observation starts
    plant.cycle(1300.0)  # the request changes again while it waits: both are dropped
    for _ in range(12):
        plant.cycle(1300.0)
    assert not ctl.model.units  # nothing was learned from the disturbed observation


@pytest.mark.req("FR-LOAD-02")
def test_something_else_moving_the_load_disturbs_the_observation() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    plant = Plant(ctl, cfg, {r.id: 500.0 for r in cfg.rooms})
    for _ in range(4):
        plant.cycle(1300.0)
    plant.cycle(2500.0)
    plant.cycle(2500.0, disturbed=True)  # e.g. a room under protection started to heat
    for _ in range(12):
        plant.cycle(2500.0)
    assert not ctl.model.units


@pytest.mark.req("FR-LOAD-02")
def test_a_power_that_never_settles_teaches_nothing_and_gives_up_after_the_maximum_time() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    plant = Plant(ctl, cfg, {r.id: 500.0 for r in cfg.rooms})
    for _ in range(4):
        plant.cycle(1300.0)
    plant.cycle(2500.0)
    for minute in range(30):  # the outdoor unit cycles up and down by far more than the dead band
        plant.power = 2500.0 if minute % 2 else 300.0
        plant.now += MIN
        ctl.feed(plant.now, plant.power, cfg)
    assert not ctl.model.units
    assert ctl._observation is None  # noqa: SLF001  # the maximum time (10 min) has passed


@pytest.mark.req("FR-LOAD-02")
def test_nothing_is_learned_without_a_power_reading() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    for minute in range(3):
        ctl.feed(T0 + minute * MIN, 20.0, cfg)
    ctl.update(T0 + 3 * MIN, cfg, Season.HEAT, 2000.0, ranked(cfg))
    ctl.feed(T0 + 4 * MIN, None, cfg)  # the sensor is gone
    assert ctl._observation is None  # noqa: SLF001
    assert not ctl.model.units


@pytest.mark.req("FR-LOAD-02")
def test_the_learned_values_survive_a_restart_and_can_be_reset() -> None:
    model = LoadModel()
    for value in (300.0, 600.0, 500.0):
        model.update_unit("r1", value, T0)
    model.update_unit("r2", 400.0, T0)
    again = LoadModel(model.snapshot())
    assert again.power("r1", 250.0) == 500.0
    assert again.units["r2"].estimates == 1 and again.units["r2"].bootstrap == [400.0]
    assert again.units["r1"].updated == T0
    broken = LoadModel({"r1": "x", "r2": {"learned_w": "abc"}, "r3": {}})
    assert broken.power("r1", 250.0) == 250.0 and broken.power("r2", 250.0) == 250.0
    revision = model.revision
    model.reset()
    assert model.revision == revision + 1 and model.power("r1", 250.0) == 250.0


@pytest.mark.req("FR-LOAD-01")
def test_the_controller_restarts_the_load_control_with_the_plant_and_the_season() -> None:
    cfg = rooms4()
    ctrl = Controller(cfg)
    cold = states({f"r{i}": 20.0 for i in range(1, 5)})
    assert ctrl.step(T0, plan(2000), cold).steps
    later = T0 + 11 * MIN  # after the minimum run time the plan decides: it is zero
    off = ctrl.step(later, plan(0, later), cold)
    assert not off.running and off.steps == {}
    started = ctrl.step(later + MIN, plan(2000, later), cold)
    assert started.steps  # a new run starts from the standard again
    switched = ctrl.step(later + 2 * MIN, plan(2000, later), cold, season=Season.COOL)
    assert switched.season is Season.COOL and switched.steps  # a new cooling run, not the heating one
    assert all(switched.commands[rid].mode is Mode.COOL for rid in switched.steps)


@pytest.mark.req("FR-LOAD-01")
def test_two_units_one_step_above_the_start_threshold_are_the_minimum_stage() -> None:
    cfg = installation(*(room(f"r{i}", setpoint=20.0, power=700.0) for i in (1, 2, 3)))
    ctrl = Controller(cfg)
    # the units read 22: a setpoint of 22 - 2 + 0.5 = 20.5 is one step above their start threshold of 20
    result = ctrl.step(T0, plan(1300), states({"r1": 22.0, "r2": 22.0, "r3": 22.0}))
    assert sorted(result.steps.values()) == [1, 1]
    assert result.expected_w == 1300.0  # the minimum stage is Pmin
    for rid in result.steps:
        assert result.commands[rid].target_c == 20.5  # below the reading, as the unit starts nevertheless
    assert sum(1 for c in result.commands.values() if c.mode is Mode.HEAT) == 2


@pytest.mark.req("FR-LOAD-01")
def test_the_start_distance_is_set_per_unit_and_zero_puts_the_threshold_at_the_reading() -> None:
    cfg = installation(
        replace(room("a", setpoint=20.0), start_offset=0.0),
        replace(room("b", setpoint=20.0), start_offset=1.0),
    )
    result = Controller(cfg).step(T0, plan(1300), states({"a": 22.0, "b": 22.0}))
    assert result.commands["a"].target_c == 22.0 + 0.5  # threshold at the reading, one step above
    assert result.commands["b"].target_c == 22.0 - 1.0 + 0.5  # threshold 1 below the reading


@pytest.mark.req("FR-LOAD-02")
def test_a_run_from_standby_reaches_the_minimum_stage_and_teaches_nothing() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    plant = Plant(ctl, cfg, {r.id: 500.0 for r in cfg.rooms})
    for _ in range(4):
        plant.cycle(0.0)  # standby
    for _ in range(12):
        plant.cycle(1300.0)  # the plant starts: Pmin is the minimum stage, a power step has not been measured
    assert sum(ctl.steps.values()) == 2 and not ctl.model.units


def _hold(result, temps: dict[str, float], applied: set[str] | None = None) -> dict[str, RoomState]:  # noqa: ANN001
    """Room states after the devices carried out the commands of `result` (only those in `applied`)."""
    rooms = {}
    for rid, temp in temps.items():
        cmd = result.commands.get(rid)
        if cmd is not None and (applied is None or rid in applied):
            rooms[rid] = RoomState(cmd.mode, temp, False, cmd.target_c)
        else:
            rooms[rid] = RoomState(Mode.FAN, temp, False, None)
    return rooms


def _until_the_limit(ctrl: Controller, ids: tuple[str, ...], warm: dict[str, float], hot: dict[str, float]):  # noqa: ANN202
    """Two cycles of a run, then the cycle in which the rooms in `hot` reach their limit (3 K above)."""
    cold = {rid: 20.0 for rid in ids}
    first = ctrl.step(T0, plan(1300), states(cold))
    second = ctrl.step(T0 + MIN, plan(1300), _hold(first, warm))  # the outlier filter allows 2 K per cycle
    return second, ctrl.step(T0 + 2 * MIN, plan(1300), _hold(second, hot))


@pytest.mark.req("FR-LOAD-03")
def test_a_unit_at_its_limit_keeps_running_until_the_next_unit_holds_its_setpoint() -> None:
    cfg = installation(*(room(f"r{i}", setpoint=20.0, power=700.0) for i in (1, 2, 3)))
    ctrl = Controller(cfg)
    ids = ("r1", "r2", "r3")
    warm = {"r1": 21.5, "r2": 20.0, "r3": 20.0}
    hot = {"r1": 23.0, "r2": 20.0, "r3": 20.0}  # r1 is 3 above its setpoint: at its limit
    second, handover = _until_the_limit(ctrl, ids, warm, hot)
    assert set(second.steps) == {"r1", "r2"}
    assert handover.commands["r3"].mode is Mode.HEAT  # the next unit starts first ...
    assert handover.commands["r1"].mode is Mode.HEAT  # ... and r1 is not switched off yet
    assert "r1" in handover.steps and "r3" in handover.steps
    # r3 has not shown its setpoint yet: r1 stays on
    waiting = ctrl.step(T0 + 3 * MIN, plan(1300), _hold(handover, hot, applied={"r1", "r2"}))
    assert waiting.commands["r1"].mode is Mode.HEAT and "r1" in waiting.steps
    # now r2 and r3 hold their setpoints: r1 goes to standby
    done = ctrl.step(T0 + 4 * MIN, plan(1300), _hold(waiting, hot))
    assert done.commands["r1"].mode is Mode.FAN and "r1" not in done.steps
    assert set(done.steps) == {"r2", "r3"}


@pytest.mark.req("FR-LOAD-03")
def test_a_retiring_unit_goes_to_standby_after_the_maximum_time_even_if_the_next_unit_never_answers() -> None:
    cfg = installation(*(room(f"r{i}", setpoint=20.0, power=700.0) for i in (1, 2, 3)))
    ctrl = Controller(cfg)
    ids = ("r1", "r2", "r3")
    warm = {"r1": 21.5, "r2": 20.0, "r3": 20.0}
    hot = {"r1": 23.0, "r2": 20.0, "r3": 20.0}
    _, handover = _until_the_limit(ctrl, ids, warm, hot)
    assert handover.commands["r1"].mode is Mode.HEAT
    late = T0 + 13 * MIN  # more than the maximum time (10 min) later: r3 never showed its setpoint
    result = ctrl.step(late, plan(1300, late), _hold(handover, hot, applied={"r1", "r2"}))
    assert result.commands["r1"].mode is Mode.FAN and "r1" not in result.steps


@pytest.mark.req("FR-LOAD-03")
def test_without_a_unit_to_take_over_the_unit_at_its_limit_stops_at_once() -> None:
    cfg = installation(*(room(f"r{i}", setpoint=20.0, power=700.0) for i in (1, 2)))
    ctrl = Controller(cfg)
    warm = {"r1": 21.5, "r2": 21.5}
    hot = {"r1": 23.0, "r2": 23.0}
    _, result = _until_the_limit(ctrl, ("r1", "r2"), warm, hot)
    assert all(c.mode is Mode.FAN for c in result.commands.values()) and not result.steps
