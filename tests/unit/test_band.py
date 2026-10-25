"""FR-BAND-01: control range and absolute limit per indoor unit, relative to the current setpoint."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode, Season
from custom_components.climate_control.core.planner_model import planner_inputs

from .helpers import T0, installation, plan, room, states

NOON = datetime(2026, 1, 15, 12, 30, tzinfo=UTC)


@pytest.mark.req("FR-BAND-01")
def test_the_standard_values_are_2_for_the_control_range_and_3_for_the_absolute_limit() -> None:
    r = room("a")
    assert (r.band_down, r.band_up, r.limit_down, r.limit_up) == (2.0, 2.0, 3.0, 3.0)
    assert (r.discharge_band(Season.HEAT), r.charge_band(Season.HEAT)) == (2.0, 2.0)


@pytest.mark.req("FR-BAND-01")
def test_the_sides_swap_with_the_season() -> None:
    r = replace(room("a"), band_down=1.0, band_up=2.0, limit_down=3.0, limit_up=4.0)
    assert (r.discharge_band(Season.HEAT), r.charge_band(Season.HEAT)) == (1.0, 2.0)
    assert (r.discharge_limit(Season.HEAT), r.charge_limit(Season.HEAT)) == (3.0, 4.0)
    assert (r.discharge_band(Season.COOL), r.charge_band(Season.COOL)) == (2.0, 1.0)
    assert (r.discharge_limit(Season.COOL), r.charge_limit(Season.COOL)) == (4.0, 3.0)


@pytest.mark.req("FR-BAND-01")
def test_below_the_absolute_limit_the_room_is_heated_without_a_plan() -> None:
    cfg = installation(replace(room("a"), limit_down=1.5, band_down=1.0), room("b"))
    result = Controller(cfg).step(
        T0, plan(0), states({"a": 19.0, "b": 19.0})
    )  # both 2 below their setpoint of 21
    assert result.commands["a"].mode is Mode.HEAT  # beyond its own limit of 1.5
    assert result.commands["b"].mode is Mode.FAN  # within the standard limit of 3


@pytest.mark.req("FR-BAND-01")
def test_above_the_absolute_limit_the_room_is_not_heated_any_further() -> None:
    cfg = installation(replace(room("a"), band_up=0.5, limit_up=1.0, start_offset=0.0), room("b"))
    result = Controller(cfg).step(T0, plan(2000), states({"a": 22.0, "b": 22.0}))
    assert result.served == ("b",)  # a is 1 above its setpoint: at its limit
    near = Controller(cfg).step(T0, plan(2000), states({"a": 21.5, "b": 21.5}))
    # a would get 21.5 + its step of 0.5 (no start distance), but never beyond 1 above its setpoint of 21
    assert near.commands["a"].target_c == 22.0 and near.commands["a"].mode is Mode.HEAT


@pytest.mark.req("FR-BAND-01")
def test_the_limits_follow_a_changed_setpoint() -> None:
    cfg = installation(room("a"))
    low = Controller(cfg).step(T0, plan(0), states({"a": 18.5}))
    assert low.commands["a"].mode is Mode.FAN  # 2.5 below 21: inside the limit of 3
    raised = Controller(cfg).step(T0, plan(0), states({"a": 18.5}), {"a": 23.0})
    assert raised.commands["a"].mode is Mode.HEAT  # 4.5 below the raised setpoint: beyond the limit
    assert raised.soc_pct is not None and low.soc_pct is not None and raised.soc_pct < low.soc_pct


@pytest.mark.req("FR-BAND-01")
def test_the_planner_gets_the_bands_not_fixed_temperatures() -> None:
    wide = installation(replace(room("a"), band_down=4.0, limit_down=5.0, band_up=3.0, limit_up=4.0))
    inp = planner_inputs(wide, NOON)
    assert inp.min_charge_pct == pytest.approx(40 - 4 * 100 / 15, abs=0.01)
    assert inp.undercharge_pct == pytest.approx(40 - 5 * 100 / 15, abs=0.01)
    assert inp.max_charge_pct == pytest.approx(40 + 3 * 100 / 15, abs=0.01)
    assert inp.overcharge_pct == pytest.approx(40 + 4 * 100 / 15, abs=0.01)
    moved = installation(
        replace(room("a", setpoint=25.0), band_down=4.0, limit_down=5.0, band_up=3.0, limit_up=4.0)
    )
    assert (
        planner_inputs(moved, NOON).min_charge_pct == inp.min_charge_pct
    )  # the setpoint itself does not matter
