from datetime import timedelta

import pytest

from custom_components.climate_control.core.config import Parameters
from custom_components.climate_control.core.soc import (
    OutlierFilter,
    SocSmoother,
    deviation_to_soc,
    soc_position,
    worst_room,
)

from .helpers import T0, room

P = Parameters()


@pytest.mark.req("FR-SOC-01")
def test_the_setpoint_is_40_percent_and_every_degree_is_6_67_percent() -> None:
    assert deviation_to_soc(0, P) == 40
    assert deviation_to_soc(1, P) == pytest.approx(33.33, abs=0.01)  # 1 below the setpoint
    assert deviation_to_soc(-1, P) == pytest.approx(46.67, abs=0.01)  # 1 above
    assert deviation_to_soc(6, P) == 0 and deviation_to_soc(-9, P) == 100  # the ends of the scale
    assert deviation_to_soc(10, P) == 0 and deviation_to_soc(-12, P) == 100  # clamped


@pytest.mark.req("FR-SOC-01")
def test_the_scale_is_a_parameter() -> None:
    wide = Parameters(soc_below_k=10.0, soc_above_k=10.0)
    assert deviation_to_soc(0, wide) == 50 and deviation_to_soc(5, wide) == 25
    assert soc_position(2.0, wide) == 60


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
    assert deviation_to_soc(cold.setpoint_c - 19.0, P) == deviation_to_soc(warm.setpoint_c - 23.0, P) == 40


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
