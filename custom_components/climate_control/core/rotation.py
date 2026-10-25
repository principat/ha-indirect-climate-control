"""FR-LOAD-01 / FR-LOAD-04: the served rooms take turns instead of heating one room for a long time.

A lane is one indoor unit that is served (it heats towards the limit of its room). The plant runs with
one lane at the minimum load; more power adds lanes, each started half a rotation time (one over the number of
lanes) after the latest change so that the lanes do not change at once. A lane gives its room to the next one
when the rotation time is over, when the room's device temperature rose by more than its step since it became
active, or when the room is no longer eligible. The next room is the one with the largest deviation, where a
room that was just served counts with an assumed rise of one step until its device reports a new value.
The rooms are aired in between: a room without a lane is in the neutral mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from .config import RoomConfig
from .distribution import Tier

TOLERANCE_S = 5.0  # cycles are about one minute apart: a time limit counts a few seconds early


@dataclass
class Lane:
    room_id: str
    since: datetime
    start_c: float | None  # device temperature when the room became active


@dataclass
class _Assumed:
    reported_c: float  # the reading the assumption belongs to
    rise: float  # assumed rise since then, in the direction of the season


@dataclass(frozen=True)
class Turn:
    active: tuple[str, ...]  # rooms with a lane, oldest lane first
    replaced: tuple[str, ...]  # rooms that left their lane in this cycle (for the handover)


class Rotation:
    """Stateful across cycles. `step` once per cycle while the plant runs."""

    def __init__(self) -> None:
        self.lanes: list[Lane] = []
        self._assumed: dict[str, _Assumed] = {}

    def reset(self) -> None:
        self.lanes = []
        self._assumed = {}

    def effective(self, temps: Mapping[str, float], sign: float) -> dict[str, float]:
        """Device temperatures with the assumed rise of just served rooms (until new data arrives)."""
        out = dict(temps)
        for rid, assumed in self._assumed.items():
            if rid in temps and temps[rid] == assumed.reported_c:
                out[rid] = temps[rid] + sign * assumed.rise
        return out

    def step(
        self,
        now: datetime,
        rotation_s: float,
        lanes_wanted: int,
        tiers: Sequence[Tier],
        temps: Mapping[str, float],
        sign: float,
    ) -> Turn:
        order = [r for tier in tiers for group in tier for r in group]
        rooms = {r.id: r for r in order}
        for rid in [rid for rid, a in self._assumed.items() if temps.get(rid) != a.reported_c]:
            del self._assumed[rid]  # a new reading replaces the assumption
        replaced: list[str] = []
        lanes: list[Lane] = []
        latest = max((lane.since for lane in self.lanes), default=None)  # before this cycle's changes
        for lane in self.lanes:
            room = rooms.get(lane.room_id)
            if room is not None and not self._due(lane, room, now, rotation_s, temps, sign):
                lanes.append(lane)
                continue
            taken = {other.room_id for other in self.lanes} | {other.room_id for other in lanes}
            following = self._next(order, taken)
            if room is not None:
                if following is None:  # nobody else to take over: the room stays
                    lanes.append(lane)
                    continue
                self._served(room, lane, temps)
            replaced.append(lane.room_id)
            if following is not None:
                lanes.append(Lane(following.id, now, temps.get(following.id)))
        self.lanes = lanes
        while len(self.lanes) > lanes_wanted:  # fewer lanes: the room with the least deviation stops
            fullest = max(self.lanes, key=lambda lane: order.index(rooms[lane.room_id]))
            self.lanes.remove(fullest)
        if len(self.lanes) < lanes_wanted:
            stagger = rotation_s / (len(self.lanes) + 1) if self.lanes else 0.0
            if latest is None or (now - latest).total_seconds() >= stagger - TOLERANCE_S:
                following = self._next(order, {lane.room_id for lane in self.lanes})
                if following is not None:
                    self.lanes.append(Lane(following.id, now, temps.get(following.id)))
        return Turn(tuple(lane.room_id for lane in self.lanes), tuple(replaced))

    @staticmethod
    def _due(
        lane: Lane,
        room: RoomConfig,
        now: datetime,
        rotation_s: float,
        temps: Mapping[str, float],
        sign: float,
    ) -> bool:
        if (now - lane.since).total_seconds() >= rotation_s - TOLERANCE_S:
            return True
        reading = temps.get(lane.room_id)
        # the room rose by more than its step since it became active: the next room is up
        return (
            lane.start_c is not None and reading is not None and sign * (reading - lane.start_c) > room.step
        )

    @staticmethod
    def _next(order: Sequence[RoomConfig], taken: set[str]) -> RoomConfig | None:
        return next((r for r in order if r.id not in taken), None)

    def _served(self, room: RoomConfig, lane: Lane, temps: Mapping[str, float]) -> None:
        """A room that was served without a new reading is assumed to have risen by one step."""
        reading = temps.get(room.id)
        if reading is None or lane.start_c is None or reading != lane.start_c:
            self._assumed.pop(room.id, None)  # the device reported a new value: that one counts
            return
        before = self._assumed.get(room.id)
        rise = (before.rise if before is not None and before.reported_c == reading else 0.0) + room.step
        self._assumed[room.id] = _Assumed(reading, rise)
