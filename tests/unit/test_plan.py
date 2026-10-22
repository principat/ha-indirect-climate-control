from datetime import UTC, datetime, timedelta

import pytest

from custom_components.climate_control.core.model import Mode
from custom_components.climate_control.core.plan import plan_from_forecast

from .helpers import T0, installation, plan, states

HOUR = timedelta(hours=1)


def _forecast(values: list[float], start: datetime = T0) -> list[dict[str, object]]:
    return [{"time": (start + i * HOUR).isoformat(), "value": v} for i, v in enumerate(values)]


@pytest.mark.req("FR-PLAN-01")
def test_reads_power_now_and_following_hours() -> None:
    p = plan_from_forecast("1.5", "kW", _forecast([1.5, 2.0, 0.0, 3.0]), T0)
    assert p is not None
    assert p.power_at(T0 + timedelta(minutes=30)) == 1500
    assert p.power_at(T0 + HOUR) == 2000
    assert [pt.power_w for pt in p.horizon(T0, 2.5)] == [1500, 2000, 0]


@pytest.mark.req("FR-PLAN-01")
def test_accepts_mapping_layout_watts_and_naive_times() -> None:
    naive = {(T0 + i * HOUR).replace(tzinfo=None).isoformat(): v for i, v in enumerate([800, 900])}
    p = plan_from_forecast("800", "W", naive, T0)
    assert p is not None and p.power_at(T0) == 800 and p.power_at(T0 + HOUR) == 900


@pytest.mark.req("FR-PLAN-01")
def test_without_forecast_the_current_value_is_the_plan() -> None:
    p = plan_from_forecast("2", "kW", None, T0)
    assert p is not None and p.power_at(T0 + timedelta(minutes=5)) == 2000
    assert plan_from_forecast("unavailable", "kW", None, T0) is None


@pytest.mark.req("FR-PLAN-01")
def test_ignores_malformed_forecast_entries() -> None:
    fc = [{"time": "garbage", "value": 1}, {"time": T0.isoformat(), "value": "x"}, *_forecast([1.0, 1.0])]
    p = plan_from_forecast("1", "kW", fc, T0)
    assert p is not None and len(p.points) == 2


@pytest.mark.req("FR-SAFE-04")
def test_plan_is_stale_when_older_than_max_age_or_expired() -> None:
    p = plan(1500, hours=3)
    assert not p.is_stale(T0, 1800)
    assert p.is_stale(T0 + timedelta(minutes=31), 1800)
    assert p.is_stale(T0 + 3 * HOUR, 10**6)
    assert p.power_at(T0 - HOUR) is None


@pytest.mark.req("FR-SAFE-04")
def test_fallback_heats_all_units_with_standard_setpoints() -> None:
    from custom_components.climate_control.core.controller import Controller

    ctrl = Controller(installation())
    temps = {"a": 22.0, "b": 25.0, "c": 19.0}
    old = plan(2000, now=T0 - 2 * HOUR)
    for p in (None, old):
        result = ctrl.step(T0, p, states(temps))
        assert result.fallback
        assert {rid: (c.mode, c.target_c) for rid, c in result.commands.items()} == {
            rid: (Mode.HEAT, 21.0) for rid in temps
        }


@pytest.mark.req("FR-SAFE-04")
def test_single_value_plan_lives_until_max_age() -> None:
    p = plan_from_forecast("2", "kW", None, datetime(2026, 1, 1, tzinfo=UTC))
    assert p is not None
    assert not p.is_stale(datetime(2026, 1, 1, 0, 10, tzinfo=UTC), 1800)
    assert p.is_stale(datetime(2026, 1, 1, 1, 0, tzinfo=UTC), 1800)


@pytest.mark.req("FR-PLAN-01")
def test_several_planner_outputs_are_summed() -> None:
    from custom_components.climate_control.core.plan import combine

    stage1 = plan_from_forecast("1.5", "kW", _forecast([1.5, 1.5, 0.5, 0.0]), T0)
    stage2 = plan_from_forecast("0.3", "kW", _forecast([0.3, 0.0, 0.0]), T0 - timedelta(minutes=5))
    total = combine([stage1, stage2])
    assert total is not None
    assert [total.power_at(T0 + i * HOUR) for i in range(4)] == [1800, 1500, 500, None]  # ends with stage 2
    assert total.received == T0 - timedelta(minutes=5)  # as old as the oldest part
    assert combine([stage1]) is stage1


@pytest.mark.req("FR-SAFE-04")
def test_missing_planner_output_means_no_plan() -> None:
    from custom_components.climate_control.core.plan import combine

    assert combine([plan(1000), None]) is None
    assert combine([]) is None
