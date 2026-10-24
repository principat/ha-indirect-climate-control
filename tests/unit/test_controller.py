from datetime import timedelta

import pytest

from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode, RoomState

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)


def _modes(result) -> dict[str, Mode]:  # noqa: ANN001
    return {rid: c.mode for rid, c in result.commands.items()}


@pytest.mark.req("FR-PLAN-02")
def test_below_stop_threshold_all_units_go_neutral() -> None:
    ctrl = Controller(installation())
    temps = {"a": 20.0, "b": 20.0, "c": 20.0}
    assert ctrl.step(T0, plan(2000), states(temps)).running
    later = T0 + 10 * MIN  # after the minimum run time
    result = ctrl.step(later, plan(600, later), states(temps, Mode.HEAT))
    assert not result.running
    assert set(_modes(result).values()) == {Mode.FAN}


@pytest.mark.req("FR-PLAN-02")
def test_no_pulse_operation_between_thresholds() -> None:
    ctrl = Controller(installation())
    temps = {"a": 20.0, "b": 20.0, "c": 20.0}
    assert not ctrl.step(T0, plan(1000), states(temps)).running
    assert ctrl.step(T0 + MIN, plan(1100), states(temps)).running
    for i in range(2, 6):
        assert ctrl.step(T0 + i * MIN, plan(800), states(temps, Mode.HEAT)).running


@pytest.mark.req("FR-PLAN-03")
def test_running_requests_at_least_pmin_and_serves_enough_units() -> None:
    ctrl = Controller(installation())
    result = ctrl.step(T0, plan(1100), states({"a": 20.0, "b": 18.0, "c": 21.0}))
    assert result.requested_w == 1300
    assert result.served == ("b", "a")  # 2 x 700 W >= 1300 W


@pytest.mark.req("FR-PLAN-04")
def test_plan_has_priority_over_regulation() -> None:
    ctrl = Controller(installation())
    warm = {"a": 23.0, "b": 23.0, "c": 23.0}
    # Plan charges although every room is above its setpoint.
    assert ctrl.step(T0, plan(2000), states(warm)).running
    # Plan stops although rooms are below setpoint: the run is not extended beyond the minimum run time.
    cool = {"a": 20.0, "b": 20.0, "c": 20.0}
    later = T0 + 10 * MIN
    result = ctrl.step(later, plan(0, later), states(cool, Mode.HEAT))
    assert not result.running and Mode.HEAT not in _modes(result).values()


@pytest.mark.req("FR-MODE-03")
def test_neutral_mode_is_fan_by_default_and_configurable() -> None:
    temps = {"a": 21.0, "b": 21.0, "c": 21.0}
    assert set(_modes(Controller(installation()).step(T0, plan(0), states(temps))).values()) == {Mode.FAN}
    ctrl = Controller(installation(neutral_mode=Mode.OFF))
    assert set(_modes(ctrl.step(T0, plan(0), states(temps))).values()) == {Mode.OFF}


@pytest.mark.req("FR-SRC-01")
def test_temperature_is_the_device_reading_as_reported_without_rounding() -> None:
    ctrl = Controller(installation(room("a")))
    result = ctrl.step(T0, plan(0), {"a": RoomState(Mode.FAN, 20.5)})
    assert result.soc_pct == pytest.approx((20.5 - 15) / 15 * 100, abs=0.01)  # 36.67 %, not 33.3 or 40
    for reading, soc in ((21.5, 43.33), (22.0, 46.67), (22.5, 50.0)):  # the half steps stay apart
        assert Controller(installation(room("a"))).step(
            T0, plan(0), {"a": RoomState(Mode.FAN, reading)}
        ).soc_pct == (pytest.approx(soc, abs=0.01))


@pytest.mark.req("FR-SAFE-01")
def test_open_window_takes_room_out_of_control() -> None:
    ctrl = Controller(installation())
    result = ctrl.step(T0, plan(2000), states({"a": 14.0, "b": 20.0, "c": 20.0}, a=True))
    assert result.commands["a"].mode == Mode.FAN
    assert "a" not in result.served
    assert result.worst_room != "a"


@pytest.mark.req("FR-SAFE-01")
def test_open_window_also_overrides_fallback() -> None:
    ctrl = Controller(installation(fallback_delay_s=0))
    result = ctrl.step(T0, None, states({"a": 20.0, "b": 20.0, "c": 20.0}, b=True))
    assert result.commands["b"].mode == Mode.FAN and result.commands["a"].mode == Mode.HEAT


@pytest.mark.req("FR-SAFE-02")
def test_below_hard_minimum_heats_without_plan_demand() -> None:
    ctrl = Controller(installation())
    result = ctrl.step(T0, plan(0), states({"a": 17.0, "b": 18.0, "c": 21.0}))
    assert not result.running
    assert result.commands["a"] == result.commands["a"].__class__(Mode.HEAT, 21.0)
    assert result.commands["b"].mode == Mode.FAN  # exactly at the absolute limit (3 below): no protection


@pytest.mark.req("FR-SAFE-02")
def test_hard_minimum_wins_over_cooling() -> None:
    ctrl = Controller(installation(overheat_s=0))
    result = ctrl.step(T0, plan(0), states({"a": 17.0, "b": 25.0, "c": 21.0}))
    assert result.commands["a"].mode == Mode.HEAT and result.commands["b"].mode == Mode.FAN


@pytest.mark.req("FR-SAFE-03")
def test_overheated_room_cools_after_one_hour() -> None:
    ctrl = Controller(installation())
    temps = {"a": 24.0, "b": 21.0, "c": 21.0}
    assert ctrl.step(T0, plan(0), states(temps)).commands["a"].mode == Mode.FAN
    assert ctrl.step(T0 + 59 * MIN, plan(0, T0 + 59 * MIN), states(temps)).commands["a"].mode == Mode.FAN
    result = ctrl.step(T0 + 60 * MIN, plan(0, T0 + 60 * MIN), states(temps))
    assert result.commands["a"].mode == Mode.COOL and result.commands["a"].target_c == 21.0


@pytest.mark.req("FR-SAFE-03")
def test_overheat_timer_resets_when_room_cools_down() -> None:
    ctrl = Controller(installation())
    ctrl.step(T0, plan(0), states({"a": 24.0, "b": 21.0, "c": 21.0}))
    ctrl.step(T0 + 30 * MIN, plan(0, T0 + 30 * MIN), states({"a": 23.0, "b": 21.0, "c": 21.0}))
    t = T0 + 70 * MIN
    result = ctrl.step(t, plan(0, t), states({"a": 24.0, "b": 21.0, "c": 21.0}))
    assert result.commands["a"].mode == Mode.FAN


@pytest.mark.req("FR-SAFE-03")
def test_no_cooling_while_any_unit_heats() -> None:
    ctrl = Controller(installation(overheat_s=0))
    result = ctrl.step(T0, plan(2000), states({"a": 25.0, "b": 20.0, "c": 20.0}))
    assert result.commands["a"].mode != Mode.COOL
    assert Mode.HEAT in _modes(result).values()


@pytest.mark.req("FR-MODE-01")
def test_heating_while_another_unit_cools_goes_via_neutral() -> None:
    ctrl = Controller(installation())
    current = {
        "a": RoomState(Mode.COOL, 25.0),
        "b": RoomState(Mode.FAN, 20.0),
        "c": RoomState(Mode.HEAT, 20.0),
    }
    result = ctrl.step(T0, plan(2000), current)
    assert _modes(result) == {"a": Mode.FAN, "b": Mode.FAN, "c": Mode.FAN}
    assert all(c.target_c is None for c in result.commands.values())
    neutral = {rid: RoomState(Mode.FAN, s.temperature_c) for rid, s in current.items()}
    result = ctrl.step(T0 + MIN, plan(2000), neutral)
    assert Mode.HEAT in _modes(result).values()
    assert all(c.target_c is not None for c in result.commands.values() if c.mode == Mode.HEAT)


@pytest.mark.req("FR-DIST-01")
def test_largest_deviation_is_served_first() -> None:
    ctrl = Controller(installation())
    result = ctrl.step(T0, plan(1300), states({"a": 21.0, "b": 18.0, "c": 20.0}))
    assert result.served[0] == "b"


@pytest.mark.req("FR-SOC-01")
def test_soc_follows_worst_room_relative_to_own_setpoint() -> None:
    cfg = installation(room("a", setpoint=22.0), room("b", setpoint=18.0))
    result = Controller(cfg).step(T0, plan(0), states({"a": 21.0, "b": 19.0}))
    assert result.worst_room == "a"  # 1 K below its setpoint, b is 1 K above its own
    assert result.soc_pct == pytest.approx(33.33, abs=0.01)  # 1 below its setpoint: 40 % - 6.67 %


@pytest.mark.req("FR-SOC-02")
def test_soc_outlier_is_ignored() -> None:
    ctrl = Controller(installation(room("a")))
    ctrl.step(T0, plan(0), states({"a": 21.0}))
    result = ctrl.step(T0 + MIN, plan(0), states({"a": 14.0}))
    assert result.soc_pct == pytest.approx(40.0)  # the outlier is ignored: still on the setpoint


@pytest.mark.req("FR-GEN-01")
def test_variable_setpoint_is_used_by_safety_and_fallback() -> None:
    ctrl = Controller(installation())
    temps = {"a": 19.0, "b": 21.0, "c": 21.0}
    # Hard minimum relative to the current setpoint 23 degC: 19 < 21 -> heat a to 23.
    result = ctrl.step(T0, plan(0), states(temps), {"a": 23.0})
    assert result.commands["a"] == result.commands["a"].__class__(Mode.HEAT, 23.0)
    ctrl = Controller(installation(fallback_delay_s=0))  # fallback without waiting
    ctrl.step(T0, None, states(temps), {"b": 19.5})
    result = ctrl.step(T0 + 4 * MIN, None, states(temps), {"b": 19.5})  # third step: all groups are on
    assert result.commands["b"].target_c == 19.5 and result.commands["c"].target_c == 21.0


@pytest.mark.req("FR-PLNR-01")
def test_overload_limit_is_per_room() -> None:
    from dataclasses import replace

    cool_room = replace(
        room("a"), band_up=1.0, limit_up=1.0, start_offset=0.0
    )  # limit 1 above the setpoint of 21
    ctrl = Controller(installation(cool_room, room("b")))
    result = ctrl.step(T0, plan(2000), states({"a": 22.0, "b": 22.0}))
    assert result.served == ("b",)  # a reached its own overload limit
    result = ctrl.step(T0, plan(2000), states({"a": 21.5, "b": 20.0}))
    assert result.commands["a"].target_c == 22.0  # 21.5 + 2 steps capped at the room's own limit
