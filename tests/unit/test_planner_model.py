from datetime import UTC, datetime

import pytest

from custom_components.climate_control.core.planner_model import is_night, planner_inputs, weighted_setpoint

from .helpers import installation, room

CFG = installation(room("a", setpoint=22.0, area=30), room("b", setpoint=18.0, area=10))
NOON = datetime(2026, 1, 15, 12, 30, tzinfo=UTC)
NIGHT = datetime(2026, 1, 15, 22, 0, tzinfo=UTC)


@pytest.mark.req("FR-PLNR-01")
def test_weighted_lower_bounds() -> None:
    assert weighted_setpoint(CFG) == 21.0
    inp = planner_inputs(CFG, NOON)
    assert inp.min_charge_pct == 40.0  # 21 degC on 15..30
    assert inp.undercharge_pct == pytest.approx(26.67)  # 19 degC, hard minimum


@pytest.mark.req("FR-PLNR-01")
def test_static_buffer_values() -> None:
    inp = planner_inputs(CFG, NOON)
    assert inp.capacity_kwh == pytest.approx(52.5)  # 3.5 kWh/K x 15 K
    assert inp.efficiency_pct == 92.0
    assert inp.max_discharge_kw == 3.5
    assert inp.max_charge_pct == 60.0  # comfort max 24 degC
    assert inp.overcharge_pct == pytest.approx(86.67)  # overload up to 28 degC
    assert inp.undercharge_cost == 0.003
    assert inp.overcharge_cost > 0


@pytest.mark.req("FR-PLNR-01")
def test_max_power_for_the_connection() -> None:
    inp = planner_inputs(CFG, NOON)
    assert inp.max_charge_kw == 3.3  # Pmax


@pytest.mark.req("FR-PLNR-01")
def test_night_setback_lowers_only_lower_bounds() -> None:
    day, night = planner_inputs(CFG, NOON), planner_inputs(CFG, NIGHT)
    assert night.min_charge_pct < day.min_charge_pct
    assert night.undercharge_pct < day.undercharge_pct
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
