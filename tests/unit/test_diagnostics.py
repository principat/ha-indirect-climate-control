from dataclasses import replace

import pytest

from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.diagnostics import room_diagnostics

from .helpers import T0, installation, plan, room, states


@pytest.mark.req("FR-OBS-02")
def test_deviation_heat_demand_and_storage_per_room() -> None:
    # capacity 3.5 kWh/K split by area: a 30 m2 -> 2.625 kWh/K, b 10 m2 -> 0.875 kWh/K
    cfg = installation(
        room("a", setpoint=21.0, area=30), replace(room("b", setpoint=20.0, area=10), limit_up=5.0)
    )
    diag = room_diagnostics(cfg, {"a": 19.0, "b": 22.0})
    assert diag["a"].deviation_k == 2.0
    assert diag["a"].heat_demand_kwh == pytest.approx(5.25)
    assert diag["a"].storage_kwh == pytest.approx(2.625 * 5)  # up to the absolute limit 3 above the setpoint
    assert diag["b"].deviation_k == -2.0
    assert diag["b"].heat_demand_kwh == pytest.approx(-1.75)  # stored above the setpoint
    assert diag["b"].storage_kwh == pytest.approx(0.875 * 3)  # up to its own limit 5 above its setpoint


@pytest.mark.req("FR-OBS-02")
def test_planned_offset_is_the_power_steps_times_the_step_size_and_zero_when_not_served() -> None:
    from dataclasses import replace

    cfg = installation(replace(room("a"), step=1.0), room("b"), room("c"))
    diag = room_diagnostics(cfg, {"a": 20.0, "b": 20.0, "c": 20.0}, steps={"a": 2, "b": 3})
    assert diag["a"].offset == 2.0 and diag["b"].offset == 1.5 and diag["c"].offset == 0.0
    assert room_diagnostics(cfg, {"a": 20.0})["b"].offset == 0.0  # unknown temperature: still no offset


@pytest.mark.req("FR-OBS-02")
def test_storage_is_never_negative_and_unknown_rooms_have_no_values() -> None:
    cfg = installation(room("a"), room("b"))
    diag = room_diagnostics(cfg, {"a": 29.0})
    assert diag["a"].storage_kwh == 0.0
    assert diag["b"].deviation_k is None and diag["b"].heat_demand_kwh is None


@pytest.mark.req("FR-OBS-02")
def test_cycle_reports_the_temperatures_it_used() -> None:
    result = Controller(installation(room("a"))).step(T0, plan(0), states({"a": 20.6}))
    assert result.temperatures == {"a": 20.6}
