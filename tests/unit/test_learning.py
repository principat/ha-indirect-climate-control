"""FR-PLNR-02/03: the buffer capacity is learned from the outdoor unit power and the device temperatures."""

from datetime import datetime, timedelta

import pytest

from custom_components.climate_control.core.learning import (
    E01_MAX_KWH,
    START_E01_KWH,
    CapacityLearner,
)
from custom_components.climate_control.core.model import Season

from .helpers import T0

AREAS = {"a": 10.0, "b": 10.0}
POWER_W = 1300.0
TRUE_E01 = 0.2  # kWh per 0.1 K in the simulated plant (= 2 kWh per K)
MINUTE_KWH = POWER_W / 60 / 1000


class Plant:
    """Rooms that warm (or cool) by exactly the learned quantity per kWh, optionally with 0.5 K readings."""

    def __init__(
        self, learner: CapacityLearner, season: Season = Season.HEAT, quantize: bool = False
    ) -> None:
        self.learner = learner
        self.season = season
        self.quantize = quantize
        self.t = {"a": 20.0, "b": 20.3}
        self.now = T0
        self.power = POWER_W

    def readings(self) -> dict[str, float]:
        if not self.quantize:
            return dict(self.t)
        return {k: round(v * 2) / 2 for k, v in self.t.items()}

    def minute(self, running: bool = True, temps: dict[str, float] | None = None) -> bool:
        self.now += timedelta(minutes=1)
        if running:
            delta_k = self.season.sign * self.power / 60 / 1000 / TRUE_E01 * 0.1
            self.t = {k: v + delta_k for k, v in self.t.items()}
        return self.learner.update(
            self.now, self.season, running, temps or self.readings(), AREAS, self.power if running else 30.0
        )

    def run(self, minutes: int, **kwargs: object) -> int:
        return sum(self.minute(**kwargs) for _ in range(minutes))  # type: ignore[arg-type]


@pytest.mark.req("FR-PLNR-02")
def test_start_value_is_three_kwh_per_kelvin() -> None:
    learner = CapacityLearner()
    assert START_E01_KWH == 0.3
    assert learner.capacity_kwh_per_k(Season.HEAT) == 3.0
    assert learner.capacity_kwh_per_k(Season.COOL) == 3.0


@pytest.mark.req("FR-PLNR-02")
def test_no_estimate_from_less_than_the_minimum_window() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    # 0.35 K at 1.3 kW and 2 kWh/K take about 32 minutes; 25 minutes is clearly too short
    assert plant.run(25) == 0
    assert learner.learned[Season.HEAT].estimates == 0
    assert learner.capacity_kwh_per_k(Season.HEAT) == 3.0


@pytest.mark.req("FR-PLNR-02")
def test_first_three_windows_replace_the_start_value_by_their_median() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    plant.run(130)
    item = learner.learned[Season.HEAT]
    assert item.estimates == 3
    assert item.e01_kwh == pytest.approx(TRUE_E01, rel=0.1)
    assert learner.capacity_kwh_per_k(Season.HEAT) == pytest.approx(2.0, rel=0.1)
    assert item.updated is not None


@pytest.mark.req("FR-PLNR-02")
def test_later_estimates_move_the_value_slowly_and_by_at_most_a_quarter() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    plant.run(130)
    before = learner.learned[Season.HEAT].e01_kwh
    plant.power = POWER_W * 3  # the plant suddenly needs only a third of the energy per K: estimate far away
    plant.run(60)
    after = learner.learned[Season.HEAT].e01_kwh
    assert after != before and abs(after / before - 1) <= 0.25 * (learner.learned[Season.HEAT].estimates - 3)
    step_limit = 0.25 * before
    assert (
        abs(after - before) <= step_limit * 10
    )  # many estimates, each limited; never a jump to the estimate


@pytest.mark.req("FR-PLNR-02")
def test_half_degree_device_readings_still_give_a_usable_value() -> None:
    learner = CapacityLearner()
    plant = Plant(learner, quantize=True)
    plant.run(240)
    item = learner.learned[Season.HEAT]
    assert item.estimates >= 3
    assert item.e01_kwh == pytest.approx(TRUE_E01, rel=0.4)  # +-37 % worst case of a 0.35 K window


@pytest.mark.req("FR-PLNR-02")
def test_cooling_is_learned_separately_with_its_own_value() -> None:
    learner = CapacityLearner()
    plant = Plant(learner, Season.COOL)
    plant.run(130)
    assert learner.learned[Season.COOL].estimates == 3
    assert learner.learned[Season.COOL].e01_kwh == pytest.approx(TRUE_E01, rel=0.1)
    assert learner.learned[Season.HEAT].estimates == 0
    assert learner.capacity_kwh_per_k(Season.HEAT) == 3.0


@pytest.mark.req("FR-PLNR-02")
def test_a_plant_that_stops_discards_the_window() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    plant.run(30)  # almost a window
    plant.run(5, running=False)
    plant.run(30)  # a new run must start from zero: together 60 minutes, but in two pieces
    assert learner.learned[Season.HEAT].estimates == 0


@pytest.mark.req("FR-PLNR-02")
def test_changes_of_season_or_of_the_rooms_discard_the_window() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    plant.run(30)
    plant.minute(temps={"a": plant.t["a"]})  # a room dropped out (open window): another mean temperature
    plant.run(30)
    assert learner.learned[Season.HEAT].estimates == 0
    plant.run(10)
    plant.season = Season.COOL  # the switch turned
    plant.run(30)
    assert learner.learned[Season.COOL].estimates == 0


@pytest.mark.req("FR-PLNR-02")
def test_missing_samples_and_missing_power_discard_the_window() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    plant.run(30)
    plant.now += timedelta(minutes=10)  # no cycle for 10 minutes
    plant.run(30)
    assert learner.learned[Season.HEAT].estimates == 0
    assert not learner.update(
        plant.now + timedelta(minutes=1), Season.HEAT, True, plant.readings(), AREAS, None
    )
    plant.now += timedelta(minutes=1)
    plant.run(30)
    assert learner.learned[Season.HEAT].estimates == 0


@pytest.mark.req("FR-PLNR-02")
def test_the_first_minute_of_a_run_is_not_measured() -> None:
    learner = CapacityLearner()
    now = T0
    learner.update(now, Season.HEAT, True, {"a": 20.0, "b": 20.0}, AREAS, 1300)
    # energy of the first minute must not count: a window needs the temperature to move afterwards
    learner.update(now + timedelta(seconds=30), Season.HEAT, True, {"a": 20.0, "b": 20.0}, AREAS, 1300)
    assert learner._points == []  # noqa: SLF001


@pytest.mark.req("FR-PLNR-02")
def test_implausible_estimates_are_ignored() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    plant.power = 60_000.0  # absurd power: more than E01_MAX_KWH per 0.1 K is no capacity
    plant.t = {"a": 20.0, "b": 20.0}

    def hot_minute() -> None:
        plant.now += timedelta(minutes=1)
        plant.t = {k: v + 0.01 for k, v in plant.t.items()}
        learner.update(plant.now, Season.HEAT, True, dict(plant.t), AREAS, plant.power)

    for _ in range(120):
        hot_minute()
    assert learner.learned[Season.HEAT].estimates == 0
    assert E01_MAX_KWH < 60_000 / 60 / 1000 / 0.01 * 0.1  # the measured value was really beyond the limit


@pytest.mark.req("FR-PLNR-02")
def test_the_learned_values_survive_a_restart() -> None:
    learner = CapacityLearner()
    Plant(learner).run(130)
    stored = learner.snapshot()
    again = CapacityLearner(stored)
    assert again.learned[Season.HEAT].e01_kwh == learner.learned[Season.HEAT].e01_kwh
    assert again.learned[Season.HEAT].estimates == 3
    assert again.learned[Season.HEAT].updated == learner.learned[Season.HEAT].updated
    assert again.capacity_kwh_per_k(Season.COOL) == 3.0


@pytest.mark.req("FR-PLNR-02")
def test_unusable_stored_data_falls_back_to_the_start_value() -> None:
    for stored in ({"heat": "x"}, {"heat": {"e01_kwh": "abc"}}, {"heat": {"e01_kwh": 99}}, {"cool": {}}, {}):
        assert CapacityLearner(stored).capacity_kwh_per_k(Season.HEAT) == 3.0


@pytest.mark.req("FR-PLNR-03")
def test_reset_returns_to_the_start_values() -> None:
    learner = CapacityLearner()
    Plant(learner).run(130)
    assert learner.capacity_kwh_per_k(Season.HEAT) != 3.0
    learner.reset()
    for season in Season:
        assert learner.capacity_kwh_per_k(season) == 3.0
        assert learner.learned[season].estimates == 0 and learner.learned[season].updated is None


@pytest.mark.req("FR-PLNR-02")
def test_updated_timestamp_is_the_time_of_the_last_estimate() -> None:
    learner = CapacityLearner()
    plant = Plant(learner)
    plant.run(130)
    updated = learner.learned[Season.HEAT].updated
    assert isinstance(updated, datetime) and T0 < updated <= plant.now
