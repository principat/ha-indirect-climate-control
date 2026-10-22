from datetime import timedelta

import pytest

from custom_components.climate_control.core.config import Parameters
from custom_components.climate_control.core.soc import (
    OutlierFilter,
    SocSmoother,
    temperature_to_soc,
    worst_room,
)

from .helpers import T0, room

P = Parameters()


@pytest.mark.req("FR-SOC-01")
def test_scale_15_to_30_degrees_is_0_to_100_percent() -> None:
    assert temperature_to_soc(15, P) == 0
    assert temperature_to_soc(30, P) == 100
    assert temperature_to_soc(22.5, P) == 50
    assert temperature_to_soc(10, P) == 0 and temperature_to_soc(35, P) == 100


@pytest.mark.req("FR-SOC-01")
def test_overheated_room_does_not_distort_worst_room() -> None:
    a, b, c = room("a", 21), room("b", 21), room("c", 18)
    worst = worst_room([(a, 20.0), (b, 29.0), (c, 18.0)])
    assert worst == (a, 20.0)
    assert worst_room([]) is None


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
