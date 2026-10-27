"""FR-SOC-03 / FR-SOC-04: remembered value (anchor) per room for the SOC and the display offset."""

from __future__ import annotations

from array import array
from collections.abc import Mapping, Sequence
from typing import Any

from .config import Parameters, RoomConfig
from .model import Season
from .soc import room_fill, soc_of

MAX_PERIOD_S = 8 * 3600  # a longer work period is not evaluated (its readings are not kept)
SOLVER_STEPS = 50


def follow(anchor: float | None, reported: float, offset: float, sign: float) -> float:
    """The anchor after a reading (heating: `sign` 1, cooling: -1, mirrored).

    It starts at the reading, follows a fall at once and a rise only when the reading is above the anchor
    plus the offset, then with the offset as distance. It never gets smaller while the reading rises.
    """
    if anchor is None:
        return reported
    t, a = sign * reported, sign * anchor
    if t < a:
        a = t
    elif a + offset < t:
        a = t - offset
    return sign * a


class AnchorTracker:
    """The anchors of one work period and the adaptation of the display offset after it."""

    def __init__(self, params: Parameters) -> None:
        self._params = params
        self.offset = params.display_offset_k
        self.largest: float | None = None  # largest measured deviation of a reading over its setpoint
        self.revision = 0  # counts changes of `offset` and `largest` (to store them)
        self._max_cycles = max(1, int(MAX_PERIOD_S / params.cycle_s))
        self._reset_period()

    def _reset_period(self) -> None:
        self._active = False
        self._season = Season.HEAT
        self._anchors: dict[str, float] = {}
        self._series: dict[str, array[float]] = {}  # the readings of the period per room, one per cycle
        self._cycles = 0
        self._signature: tuple[object, ...] = ()
        self._rooms: tuple[RoomConfig, ...] = ()
        self._valid = True
        self._end: int | None = None  # index of the last cycle with a working unit
        self._soc_end: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {"offset": self.offset, "largest": self.largest}

    def restore(self, data: Mapping[str, Any]) -> None:
        offset, largest = data.get("offset"), data.get("largest")
        if isinstance(offset, int | float) and offset >= 0:
            self.offset = float(offset)
        if isinstance(largest, int | float) and largest >= 0:
            self.largest = float(largest)

    def set_offset(self, value: float) -> None:
        """FR-SOC-05: by hand."""
        if value < 0:
            raise ValueError("the display offset must not be negative")
        if value != self.offset:
            self.offset = value
            self.revision += 1

    def set_largest(self, value: float | None) -> None:
        """FR-SOC-05: by hand, None = not measured yet."""
        if value is not None and value < 0:
            raise ValueError("the largest deviation must not be negative")
        if value != self.largest:
            self.largest = value
            self.revision += 1

    def invalidate(self) -> None:
        """The running period is not evaluated (fallback, FR-SOC-04)."""
        self._valid = False

    def abandon(self) -> None:
        """A new season starts a new state: the period is dropped."""
        self._reset_period()

    def step(
        self,
        season: Season,
        rooms: Sequence[RoomConfig],
        reported: Mapping[str, float],
        busy: bool,
        settled: bool,
    ) -> dict[str, float]:
        """The temperatures that fill the SOC, for the rooms in `reported`.

        `busy`: a unit works. `settled`: no unit works and all have settled (end of the period).
        """
        if not self._active:
            if not busy:
                return dict(reported)
            self._active = True
            self._season = season
        signature = (season, tuple((r.id, r.setpoint_c) for r in rooms))
        if self._cycles == 0:
            self._signature = signature
        elif signature != self._signature:
            self._valid = False  # setpoint, number of rooms or window state changed
        self._rooms = tuple(rooms)
        for r in rooms:
            self._anchors[r.id] = follow(self._anchors.get(r.id), reported[r.id], self.offset, season.sign)
        if self._cycles < self._max_cycles:
            for r in rooms:
                self._series.setdefault(r.id, array("f")).append(reported[r.id])
            self._cycles += 1
        else:
            self._valid = False
        if busy:
            self._end = None
            self._measure(season, rooms, reported)
        elif self._end is None:
            self._end = self._cycles - 1
            self._soc_end = self._soc(season, rooms, self._anchors)
        if not (settled and not busy):
            return dict(self._anchors)
        self._finish(season, rooms, reported)
        return dict(reported)

    def _measure(self, season: Season, rooms: Sequence[RoomConfig], reported: Mapping[str, float]) -> None:
        deviation = max(season.sign * (reported[r.id] - r.setpoint_c) for r in rooms)
        if deviation > 0 and (self.largest is None or deviation > self.largest):
            self.largest = deviation
            self.revision += 1

    def _soc(self, season: Season, rooms: Sequence[RoomConfig], temps: Mapping[str, float]) -> float:
        return soc_of([room_fill(r, temps[r.id], season) for r in rooms], self._params.soc_sigma)

    def _finish(self, season: Season, rooms: Sequence[RoomConfig], reported: Mapping[str, float]) -> None:
        """FR-SOC-04: compare the SOC at the end of the work with the SOC after settling."""
        p = self._params
        if self._valid and self._soc_end is not None and self.largest is not None and self._end is not None:
            settled_soc = self._soc(season, rooms, reported)
            if abs(self._soc_end - settled_soc) > p.offset_threshold_pct:
                cap = p.offset_cap_factor * self.largest
                new = round(self._solve(season, settled_soc, cap), 3)
                if new != self.offset:
                    self.offset = new
                    self.revision += 1
        self._reset_period()

    def _soc_at_end(self, season: Season, offset: float) -> float:
        """The SOC at the end of the work, recomputed with another offset from the recorded readings."""
        assert self._end is not None
        anchors: dict[str, float] = {}
        for rid, readings in self._series.items():
            anchor: float | None = None
            for value in readings[: self._end + 1]:
                anchor = follow(anchor, value, offset, season.sign)
            assert anchor is not None
            anchors[rid] = anchor
        return self._soc(season, self._rooms, anchors)

    def _solve(self, season: Season, target: float, cap: float) -> float:
        """The offset in [0, cap] whose recomputed SOC at the end of the work is closest to `target`.

        A larger offset gives a lower SOC, so the interval is halved until the result is far inside
        the allowed deviation (a result within `offset_target_pct` is enough, FR-SOC-04).
        """
        if self._soc_at_end(season, 0.0) <= target:
            return 0.0
        if self._soc_at_end(season, cap) >= target:
            return cap
        low, high = 0.0, cap
        best, best_error = low, abs(self._soc_at_end(season, low) - target)
        for _ in range(SOLVER_STEPS):
            if best_error <= self._params.offset_target_pct / 10:
                break
            mid = (low + high) / 2
            soc = self._soc_at_end(season, mid)
            error = abs(soc - target)
            if error < best_error:
                best, best_error = mid, error
            if soc > target:
                low = mid
            else:
                high = mid
        return best
