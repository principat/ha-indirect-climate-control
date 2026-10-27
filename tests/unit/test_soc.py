import math
from datetime import timedelta

import pytest

from custom_components.climate_control.core.config import Parameters, RoomConfig
from custom_components.climate_control.core.model import Season
from custom_components.climate_control.core.soc import (
    OutlierFilter,
    SocSmoother,
    position_pct,
    room_fill,
    soc_of,
    worst_room,
)

from .helpers import T0, room

P = Parameters()
SIGMA = P.soc_sigma
DEFAULT = (2.0, 3.0, 2.0, 3.0)  # control range and absolute limit, down and up


def soc(*rooms_at: tuple[RoomConfig, float], season: Season = Season.HEAT, sigma: float = SIGMA) -> float:
    return soc_of([room_fill(r, t, season) for r, t in rooms_at], sigma)


def weight(comfort: float, coldest: float = 0.0, sigma: float = SIGMA) -> float:
    return math.exp(-(comfort**2 - coldest**2) / (2 * sigma**2))


@pytest.mark.req("FR-SOC-01")
def test_the_scale_of_a_room_has_the_setpoint_in_the_middle_and_edge_zones_of_ten_percent() -> None:
    assert position_pct(0, *DEFAULT) == pytest.approx(50)
    assert position_pct(-3, *DEFAULT) == 0 and position_pct(3, *DEFAULT) == 100  # the absolute limits
    assert position_pct(-2, *DEFAULT) == pytest.approx(10) and position_pct(2, *DEFAULT) == pytest.approx(90)
    assert position_pct(-2.5, *DEFAULT) == pytest.approx(5)  # the middle of the lower edge zone
    assert position_pct(-1, *DEFAULT) == pytest.approx(30) and position_pct(1, *DEFAULT) == pytest.approx(70)
    assert position_pct(-9, *DEFAULT) == 0 and position_pct(9, *DEFAULT) == 100  # clamped


@pytest.mark.req("FR-SOC-01")
def test_the_setpoint_stays_in_the_middle_when_the_control_range_is_not_symmetric() -> None:
    lopsided = (1.0, 3.0, 3.0, 4.0)
    assert position_pct(0, *lopsided) == pytest.approx(50)
    assert position_pct(-1, *lopsided) == pytest.approx(10)  # the lower end of the control range
    assert position_pct(3, *lopsided) == pytest.approx(90)  # the upper end
    assert position_pct(-0.5, *lopsided) == pytest.approx(30)  # a steep lower half
    assert position_pct(1.5, *lopsided) == pytest.approx(70)  # a flat upper half


@pytest.mark.req("FR-SOC-01")
def test_an_edge_zone_without_width_is_a_step_at_its_edge() -> None:
    no_buffer = (2.0, 2.0, 2.0, 2.0)
    assert position_pct(-1.9, *no_buffer) == pytest.approx(12)
    assert position_pct(-2.0, *no_buffer) == pytest.approx(10)  # on the edge the zone counts as full
    assert position_pct(-2.1, *no_buffer) == 0  # beyond it as empty
    assert position_pct(2.0, *no_buffer) == pytest.approx(90) and position_pct(2.1, *no_buffer) == 100


@pytest.mark.req("FR-SOC-01")
def test_a_single_room_has_the_soc_of_its_own_scale() -> None:
    a = room("a", 21)
    assert soc((a, 21.0)) == pytest.approx(50)
    assert soc((a, 19.0)) == pytest.approx(10) and soc((a, 20.0)) == pytest.approx(30)
    assert soc((a, 18.0)) == 0 and soc((a, 24.0)) == 100


@pytest.mark.req("FR-SOC-01")
def test_the_soc_lies_between_the_worst_room_and_the_mean_and_cold_rooms_count_more() -> None:
    a, b = room("a", 19), room("b", 23)
    assert soc((a, 19.0), (b, 23.0)) == pytest.approx(50)  # both on their setpoints
    # a 2 below its setpoint (comfort fill 0, weight 1), b 1 below (fill 0.25, weight 0.71)
    both = soc((a, 17.0), (b, 22.0))
    assert both == pytest.approx(18.28, abs=0.01)
    assert 10 < both < 20  # the worst room alone: 10 %, the plain mean of the comfort fills: 20 %


@pytest.mark.req("FR-SOC-01")
def test_the_edge_zones_are_plain_means_over_the_rooms() -> None:
    a, b = room("a", 21), room("b", 21)
    # lower edge zone: a at the absolute limit (empty), b on its setpoint (full); comfort fills 0 and 0.5
    w = weight(0.5)
    comfort = 80 * (0.5 * w) / (1 + w)
    assert soc((a, 18.0), (b, 21.0)) == pytest.approx(10 * 0.5 + comfort)
    # upper edge zone: a at the absolute limit above (full), b on its setpoint (empty); fills 1 and 0.5
    w = weight(1.0, 0.5)
    comfort = 80 * (0.5 + w * 1.0) / (1 + w)
    assert soc((a, 24.0), (b, 21.0)) == pytest.approx(10 * 1 + comfort + 10 * 0.5)


@pytest.mark.req("FR-SOC-01")
def test_the_width_of_the_bell_is_a_parameter() -> None:
    a, b = room("a", 21), room("b", 21)
    rooms = ((a, 19.0), (b, 21.0))  # comfort fills 0 and 0.5
    narrow, default, wide = soc(*rooms, sigma=0.05), soc(*rooms), soc(*rooms, sigma=50.0)
    assert narrow < default < wide
    assert narrow == pytest.approx(10, abs=0.5)  # follows the coldest room
    assert wide == pytest.approx(10 + 80 * 0.25, abs=0.1)  # the mean of the two comfort fills
    assert soc(*rooms, sigma=0.001) == pytest.approx(10, abs=0.5)  # a very narrow bell does not underflow


@pytest.mark.req("FR-SOC-01")
def test_overheated_rooms_hardly_count_in_the_comfort_zone() -> None:
    a, b, c = room("a", 21), room("b", 21), room("c", 21)
    neutral = soc((a, 20.0), (b, 21.0), (c, 21.0))
    with_hot = soc((a, 20.0), (b, 21.0), (c, 29.0))  # c is far above its setpoint
    # c raises the SOC only through the upper edge zone (a third of 10 %), its comfort fill 1 hardly weighs
    assert with_hot - 10 / 3 < neutral


@pytest.mark.req("FR-SOC-01")
def test_cooling_mirrors_the_scale() -> None:
    a = room("a", 24)
    assert soc((a, 24.0), season=Season.COOL) == pytest.approx(50)
    assert soc((a, 26.0), season=Season.COOL) == pytest.approx(
        10
    )  # 2 above the setpoint: the discharged side
    assert soc((a, 22.0), season=Season.COOL) == pytest.approx(90)
    assert soc((a, 26.0), season=Season.COOL) == pytest.approx(soc((room("b", 21), 19.0)))


@pytest.mark.req("FR-SOC-01")
def test_overheated_room_does_not_distort_worst_room() -> None:
    a, b, c = room("a", 21), room("b", 21), room("c", 18)
    worst = worst_room([(a, 20.0), (b, 29.0), (c, 18.0)])
    assert worst == (a, 20.0)
    assert worst_room([]) is None


@pytest.mark.req("FR-SOC-01")
def test_each_room_is_measured_against_its_own_setpoint() -> None:
    cold, warm = room("a", 19), room("b", 23)
    # a is on its setpoint, b is 2 below its own: b is the worst although it is the warmer room
    assert worst_room([(cold, 19.0), (warm, 21.0)]) == (warm, 21.0)
    # both on their setpoints give the same SOC whatever the setpoints are
    assert soc((cold, 19.0)) == soc((warm, 23.0)) == pytest.approx(50)


@pytest.mark.req("FR-SOC-02")
def test_jump_above_limit_is_rejected_once() -> None:
    f = OutlierFilter(2.0)
    assert f.accept("a", 20) == 20
    assert f.accept("a", 22) == 22  # exactly 2 K is plausible
    assert f.accept("a", 26) == 22  # outlier
    assert f.accept("a", 22) == 22  # spike gone
    assert f.accept("a", 26) == 22
    assert f.accept("a", 26) == 26  # confirmed level shift


@pytest.mark.req("FR-SOC-02")
def test_smoothing_is_median_over_window() -> None:
    s = SocSmoother(900)
    assert s.add(T0, 40) == 40
    assert s.add(T0 + timedelta(minutes=5), 50) == 45
    assert s.add(T0 + timedelta(minutes=10), 41) == 41
    # the first sample leaves the 15-minute window
    assert s.add(T0 + timedelta(minutes=16), 60) == pytest.approx(50)
