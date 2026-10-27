"""FR-LOAD-01/02: load control by served rooms, power per room learned per indoor unit."""

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
from custom_components.climate_control.core.model import Mode, Season

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
    """Outdoor unit that follows the sum of true power per room with a lag, sampled once per cycle."""

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

    def settle(self, requested_w: float, cycles: int = 12) -> dict[str, int]:
        steps: dict[str, int] = {}
        for _ in range(cycles):
            steps = self.cycle(requested_w)
        return steps


def plant4() -> Plant:
    cfg = rooms4()
    return Plant(LoadControl(), cfg, {r.id: 1000.0 for r in cfg.rooms})


@pytest.mark.req("FR-LOAD-02")
def test_the_start_value_is_half_of_the_range_between_pmin_and_pmax_per_further_room() -> None:
    assert start_power_w(installation(*(room(f"r{i}") for i in range(7)))) == 1000.0
    assert start_power_w(rooms4()) == 1000.0
    model = LoadModel()
    assert model.power("r1", 1000.0) == 1000.0  # nothing learned yet


@pytest.mark.req("FR-LOAD-01")
def test_the_expected_load_is_pmin_with_one_room_and_each_further_room_adds_its_power() -> None:
    assert expected_load_w({"a": 1}, {"a": 400.0}, 1300.0) == 1300.0  # one room is Pmin
    assert expected_load_w({"a": 1, "b": 1}, {"a": 400.0, "b": 200.0}, 1300.0) == pytest.approx(1600.0)
    assert expected_load_w({"a": 1, "b": 0}, {"a": 400.0, "b": 200.0}, 1300.0) == 1300.0
    assert expected_load_w({}, {}, 1300.0) == 0.0


@pytest.mark.req("FR-LOAD-01")
def test_one_room_is_served_at_pmin_and_more_power_adds_rooms() -> None:
    plant = plant4()
    assert len(plant.settle(1300.0)) == 1 and plant.ctl.expected_w == 1300.0
    assert len(plant.settle(2300.0)) == 2  # a second room (the start value of a room is 1 kW)
    assert plant.ctl.expected_w == pytest.approx(2300.0)
    assert len(plant.settle(3300.0)) == 3


@pytest.mark.req("FR-LOAD-01")
def test_pmax_bounds_the_number_of_rooms() -> None:
    assert len(plant4().settle(9000.0, cycles=40)) == 3  # 1.3 kW + 2 x 1 kW is Pmax


@pytest.mark.req("FR-LOAD-01")
def test_nothing_changes_inside_the_dead_band() -> None:
    plant = plant4()
    assert len(plant.settle(2300.0)) == 2
    assert len(plant.settle(2300.0 + 100, cycles=14)) == 2  # 100 W is inside 130 W
    assert len(plant.settle(2300.0 + 400, cycles=14)) == 2  # one more room would not be nearer to the request
    assert len(plant.settle(3300.0, cycles=14)) == 3


@pytest.mark.req("FR-LOAD-01")
def test_lowering_stops_at_one_room() -> None:
    plant = plant4()
    assert len(plant.settle(3300.0, cycles=30)) == 3
    assert len(plant.settle(0.0, cycles=30)) == 1  # the plan drops to nothing: the floor is one room (Pmin)


@pytest.mark.req("FR-LOAD-01")
def test_rooms_that_are_no_longer_eligible_are_replaced() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    ctl.update(T0, cfg, Season.HEAT, 1300.0, ranked(cfg))
    gone = next(iter(ctl.steps))
    remaining = [r for r in cfg.rooms if r.id != gone]
    steps = ctl.update(T0 + MIN, cfg, Season.HEAT, 1300.0, ranked(cfg, rooms=remaining))
    assert gone not in steps and len(steps) == 1
    assert ctl.released == [gone]


@pytest.mark.req("FR-LOAD-02")
def test_the_power_per_room_is_learned_per_unit_from_the_settled_outdoor_power() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    true_w = {"r1": 500.0, "r2": 400.0, "r3": 600.0, "r4": 500.0}
    plant = Plant(ctl, cfg, true_w)
    for requested in (1300, 2300, 1300, 3300, 1300, 2300, 3300, 1300) * 4:
        for _ in range(25):  # the start-up phase of 10 minutes is over before the next change
            plant.cycle(float(requested))
    learned = {rid: item.learned_w for rid, item in ctl.model.units.items() if item.learned_w is not None}
    assert learned, "nothing learned"
    for value in learned.values():
        assert 200.0 <= value <= 1000.0  # moved from the start value 1 kW towards the true 0.4 to 0.6 kW
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
    plant.settle(1300.0, cycles=4)  # idle: the means before the adjustment
    ctl._begin(plant.now, {"r2": 1}, 500.0)  # noqa: SLF001  # an adjustment: an observation starts
    assert ctl._observation is not None  # noqa: SLF001
    ctl._begin(plant.now, {"r3": 1}, 500.0)  # noqa: SLF001  # another one while it waits: both are dropped
    assert ctl._observation is None  # noqa: SLF001
    assert not ctl.model.units


@pytest.mark.req("FR-LOAD-02")
def test_something_else_moving_the_load_disturbs_the_observation() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    plant = Plant(ctl, cfg, {r.id: 500.0 for r in cfg.rooms})
    plant.settle(1300.0, cycles=4)
    ctl._begin(plant.now, {"r2": 1}, 1000.0)  # noqa: SLF001  # an adjustment: an observation starts
    assert ctl._observation is not None  # noqa: SLF001
    plant.cycle(1300.0, disturbed=True)  # e.g. a room under protection started to heat
    assert ctl._observation is None  # noqa: SLF001
    plant.settle(1300.0, cycles=12)
    assert not ctl.model.units


@pytest.mark.req("FR-LOAD-02")
def test_a_power_that_never_settles_teaches_nothing_and_gives_up_after_the_maximum_time() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    plant = Plant(ctl, cfg, {r.id: 500.0 for r in cfg.rooms})
    plant.settle(1300.0, cycles=4)
    plant.cycle(2300.0)
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
    ctl.update(T0 + 3 * MIN, cfg, Season.HEAT, 2300.0, ranked(cfg))
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
def test_one_served_unit_is_the_minimum_stage() -> None:
    cfg = installation(*(room(f"r{i}", setpoint=20.0, power=700.0) for i in (1, 2, 3)))
    ctrl = Controller(cfg)
    result = ctrl.step(T0, plan(1300), states({"r1": 22.0, "r2": 22.0, "r3": 22.0}))
    assert list(result.steps.values()) == [1]
    assert result.expected_w == 1300.0  # the minimum stage is Pmin
    for rid in result.steps:
        assert (
            result.commands[rid].target_c == 22.0
        )  # above the setpoint: buffer room, setpoint plus the range 2
    assert sum(1 for c in result.commands.values() if c.mode is Mode.HEAT) == 1


@pytest.mark.req("FR-LOAD-02")
def test_a_run_from_standby_reaches_the_minimum_stage_and_teaches_nothing() -> None:
    cfg = rooms4()
    ctl = LoadControl()
    plant = Plant(ctl, cfg, {r.id: 500.0 for r in cfg.rooms})
    plant.settle(0.0, cycles=4)  # standby
    plant.settle(
        1300.0, cycles=12
    )  # the plant starts: Pmin is one room, a further room has not been measured
    assert len(ctl.steps) == 1 and not ctl.model.units
