"""FR-LOAD-05 to FR-LOAD-08, FR-SRC-02: rooms stay served until their unit has cut off, others follow."""

from datetime import timedelta

import pytest

from custom_components.climate_control.core.config import InstallationConfig
from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode, RoomState, Season
from custom_components.climate_control.core.serving import Serving, Turn

from .helpers import T0, installation, plan, room, states

MIN = timedelta(minutes=1)
IDS = ("r1", "r2", "r3")
SETPOINT = 20.0


def cfg3(**params: object) -> InstallationConfig:
    return installation(*(room(rid, setpoint=SETPOINT, power=700.0) for rid in IDS), **params)


def live_at(**readings: float) -> dict[str, float]:
    return {rid: readings.get(rid, SETPOINT) for rid in IDS}


def step(
    sv: Serving,
    cfg: InstallationConfig,
    minute: float,
    requested_w: float,
    measured_w: float | None,
    live: dict[str, float],
    max_rooms: int = 3,
    present: set[str] | None = None,
    ranked: tuple[str, ...] = IDS,
) -> Turn:
    return sv.step(
        T0 + minute * MIN,
        cfg,
        Season.HEAT,
        requested_w,
        measured_w,
        [cfg.room(rid) for rid in ranked],
        set(IDS) if present is None else present,
        live,
        max_rooms,
    )


@pytest.mark.req("FR-LOAD-05")
def test_the_room_with_the_largest_deviation_is_served_first_and_stays_served() -> None:
    cfg, sv = cfg3(), Serving()
    assert step(sv, cfg, 0, 1300, 1300, live_at()).active == ("r1",)
    for minute in range(1, 9):  # the unit heats but has not cut off yet: nothing changes
        turn = step(sv, cfg, minute, 1300, 1300, live_at(r1=20.0 + 0.3 * minute))
        assert turn.active == ("r1",) and not turn.released


@pytest.mark.req("FR-LOAD-05")
def test_the_controller_gives_the_served_unit_the_setpoint_of_its_room_without_buffer() -> None:
    for reading in (19.0, 20.0, 22.0):  # whatever the reading, the setpoint is the one of the room
        ctrl = Controller(installation(room("a", setpoint=20.0)))
        result = ctrl.step(T0, plan(1300), states({"a": reading}))
        assert result.commands["a"].mode is Mode.HEAT and result.commands["a"].target_c == 20.0


@pytest.mark.req("FR-LOAD-05")
def test_a_room_below_its_setpoint_is_served_before_one_above_it() -> None:
    ctrl = Controller(installation(room("a", setpoint=20.0), room("b", setpoint=20.0)))
    result = ctrl.step(T0, plan(1300), states({"a": 22.0, "b": 19.0}))  # the buffer comes after the setpoint
    assert result.served == ("b",)
    assert result.commands["a"].mode is Mode.FAN


@pytest.mark.req("FR-LOAD-05")
def test_the_unit_that_reached_the_cut_off_distance_is_not_served_again() -> None:
    ctrl = Controller(installation(room("a", setpoint=20.0), room("b", setpoint=20.0)))
    result = ctrl.step(T0, plan(1300), states({"a": 23.5, "b": 22.0}))  # a: 3.5 above, but b is 2 above
    assert result.served == ("b",)  # a has reached the cut-off distance and is not eligible


@pytest.mark.req("FR-LOAD-06")
def test_a_further_room_follows_when_the_power_is_below_the_request_after_the_start_up_phase() -> None:
    cfg, sv = cfg3(), Serving()
    assert step(sv, cfg, 0, 2300, 1320, live_at()).active == ("r1",)
    assert step(sv, cfg, 5, 2300, 1320, live_at()).active == ("r1",)  # inside the start-up phase
    assert step(sv, cfg, 10, 2300, 1320, live_at()).active == ("r1", "r2")
    assert step(sv, cfg, 11, 2300, 1320, live_at()).active == ("r1", "r2")  # r2 is not active yet: wait


@pytest.mark.req("FR-LOAD-06")
def test_nothing_is_added_inside_the_dead_band_and_pmax_bounds_the_rooms() -> None:
    cfg, sv = cfg3(), Serving()
    step(sv, cfg, 0, 1300, 1300, live_at())
    assert step(sv, cfg, 10, 1300, 1190, live_at()).active == ("r1",)  # 110 W below: inside 130 W
    capped, sv2 = cfg3(), Serving()
    step(sv2, capped, 0, 9000, 1300, live_at(), max_rooms=2)
    step(sv2, capped, 10, 9000, 1300, live_at(), max_rooms=2)
    assert step(sv2, capped, 20, 9000, 1300, live_at(), max_rooms=2).active == ("r1", "r2")


@pytest.mark.req("FR-LOAD-06")
def test_the_next_room_starts_at_the_join_distance_before_the_first_cuts_off() -> None:
    cfg, sv = cfg3(), Serving()
    step(sv, cfg, 0, 1300, 1300, live_at())
    assert step(sv, cfg, 1, 1300, 1300, live_at(r1=22.4)).active == ("r1",)  # 2.4 above: not yet
    turn = step(sv, cfg, 2, 1300, 1300, live_at(r1=22.5))  # 3.5 minus 1 above the setpoint
    assert turn.active == ("r1", "r2")
    assert step(sv, cfg, 3, 1300, 1300, live_at(r1=23.0, r2=20.0)).active == ("r1", "r2")  # r2 is pending


@pytest.mark.req("FR-LOAD-06")
def test_a_started_room_is_active_only_after_its_live_device_temperature_rose() -> None:
    cfg, sv = cfg3(), Serving()
    step(sv, cfg, 0, 1300, 1300, live_at())
    step(sv, cfg, 1, 1300, 1300, live_at(r1=22.5))
    assert not sv.rooms["r2"].active
    step(sv, cfg, 2, 1300, 1300, live_at(r1=23.0, r2=20.5))
    assert not sv.rooms["r2"].active  # 0.5 is below the activation rise of 1
    step(sv, cfg, 3, 1300, 1300, live_at(r1=23.0, r2=21.0))
    assert sv.rooms["r2"].active


@pytest.mark.req("FR-LOAD-06")
def test_a_room_that_never_rises_is_active_after_the_maximum_wait() -> None:
    cfg, sv = cfg3(), Serving()
    step(sv, cfg, 0, 1300, 1300, live_at())
    step(sv, cfg, 1, 1300, 1300, live_at(r1=22.5))
    step(sv, cfg, 5, 1300, 1300, live_at(r1=23.0))
    assert not sv.rooms["r2"].active
    step(sv, cfg, 12, 1300, 1300, live_at(r1=23.0))  # more than 10 minutes after its start
    assert sv.rooms["r2"].active


@pytest.mark.req("FR-LOAD-07")
def test_a_surplus_does_not_lower_the_load_inside_the_start_up_phase() -> None:
    cfg, sv = _two_active()
    turn = step(sv, cfg, 12, 1300, 3000, live_at(r1=22.0, r2=21.0))
    assert turn.active == ("r1", "r2") and not turn.released


@pytest.mark.req("FR-LOAD-07")
def test_a_surplus_releases_the_most_advanced_room_after_the_start_up_phase() -> None:
    cfg, sv = _two_active()
    turn = step(sv, cfg, 21, 1300, 3000, live_at(r1=22.0, r2=21.0))
    assert turn.released == ("r1",) and turn.active == ("r2",)  # r1 has the larger distance to its setpoint
    again = step(sv, cfg, 40, 1300, 3000, live_at(r2=21.0))
    assert again.active == ("r2",)  # a single room is never lowered


def _two_active() -> tuple[InstallationConfig, Serving]:
    """r1 served since the start, r2 added after the start-up phase and active by its rise."""
    cfg, sv = cfg3(), Serving()
    step(sv, cfg, 0, 2300, 1300, live_at())
    step(sv, cfg, 10, 2300, 1300, live_at())
    step(sv, cfg, 11, 2300, 2300, live_at(r1=21.0, r2=21.0))
    assert sv.rooms["r2"].active and set(sv.rooms) == {"r1", "r2"}
    return cfg, sv


@pytest.mark.req("FR-LOAD-08")
def test_with_several_active_rooms_the_unit_does_not_leave_before_its_replacement_is_active() -> None:
    cfg, sv = _two_active()  # r1 and r2 are active, r3 could still be served
    assert step(sv, cfg, 12, 1300, 2300, live_at(r1=22.5, r2=21.0)).active == (
        "r1",
        "r2",
        "r3",
    )  # r3 replaces r1
    cut = step(sv, cfg, 13, 1300, 2300, live_at(r1=23.5, r2=21.5, r3=20.0))
    assert not cut.released  # r1 is at the cut-off distance, but r3 has not risen yet
    waiting = step(sv, cfg, 14, 1300, 2300, live_at(r1=23.5, r2=21.5, r3=20.5))
    assert not waiting.released
    done = step(sv, cfg, 15, 1300, 2300, live_at(r1=23.5, r2=21.5, r3=21.0))
    assert done.released == ("r1",) and set(done.active) == {"r2", "r3"}


@pytest.mark.req("FR-LOAD-08")
def test_a_unit_at_the_cut_off_distance_leaves_at_once_when_the_maximum_number_of_rooms_is_served() -> None:
    cfg, sv = _two_active()
    turn = step(sv, cfg, 12, 1300, 2300, live_at(r1=23.5, r2=21.0), max_rooms=1)
    assert turn.released == ("r1",) and turn.active == ("r2",)  # no further room may start


@pytest.mark.req("FR-LOAD-08")
def test_the_only_active_room_waits_for_its_successor_which_is_started_at_once() -> None:
    cfg, sv = cfg3(), Serving()
    step(sv, cfg, 0, 1300, 1300, live_at())
    turn = step(sv, cfg, 1, 1300, 1300, live_at(r1=23.5))
    assert turn.active == ("r1", "r2") and not turn.released  # r2 starts, r1 stays until r2 is active
    waiting = step(sv, cfg, 2, 1300, 1700, live_at(r1=23.5, r2=20.5))
    assert not waiting.released  # r2 has not risen by 1 yet
    done = step(sv, cfg, 3, 1300, 1700, live_at(r1=23.5, r2=21.0))
    assert done.released == ("r1",) and done.active == ("r2",)


@pytest.mark.req("FR-LOAD-08")
def test_without_a_room_to_take_over_the_unit_at_the_cut_off_distance_leaves_at_once() -> None:
    cfg = installation(room("r1", setpoint=SETPOINT))
    sv = Serving()
    sv.step(T0, cfg, Season.HEAT, 1300, 1300, [cfg.room("r1")], {"r1"}, {"r1": 20.0}, 1)
    turn = sv.step(T0 + MIN, cfg, Season.HEAT, 1300, 1300, [], {"r1"}, {"r1": 23.5}, 1)
    assert turn.released == ("r1",) and not turn.active


@pytest.mark.req("FR-LOAD-05")
def test_a_room_that_leaves_the_control_is_released() -> None:
    cfg, sv = cfg3(), Serving()
    step(sv, cfg, 0, 1300, 1300, live_at())
    turn = step(sv, cfg, 1, 1300, 1300, live_at(), present={"r2", "r3"}, ranked=("r2", "r3"))
    assert turn.released == ("r1",) and turn.active == ("r2",)  # e.g. a window was opened in r1


def _cycle(
    ctrl: Controller,
    minute: int,
    live: dict[str, float],
    last: dict[str, tuple[Mode, float | None]] | None,
    w: float,
):  # noqa: ANN202
    """One cycle of the controller; the units show what the previous cycle commanded."""
    rooms = {
        rid: RoomState(last[rid][0] if last else Mode.FAN, t, False, last[rid][1] if last else None)
        for rid, t in live.items()
    }
    now = T0 + minute * MIN
    result = ctrl.step(now, plan(1300, now), rooms, outdoor_power_w=w)
    return result, {rid: (c.mode, c.target_c) for rid, c in result.commands.items()}


@pytest.mark.req("FR-SRC-02")
def test_a_working_unit_holds_its_value_and_the_cut_off_counts_on_the_live_value() -> None:
    ctrl = Controller(cfg3())
    result, last = _cycle(ctrl, 0, live_at(), None, 1300.0)
    assert result.served == ("r1",)
    # r1 warms up and distorts its own reading, which is held; a neutral unit may fall
    for minute, (r1, r2) in enumerate(((21.0, 19.5), (22.0, 19.0), (22.5, 19.0)), start=1):
        result, last = _cycle(ctrl, minute, live_at(r1=r1, r2=r2), last, 1300.0)
        assert result.temperatures["r1"] == SETPOINT  # held while r1 works
        assert result.temperatures["r2"] == r2  # a neutral unit counts when its reading falls
    # r1 reached 2.5 above its setpoint (the join distance): the next room starts, measured on the live value
    assert set(result.served) == {"r1", "r2"} or set(result.served) == {"r1", "r3"}
    second = next(rid for rid in result.served if rid != "r1")
    start = live_at(r1=22.5, r2=19.0)[second]
    # the new room becomes active by its live rise (1 above its reading at the start), the power rises again
    result, last = _cycle(ctrl, 4, live_at(r1=23.0, **{second: start + 0.5}), last, 1700.0)
    assert "r1" in result.served  # r1 has not cut off yet and its replacement is not active yet
    # the cut-off of r1 is its live reading of 3.5 above the setpoint
    result, last = _cycle(ctrl, 5, live_at(r1=23.5, **{second: start + 1.0}), last, 1700.0)
    assert "r1" not in result.served and second in result.served and last["r1"][0] is Mode.FAN


@pytest.mark.req("FR-SRC-02")
def test_neutral_units_can_only_fall_while_another_unit_works_and_follow_the_reading_afterwards() -> None:
    ctrl = Controller(cfg3())
    result, last = _cycle(ctrl, 0, live_at(), None, 1300.0)
    assert result.served == ("r1",)
    # r1 works and warms its neighbour r2 through the pipes: the rise of r2 does not count, a fall does
    for minute, r2, expected in ((1, 21.0, 20.0), (2, 19.5, 19.5), (3, 20.5, 19.5)):
        result, last = _cycle(ctrl, minute, live_at(r1=20.5, r2=r2), last, 1300.0)
        assert result.temperatures["r2"] == expected
    # after the settling time without any working unit the reported value counts again
    seen = {}
    for minute in (12, 13, 14, 25):
        now = T0 + minute * MIN
        rooms = {rid: RoomState(Mode.FAN, t) for rid, t in live_at(r1=20.5, r2=21.0).items()}
        seen[minute] = ctrl.step(now, plan(0, now), rooms).temperatures["r2"]
    assert seen[14] == 19.5 and seen[25] == 21.0


@pytest.mark.req("FR-SRC-02")
def test_after_a_stop_only_the_fall_of_the_reading_counts_until_it_has_settled() -> None:
    ctrl = Controller(cfg3())
    result, last = _cycle(ctrl, 0, live_at(), None, 1300.0)
    assert result.running
    result, last = _cycle(ctrl, 11, live_at(r1=19.0), last, 1300.0)
    seen = {}
    # the plan is zero from minute 12, the unit is neutral from minute 13: its reading falls, then rises
    for minute, reading in ((12, 20.5), (13, 22.0), (14, 21.0), (15, 22.0), (24, 22.0)):
        now = T0 + minute * MIN
        rooms = {rid: RoomState(Mode.FAN, t) for rid, t in live_at(r1=reading, r2=19.5).items()}
        seen[minute] = ctrl.step(now, plan(0, now), rooms).temperatures["r1"]
    assert seen[12] == 20.0  # the unit still works: held at the value from before the heating
    assert seen[13] == 22.0  # stopped: the reading is followed from here
    assert seen[14] == 21.0  # the fall counts
    assert seen[15] == 21.0  # a rise does not, the reading has not settled
    assert seen[24] == 22.0  # settled (10 minutes after the stop): the reported value counts again


@pytest.mark.req("FR-SRC-02")
def test_a_settling_time_of_zero_switches_the_freezing_off() -> None:
    ctrl = Controller(cfg3(settle_s=0.0))
    result, last = _cycle(ctrl, 0, live_at(), None, 1300.0)
    assert result.served == ("r1",)
    result, last = _cycle(ctrl, 1, live_at(r1=21.0, r2=18.5), last, 1300.0)
    assert result.temperatures["r2"] == 18.5  # a unit works, but the readings count as they are reported
