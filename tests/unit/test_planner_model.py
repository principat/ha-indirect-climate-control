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
    assert inp.min_charge_pct == pytest.approx(10.0)  # the lower end of the control range
    assert inp.undercharge_pct == pytest.approx(0.0)  # the absolute limit below the setpoint


@pytest.mark.req("FR-PLNR-01")
def test_the_limits_do_not_depend_on_the_setpoints_themselves() -> None:
    other = installation(room("a", setpoint=25.0, area=30), room("b", setpoint=16.0, area=10))
    assert planner_inputs(other, NOON).min_charge_pct == planner_inputs(CFG, NOON).min_charge_pct
    assert planner_inputs(other, NOON).overcharge_pct == planner_inputs(CFG, NOON).overcharge_pct


@pytest.mark.req("FR-PLNR-01")
def test_static_buffer_values() -> None:
    inp = planner_inputs(CFG, NOON)
    # 3.5 kWh/K x 4 degrees of control range, which are 80 % of the scale
    assert inp.capacity_kwh == pytest.approx(17.5)
    assert inp.efficiency_pct == 92.0
    assert inp.max_discharge_kw == 3.5
    assert inp.max_charge_pct == pytest.approx(90.0)  # the upper end of the control range
    assert inp.overcharge_pct == pytest.approx(100.0)  # the absolute limit above the setpoint
    assert inp.undercharge_cost == 0.003
    assert inp.overcharge_cost > 0


@pytest.mark.req("FR-PLNR-01")
def test_max_power_for_the_connection() -> None:
    inp = planner_inputs(CFG, NOON)
    assert inp.max_charge_kw == 3.3  # Pmax


@pytest.mark.req("FR-PLNR-01")
def test_night_setback_lowers_only_lower_bounds() -> None:
    day, night = planner_inputs(CFG, NOON), planner_inputs(CFG, NIGHT)
    # the setback of 1 uses the whole lower edge zone (the absolute limit is 1 below the control range)
    assert night.min_charge_pct == pytest.approx(0.0) and night.undercharge_pct == pytest.approx(0.0)
    wide = installation(*(replace(r, limit_down=5.0) for r in CFG.rooms))  # an edge zone of 3
    assert planner_inputs(wide, NIGHT).min_charge_pct == pytest.approx(10 * (1 - 1 / 3), abs=0.01)
    assert planner_inputs(wide, NIGHT).undercharge_pct == pytest.approx(0.0)
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
    # weighted bands: 1.5 below, 2.5 above, together 4 (80 % of the scale)
    assert inp.capacity_kwh == pytest.approx(3.5 * 4 / 0.8)
    assert (inp.min_charge_pct, inp.max_charge_pct) == (10.0, 90.0)
    assert (inp.undercharge_pct, inp.overcharge_pct) == (0.0, 100.0)
    # the weighted limit below is 2.5, so a setback of 0.5 uses half of the edge zone (1.0 wide)
    night = planner_inputs(replace(cfg, params=replace(cfg.params, night_setback_k=0.5)), NIGHT)
    assert night.min_charge_pct == pytest.approx(5.0) and night.undercharge_pct == 0.0
