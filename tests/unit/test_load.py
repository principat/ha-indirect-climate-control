"""FR-LOAD-01/02: load control on temperature events, power per step learned per indoor unit."""

from dataclasses import replace
from datetime import timedelta

import pytest

from custom_components.climate_control.core.config import InstallationConfig
from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.load import (
    LoadControl,
    LoadModel,
    start_power_w,
)
from custom_components.climate_control.core.model import Mode, Season

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)
IDLE_W = 20.0


def rooms4(**per_room: float) -> InstallationConfig:
    return installation(*(room(f"r{i}", power=700.0) for i in range(1, 5)), **per_room)


def ranked(cfg: InstallationConfig, season: Season = Season.HEAT):  # noqa: ANN202
    return list(cfg.rooms)


class Plant:
    """Outdoor unit that follows the sum of true power per step with a lag, sampled once per cycle."""

    def __init__(
        self, ctl: LoadControl, cfg: InstallationConfig, true_w: dict[str, float], alpha: float = 0.6
    ) -> None:
        self.ctl, self.cfg, self.true_w, self.alpha = ctl, cfg, true_w, alpha
        self.power = IDLE_W
        self.now = T0

    def cycle(self, requested_w: float, disturbed: bool = False) -> dict[str, int]:
        target = IDLE_W + sum(self.true_w[rid] * n for rid, n in self.ctl.steps.items())
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
        assert sum(steps.values()) * 250 == pytest.approx(ctl.expected_w)


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
def test_a_step_moves_two_units_one_of_the_largest_and_one_of_the_smallest_class() -> None:
    cfg = installation(
        room("big1", power=900.0),
        room("small", power=500.0),
        room("big2", power=900.0),
        room("mid", power=700.0),
    )
    ctl = LoadControl()
    steps = ctl.update(T0, cfg, Season.HEAT, 1300.0, ranked(cfg))
    # the first pair is the first unit of the largest class and the first of the smallest class
    assert steps.get("big1", 0) > 0 and steps.get("small", 0) > 0
    assert (
        "big2" not in steps and "mid" not in steps
    )  # setpoints first, more units only when these are used up


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
    steps = ctl.update(T0 + MIN, cfg, Season.HEAT, 2000.0, remaining)
    assert gone not in steps and sum(steps.values()) > 0


@pytest.mark.req("FR-LOAD-01")
def test_the_controller_sets_the_setpoint_beyond_the_device_temperature_by_the_steps() -> None:
    cfg = rooms4()
    ctrl = Controller(cfg)
    result = ctrl.step(T0, plan(2000), states({f"r{i}": 20.0 for i in range(1, 5)}))
    assert result.steps and sum(result.steps.values()) >= 2
    for rid, n in result.steps.items():
        assert result.commands[rid].mode is Mode.HEAT
        assert result.commands[rid].target_c == pytest.approx(20.0 + n * 0.5)
    idle = [rid for rid in (f"r{i}" for i in range(1, 5)) if rid not in result.steps]
    assert all(result.commands[rid].mode is Mode.FAN for rid in idle)
    assert result.expected_w == pytest.approx(sum(250.0 * n for n in result.steps.values()))


@pytest.mark.req("FR-LOAD-01")
def test_the_step_size_is_set_per_unit() -> None:
    cfg = installation(replace(room("a"), step=1.0), room("b"))
    ctrl = Controller(cfg)
    result = ctrl.step(T0, plan(1500), states({"a": 20.0, "b": 20.0}))
    assert result.commands["a"].target_c == pytest.approx(20.0 + result.steps["a"] * 1.0)
    assert result.commands["b"].target_c == pytest.approx(20.0 + result.steps["b"] * 0.5)


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
