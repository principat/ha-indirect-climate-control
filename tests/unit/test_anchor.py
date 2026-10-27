"""FR-SOC-03 to FR-SOC-05: remembered value (anchor), display offset, its adaptation and its storage."""

from __future__ import annotations

from datetime import timedelta

import pytest

from custom_components.climate_control.core.anchor import AnchorTracker, follow
from custom_components.climate_control.core.config import Parameters, RoomConfig
from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode, RoomState, Season
from custom_components.climate_control.core.soc import room_fill, soc_of

from .helpers import T0, installation, plan, room

OFFSET = 3.5
SIGMA = Parameters().soc_sigma
MIN = timedelta(minutes=1)


def _soc(rooms: list[RoomConfig], temps: dict[str, float], season: Season = Season.HEAT) -> float:
    return soc_of([room_fill(r, temps[r.id], season) for r in rooms], SIGMA)


def _period(
    tracker: AnchorTracker,
    rooms: list[RoomConfig],
    work: list[dict[str, float]],
    after: list[dict[str, float]],
    season: Season = Season.HEAT,
) -> tuple[float, float]:
    """One work period: the cycles with a working unit, then the cycles until all units have settled.

    `after[0]` is the first cycle after the stop (the display is still high), `after[-1]` the one at which
    all units have settled. Returns the SOC at the end of the work (from the remembered values) and after
    the settling (from the readings).
    """
    for readings in work:
        tracker.step(season, rooms, readings, True, False)
    soc_end = _soc(rooms, tracker.step(season, rooms, after[0], False, False), season)
    for readings in after[1:-1]:
        tracker.step(season, rooms, readings, False, False)
    settled = tracker.step(season, rooms, after[-1], False, True)
    return soc_end, _soc(rooms, settled, season)


@pytest.mark.req("FR-SOC-03")
def test_the_anchor_follows_a_rise_only_beyond_the_offset_and_a_fall_at_once() -> None:
    anchor: float | None = None
    seen = []
    for reported in (20.0, 23.0, 24.0, 22.0, 19.5, 22.5):  # the scenario of the specification
        anchor = follow(anchor, reported, OFFSET, 1)
        seen.append(anchor)
    assert seen == [20.0, 20.0, 20.5, 20.5, 19.5, 19.5]


@pytest.mark.req("FR-SOC-03")
def test_the_anchor_never_gets_smaller_while_the_reading_rises() -> None:
    anchor: float | None = None
    last = -100.0
    for i in range(60):
        anchor = follow(anchor, 18.0 + i * 0.5, OFFSET, 1)
        assert anchor >= last
        last = anchor


@pytest.mark.req("FR-SOC-03")
def test_the_rule_is_mirrored_for_cooling() -> None:
    anchor = follow(None, 24.0, OFFSET, -1)
    assert follow(anchor, 21.0, OFFSET, -1) == 24.0  # 3 below: not beyond the offset
    assert follow(anchor, 20.0, OFFSET, -1) == 23.5  # 4 below: the anchor follows with the offset
    assert follow(23.5, 25.0, OFFSET, -1) == 25.0  # a rise (against the season) follows at once


@pytest.mark.req("FR-SOC-03")
def test_outside_a_work_period_the_readings_count_and_a_period_runs_until_all_units_settled() -> None:
    rooms = [room("a"), room("b")]
    tracker = AnchorTracker(Parameters())
    idle = {"a": 20.0, "b": 21.0}
    assert tracker.step(Season.HEAT, rooms, idle, False, True) == idle  # no unit works: readings count
    start = tracker.step(
        Season.HEAT, rooms, idle, True, False
    )  # a unit starts: the anchors start at the readings
    assert start == idle
    hot = {"a": 26.0, "b": 21.5}  # the working unit shows more, the neutral room only a little
    held = tracker.step(Season.HEAT, rooms, hot, True, False)
    assert held == {"a": 22.5, "b": 21.0}  # 26 - 3.5, and 21.5 is not beyond the offset
    stopped = {"a": 24.0, "b": 21.5}
    assert tracker.step(Season.HEAT, rooms, stopped, False, False) == held  # not settled: still anchored
    assert (
        tracker.step(Season.HEAT, rooms, stopped, True, False) == held
    )  # a unit works again: the period goes on
    assert (
        tracker.step(Season.HEAT, rooms, stopped, False, True) == stopped
    )  # settled: the readings count again
    assert tracker.step(Season.HEAT, rooms, {"a": 23.0, "b": 21.0}, False, True) == {"a": 23.0, "b": 21.0}


@pytest.mark.req("FR-SOC-03")
def test_a_room_that_rises_by_less_than_the_offset_stays_on_its_remembered_value() -> None:
    rooms = [room("a")]
    tracker = AnchorTracker(Parameters())
    tracker.step(Season.HEAT, rooms, {"a": 19.0}, True, False)
    assert tracker.step(Season.HEAT, rooms, {"a": 22.0}, True, False) == {"a": 19.0}  # accepted: undervalued


@pytest.mark.req("FR-SOC-03")
def test_the_soc_of_the_controller_is_built_from_the_remembered_values() -> None:
    cfg = installation(room("a", 21.0), soc_smoothing_s=0.0)
    ctrl = Controller(cfg)
    r = cfg.rooms[0]
    first = ctrl.step(T0, plan(2000), {"a": RoomState(Mode.FAN, 20.0)})
    assert first.soc_pct == pytest.approx(_soc([r], {"a": 20.0}), abs=0.01)
    later = T0 + MIN
    heated = ctrl.step(later, plan(2000, later), {"a": RoomState(Mode.HEAT, 23.0)})
    assert heated.soc_pct == first.soc_pct  # 23 is not beyond 20 + 3.5
    hotter = later + MIN
    result = ctrl.step(hotter, plan(2000, hotter), {"a": RoomState(Mode.HEAT, 24.5)})
    assert result.soc_pct == pytest.approx(_soc([r], {"a": 21.0}), abs=0.01)  # 24.5 - 3.5
    assert ctrl.anchor.largest == pytest.approx(3.5)  # FR-SOC-04: the largest deviation over the setpoint


@pytest.mark.req("FR-SOC-04")
def test_a_deviation_up_to_the_threshold_leaves_the_offset_unchanged() -> None:
    rooms = [room("a")]
    tracker = AnchorTracker(Parameters())
    soc_end, settled = _period(tracker, rooms, [{"a": 19.0}, {"a": 24.5}], [{"a": 24.5}, {"a": 21.0}])
    assert abs(soc_end - settled) <= 10
    assert tracker.offset == OFFSET


@pytest.mark.req("FR-SOC-04")
def test_an_overvalued_end_of_work_enlarges_the_offset_until_the_deviation_is_within_five_points() -> None:
    rooms = [room("a")]
    tracker = AnchorTracker(Parameters())
    work = [{"a": 19.0}, {"a": 27.0}]
    after = [{"a": 27.0}, {"a": 21.0}]
    soc_end, settled = _period(tracker, rooms, work, after)
    assert soc_end - settled > 10  # the offset 3.5 is too small
    assert tracker.offset > OFFSET
    again = AnchorTracker(Parameters())
    again.restore(tracker.snapshot())
    soc_again, settled_again = _period(again, rooms, work, after)
    assert abs(soc_again - settled_again) <= 5  # the new offset hits the settled SOC
    assert again.offset == tracker.offset  # nothing left to adapt


@pytest.mark.req("FR-SOC-04")
def test_an_undervalued_end_of_work_reduces_the_offset() -> None:
    rooms = [room("a")]
    tracker = AnchorTracker(Parameters(display_offset_k=7.0, offset_cap_factor=2.0))
    work = [{"a": 19.0}, {"a": 24.0}]
    after = [{"a": 24.0}, {"a": 22.0}]
    soc_end, settled = _period(tracker, rooms, work, after)
    assert settled - soc_end > 10
    assert 0 <= tracker.offset < 7.0
    again = AnchorTracker(Parameters(offset_cap_factor=2.0))
    again.restore(tracker.snapshot())
    soc_again, settled_again = _period(again, rooms, work, after)
    assert abs(soc_again - settled_again) <= 5


@pytest.mark.req("FR-SOC-04")
def test_the_offset_is_never_negative() -> None:
    rooms = [room("a")]
    tracker = AnchorTracker(Parameters(display_offset_k=0.5))
    _period(tracker, rooms, [{"a": 19.0}, {"a": 22.0}], [{"a": 22.0}, {"a": 26.0}])  # even 0 undervalues
    assert tracker.offset == 0.0


@pytest.mark.req("FR-SOC-04")
def test_the_offset_is_capped_at_1_25_times_the_largest_measured_deviation() -> None:
    rooms = [room("a", 21.0)]
    tracker = AnchorTracker(Parameters())
    # the display rises 3.5 over the setpoint, but the SOC at the end of the work is far too high
    work = [{"a": 15.0}, {"a": 24.5}]
    _period(tracker, rooms, work, [{"a": 24.5}, {"a": 15.5}])
    assert tracker.largest == pytest.approx(3.5)
    assert tracker.offset == pytest.approx(1.25 * 3.5)  # 4.375, although the adaptation asks for more


@pytest.mark.req("FR-SOC-04")
def test_a_period_with_a_changed_setpoint_or_in_fallback_is_not_evaluated() -> None:
    work, after = [{"a": 19.0}, {"a": 27.0}], [{"a": 27.0}, {"a": 21.0}]
    moved = AnchorTracker(Parameters())
    changed = [room("a", 21.0)]
    moved.step(Season.HEAT, changed, work[0], True, False)
    later = [room("a", 22.0)]  # the setpoint changes during the period
    moved.step(Season.HEAT, later, work[1], True, False)
    moved.step(Season.HEAT, later, after[0], False, False)
    moved.step(Season.HEAT, later, after[1], False, True)
    assert moved.offset == OFFSET
    fallback = AnchorTracker(Parameters())
    rooms = [room("a")]
    fallback.step(Season.HEAT, rooms, work[0], True, False)
    fallback.step(Season.HEAT, rooms, work[1], True, False)
    fallback.invalidate()
    fallback.step(Season.HEAT, rooms, after[0], False, False)
    fallback.step(Season.HEAT, rooms, after[1], False, True)
    assert fallback.offset == OFFSET


@pytest.mark.req("FR-SOC-04")
def test_without_a_measured_deviation_the_offset_is_not_adapted() -> None:
    rooms = [room("a", 25.0)]  # the display stays below the setpoint all the time
    tracker = AnchorTracker(Parameters(display_offset_k=0.5))
    soc_end, settled = _period(tracker, rooms, [{"a": 23.0}, {"a": 24.9}], [{"a": 24.9}, {"a": 23.5}])
    assert abs(soc_end - settled) > 10 and tracker.largest is None
    assert tracker.offset == 0.5


@pytest.mark.req("FR-SOC-05")
def test_the_values_survive_a_restart_and_can_be_set_by_hand() -> None:
    tracker = AnchorTracker(Parameters())
    start = tracker.revision
    tracker.set_offset(4.25)
    tracker.set_largest(3.5)
    assert tracker.revision == start + 2
    restored = AnchorTracker(Parameters())
    restored.restore(tracker.snapshot())
    assert (restored.offset, restored.largest) == (4.25, 3.5)
    restored.set_largest(None)  # empty = not measured yet
    assert restored.largest is None
    restored.set_offset(restored.offset)  # unchanged: nothing to store
    assert restored.revision == 1


@pytest.mark.req("FR-SOC-05")
def test_invalid_stored_or_given_values_are_refused() -> None:
    tracker = AnchorTracker(Parameters())
    tracker.restore({"offset": -1, "largest": "x"})
    assert (tracker.offset, tracker.largest) == (OFFSET, None)
    with pytest.raises(ValueError, match="negative"):
        tracker.set_offset(-0.5)
    with pytest.raises(ValueError, match="negative"):
        tracker.set_largest(-1.0)


@pytest.mark.req("FR-SOC-04")
def test_a_work_period_longer_than_the_kept_readings_is_not_evaluated() -> None:
    rooms = [room("a")]
    tracker = AnchorTracker(Parameters(cycle_s=14400.0))  # room for two cycles of the readings only
    work = [{"a": 19.0}, {"a": 27.0}, {"a": 27.0}]
    soc_end, settled = _period(tracker, rooms, work, [{"a": 27.0}, {"a": 21.0}])
    assert soc_end - settled > 10  # the same case as above would enlarge the offset
    assert tracker.offset == OFFSET
