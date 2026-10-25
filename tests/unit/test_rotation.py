"""FR-LOAD-04: the served rooms take turns, a just served room counts with an assumed rise."""

from datetime import timedelta

import pytest

from custom_components.climate_control.core.config import RoomConfig
from custom_components.climate_control.core.distribution import Tier, rank
from custom_components.climate_control.core.rotation import Rotation

from .helpers import T0, room

SECOND = timedelta(seconds=1)
ROT = 120.0
SETPOINT = 21.0


def rooms3() -> list[RoomConfig]:
    return [room("a", setpoint=SETPOINT), room("b", setpoint=SETPOINT), room("c", setpoint=SETPOINT)]


def tiers(
    rooms: list[RoomConfig], temps: dict[str, float], rot: Rotation | None = None, sign: float = 1
) -> tuple[Tier, ...]:
    """Tiers as the controller builds them: by the deviation with the assumed rise, exact ties only."""
    eff = rot.effective(temps, sign) if rot is not None else temps
    return rank(
        [(r, sign * (r.setpoint_c - eff[r.id])) for r in rooms],
        1e-9,
        tuple(dict.fromkeys(r.power_class for r in rooms)),
    )


def at(seconds: float):  # noqa: ANN201
    return T0 + seconds * SECOND


@pytest.mark.req("FR-LOAD-04")
def test_the_first_lane_takes_the_room_with_the_largest_deviation() -> None:
    rot = Rotation()
    temps = {"a": 20.0, "b": 19.0, "c": 20.5}  # b is 2 below its setpoint
    turn = rot.step(at(0), ROT, 1, tiers(rooms3(), temps), temps, 1)
    assert turn.active == ("b",) and turn.replaced == ()


@pytest.mark.req("FR-LOAD-04")
def test_after_the_rotation_time_the_next_room_takes_over() -> None:
    rot = Rotation()
    temps = {"a": 20.0, "b": 19.0, "c": 20.5}
    rot.step(at(0), ROT, 1, tiers(rooms3(), temps), temps, 1)
    still = rot.step(at(60), ROT, 1, tiers(rooms3(), temps, rot), temps, 1)
    assert still.active == ("b",)  # inside the rotation time
    turn = rot.step(at(120), ROT, 1, tiers(rooms3(), temps, rot), temps, 1)
    assert turn.active == ("a",) and turn.replaced == (
        "b",
    )  # a (1 below) is the largest deviation of the rest


@pytest.mark.req("FR-LOAD-04")
def test_a_room_that_rose_by_more_than_its_step_is_replaced_at_once() -> None:
    rot = Rotation()
    temps = {"a": 20.0, "b": 19.0, "c": 20.5}
    rot.step(at(0), ROT, 1, tiers(rooms3(), temps), temps, 1)
    exactly = {**temps, "b": 19.5}  # exactly one step (0.5): not more
    assert rot.step(at(30), ROT, 1, tiers(rooms3(), exactly, rot), exactly, 1).active == ("b",)
    more = {**temps, "b": 20.0}  # 1.0 above the start: more than a step
    turn = rot.step(at(60), ROT, 1, tiers(rooms3(), more, rot), more, 1)
    assert turn.active != ("b",) and turn.replaced == ("b",)


@pytest.mark.req("FR-LOAD-04")
def test_cooling_mirrors_the_rise() -> None:
    rot = Rotation()
    warm = {"a": 23.0, "b": 24.0, "c": 22.0}
    rot.step(at(0), ROT, 1, tiers(rooms3(), warm, sign=-1), warm, -1)
    cooler = {**warm, "b": 22.5}  # b fell by 1.5: more than its step
    turn = rot.step(at(30), ROT, 1, tiers(rooms3(), cooler, rot, -1), cooler, -1)
    assert turn.replaced == ("b",)


@pytest.mark.req("FR-LOAD-04")
def test_a_just_served_room_counts_with_an_assumed_rise_until_its_device_reports_anew() -> None:
    rot = Rotation()
    rooms = [room("a", setpoint=SETPOINT), room("b", setpoint=SETPOINT)]
    temps = {"a": 20.0, "b": 19.0}
    rot.step(at(0), ROT, 1, tiers(rooms, temps), temps, 1)  # b
    assert rot.effective(temps, 1) == temps  # nothing assumed yet
    rot.step(at(120), ROT, 1, tiers(rooms, temps, rot), temps, 1)  # a takes over, b is assumed to have risen
    assert rot.effective(temps, 1)["b"] == pytest.approx(19.5)
    rot.step(at(240), ROT, 1, tiers(rooms, temps, rot), temps, 1)  # b again (19.5 against 20 + 0.5)
    rot.step(at(360), ROT, 1, tiers(rooms, temps, rot), temps, 1)
    assert rot.effective(temps, 1)["b"] == pytest.approx(20.0)  # two slots without a new reading: two steps
    reported = {"a": 20.0, "b": 19.5}
    rot.step(at(380), ROT, 1, tiers(rooms, reported, rot), reported, 1)
    assert rot.effective(reported, 1)["b"] == 19.5  # a new value replaces the assumption


@pytest.mark.req("FR-LOAD-04")
def test_a_new_reading_during_the_slot_means_no_assumption() -> None:
    rot = Rotation()
    rooms = [room("a", setpoint=SETPOINT), room("b", setpoint=SETPOINT)]
    temps = {"a": 20.0, "b": 19.0}
    rot.step(at(0), ROT, 1, tiers(rooms, temps), temps, 1)
    reported = {"a": 20.0, "b": 19.5}  # b reported a new value within its slot
    rot.step(at(60), ROT, 1, tiers(rooms, reported, rot), reported, 1)
    rot.step(at(120), ROT, 1, tiers(rooms, reported, rot), reported, 1)
    assert rot.effective(reported, 1) == reported


@pytest.mark.req("FR-LOAD-04")
def test_the_second_lane_starts_half_a_rotation_time_later() -> None:
    rot = Rotation()
    temps = {"a": 20.0, "b": 19.0, "c": 20.5}
    assert len(rot.step(at(0), ROT, 2, tiers(rooms3(), temps), temps, 1).active) == 1
    assert len(rot.step(at(30), ROT, 2, tiers(rooms3(), temps, rot), temps, 1).active) == 1
    assert len(rot.step(at(60), ROT, 2, tiers(rooms3(), temps, rot), temps, 1).active) == 2
    # the lanes change at different times: lane 1 at 120 s, lane 2 at 180 s
    first = rot.step(at(120), ROT, 2, tiers(rooms3(), temps, rot), temps, 1)
    assert len(first.replaced) == 1
    second = rot.step(at(180), ROT, 2, tiers(rooms3(), temps, rot), temps, 1)
    assert len(second.replaced) == 1 and second.replaced != first.replaced


@pytest.mark.req("FR-LOAD-04")
def test_fewer_lanes_stop_the_room_with_the_least_deviation() -> None:
    rot = Rotation()
    temps = {"a": 20.0, "b": 19.0, "c": 20.5}
    rot.step(at(0), ROT, 2, tiers(rooms3(), temps), temps, 1)
    two = rot.step(at(60), ROT, 2, tiers(rooms3(), temps, rot), temps, 1)
    assert set(two.active) == {"b", "a"}
    one = rot.step(at(70), ROT, 1, tiers(rooms3(), temps, rot), temps, 1)
    assert one.active == ("b",) and one.replaced == ()  # a (the smaller deviation) stops, nobody replaces it


@pytest.mark.req("FR-LOAD-04")
def test_a_room_that_is_no_longer_eligible_is_replaced_at_once() -> None:
    rot = Rotation()
    temps = {"a": 20.0, "b": 19.0, "c": 20.5}
    rot.step(at(0), ROT, 1, tiers(rooms3(), temps), temps, 1)
    without_b = [r for r in rooms3() if r.id != "b"]
    turn = rot.step(at(10), ROT, 1, tiers(without_b, temps, rot), temps, 1)
    assert turn.active == ("a",) and turn.replaced == ("b",)


@pytest.mark.req("FR-LOAD-04")
def test_the_only_room_stays_when_nobody_can_take_over() -> None:
    rot = Rotation()
    rooms = [room("a", setpoint=SETPOINT)]
    temps = {"a": 20.0}
    rot.step(at(0), ROT, 1, tiers(rooms, temps), temps, 1)
    turn = rot.step(at(300), ROT, 1, tiers(rooms, temps, rot), temps, 1)
    assert turn.active == ("a",) and turn.replaced == ()
