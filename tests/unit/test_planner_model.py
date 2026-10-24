from dataclasses import replace
from datetime import UTC, datetime

import pytest

from custom_components.climate_control.core.planner_model import is_night, planner_inputs

from .helpers import installation, room

CFG = installation(room("a", setpoint=22.0, area=30), room("b", setpoint=18.0, area=10))
NOON = datetime(2026, 1, 15, 12, 30, tzinfo=UTC)
NIGHT = datetime(2026, 1, 15, 22, 0, tzinfo=UTC)


@pytest.mark.req("FR-PLNR-01")
def test_lower_bounds_follow_the_control_range_and_the_absolute_limit() -> None:
    inp = planner_inputs(CFG, NOON)
    assert inp.min_charge_pct == pytest.approx(26.67)  # 40 % - 2 x 6.67 %: control range below the setpoint
    assert inp.undercharge_pct == pytest.approx(20.0)  # 40 % - 3 x 6.67 %: absolute limit below the setpoint


@pytest.mark.req("FR-PLNR-01")
def test_the_limits_do_not_depend_on_the_setpoints_themselves() -> None:
    other = installation(room("a", setpoint=25.0, area=30), room("b", setpoint=16.0, area=10))
    assert planner_inputs(other, NOON).min_charge_pct == planner_inputs(CFG, NOON).min_charge_pct
    assert planner_inputs(other, NOON).overcharge_pct == planner_inputs(CFG, NOON).overcharge_pct


@pytest.mark.req("FR-PLNR-01")
def test_static_buffer_values() -> None:
    inp = planner_inputs(CFG, NOON)
    assert inp.capacity_kwh == pytest.approx(52.5)  # 3.5 kWh/K x 15 degrees of scale (6 below + 9 above)
    assert inp.efficiency_pct == 92.0
    assert inp.max_discharge_kw == 3.5
    assert inp.max_charge_pct == pytest.approx(53.33)  # control range above the setpoint
    assert inp.overcharge_pct == pytest.approx(60.0)  # absolute limit above the setpoint
    assert inp.undercharge_cost == 0.003
    assert inp.overcharge_cost > 0


@pytest.mark.req("FR-PLNR-01")
def test_max_power_for_the_connection() -> None:
    inp = planner_inputs(CFG, NOON)
    assert inp.max_charge_kw == 3.3  # Pmax


@pytest.mark.req("FR-PLNR-01")
def test_night_setback_lowers_only_lower_bounds() -> None:
    day, night = planner_inputs(CFG, NOON), planner_inputs(CFG, NIGHT)
    assert night.min_charge_pct == pytest.approx(20.0)  # one more degree of setback
    assert night.undercharge_pct == pytest.approx(13.33)
    assert (night.max_charge_pct, night.overcharge_pct) == (day.max_charge_pct, day.overcharge_pct)
    by_hour = {t.hour: v for t, v in day.min_charge_forecast}
    assert by_hour[21] < by_hour[20] and by_hour[5] < by_hour[6] == by_hour[12]
    assert is_night(datetime(2026, 1, 1, 3), 21, 6) and not is_night(datetime(2026, 1, 1, 3), 8, 18)


@pytest.mark.req("FR-PLNR-01")
def test_late_charge_surcharge_falls_over_horizon() -> None:
    inp = planner_inputs(CFG, NOON)
    values = [v for _, v in inp.charge_cost_forecast]
    assert len(values) == 24 and values[0] == inp.charge_cost == 0.001 and values[-1] == 0.0
    assert values == sorted(values, reverse=True)


@pytest.mark.req("FR-PLNR-01")
def test_bounds_are_area_weighted_room_values() -> None:
    cfg = installation(
        replace(room("a", area=30), band_up=3.0, limit_up=4.0, band_down=1.0, limit_down=2.0),
        replace(room("b", area=10), band_up=1.0, limit_up=2.0, band_down=3.0, limit_down=4.0),
    )
    inp = planner_inputs(cfg, NOON)
    assert inp.max_charge_pct == pytest.approx(40 + 2.5 * 100 / 15, abs=0.01)  # weighted band above: 2.5
    assert inp.overcharge_pct == pytest.approx(40 + 3.5 * 100 / 15, abs=0.01)  # weighted limit above: 3.5
    assert inp.min_charge_pct == pytest.approx(40 - 1.5 * 100 / 15, abs=0.01)  # weighted band below: 1.5
    assert inp.undercharge_pct == pytest.approx(40 - 2.5 * 100 / 15, abs=0.01)  # weighted limit below: 2.5
