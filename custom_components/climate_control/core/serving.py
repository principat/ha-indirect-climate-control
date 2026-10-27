"""FR-LOAD-05 to FR-LOAD-08: served rooms stay served until their unit has cut off.

A served room is an indoor unit that heats (or cools) towards the setpoint of its room. It stays served until
its device temperature is the cut-off distance beyond the setpoint (the unit regulates itself down there).
More rooms are added in the order of the deviation, never at once:

- when the measured outdoor power falls below the request after the start-up phase,
- when a served room has reached the join distance (the cut-off distance minus a margin) and has no
  replacement yet, so that the replacement starts before the room cuts off and has time to draw load; a room
  that has cut off counts no longer against the maximum number of rooms.

A room that was added counts as active only when its live device temperature rose by the activation rise since
its start. A room at the cut-off distance is never released before its replacement is active; without a room
that could replace it, it leaves at once. A surplus of the measured power over the request releases the most
advanced room once the start-up phase is over.

All distances are measured on the live device temperature of the served room, never on the held one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from .config import InstallationConfig, RoomConfig
from .model import Season

EPS = 1e-9


@dataclass
class Served:
    room_id: str
    since: datetime
    start_c: float | None  # live device temperature when the room became served
    active: bool = False  # FR-LOAD-06: the device temperature rose by the activation rise
    replaces: str | None = None  # FR-LOAD-08: the room this one takes over from when that cuts off


@dataclass(frozen=True)
class Turn:
    active: tuple[str, ...]  # served rooms, oldest first
    released: tuple[str, ...]  # rooms that left in this cycle


class Serving:
    """Stateful across cycles. `step` once per cycle while the plant runs."""

    def __init__(self) -> None:
        self.rooms: dict[str, Served] = {}
        self._last_change: datetime | None = None

    def reset(self) -> None:
        self.rooms = {}
        self._last_change = None

    def step(
        self,
        now: datetime,
        cfg: InstallationConfig,
        season: Season,
        requested_w: float,
        measured_w: float | None,
        ranked: Sequence[RoomConfig],
        present: set[str],
        live: Mapping[str, float],
        max_rooms: int,
        room_w: float = 0.0,
    ) -> Turn:
        """`ranked`: eligible rooms, most urgent first. `present`: rooms that are in the control at all.
        `live`: reported device temperatures, `measured_w`: the outdoor power (None: no measurement),
        `room_w`: the power a further room adds (a room is only added or released when that brings the
        measured power nearer to the request, otherwise it would swing between two stages)."""
        p = cfg.params
        sign = season.sign
        dead = p.load_deadband_ratio * cfg.p_min_w
        cut = p.cutoff_k
        join = p.cutoff_k - p.join_margin_k
        by_id = {r.id: r for r in cfg.rooms}
        released: list[str] = []

        def excess(s: Served) -> float:
            reading = live.get(s.room_id)
            return sign * (reading - by_id[s.room_id].setpoint_c) if reading is not None else 0.0

        def room_count() -> int:  # a room that has cut off is no longer a room that works
            return sum(1 for s in self.rooms.values() if excess(s) < cut - EPS)

        for rid in [rid for rid in self.rooms if rid not in present or rid not in by_id]:
            del self.rooms[rid]
            released.append(rid)
        for s in self.rooms.values():
            reading = live.get(s.room_id)
            if not s.active:
                # without a reading there is nothing to wait for
                rose = (
                    reading is None
                    or s.start_c is None
                    or sign * (reading - s.start_c) >= p.activation_rise_k - EPS
                )
                if rose or (now - s.since).total_seconds() >= p.load_settle_max_s:
                    s.active = True
        candidates = [r for r in ranked if r.id not in self.rooms]
        # FR-LOAD-08: a room at the cut-off distance leaves once its replacement is active
        for s in sorted((s for s in self.rooms.values() if excess(s) >= cut - EPS), key=excess, reverse=True):
            replacement = next((o for o in self.rooms.values() if o.replaces == s.room_id), None)
            # without a replacement it leaves only when nothing can replace it
            ready = replacement.active if replacement else not candidates or room_count() >= max_rooms
            if ready:
                del self.rooms[s.room_id]
                released.append(s.room_id)
        # FR-LOAD-06: further rooms, one at a time
        served = list(self.rooms.values())
        pending = any(not s.active for s in served)
        waited = (now - self._last_change).total_seconds() if self._last_change is not None else float("inf")
        settled = waited >= p.startup_s
        undershot = settled and measured_w is not None and requested_w - measured_w > max(dead, room_w / 2)
        replaced = {s.replaces for s in served if s.replaces is not None}
        needy = sorted(
            (s for s in served if excess(s) >= join - EPS and s.room_id not in replaced),
            key=excess,
            reverse=True,
        )
        counted = room_count()
        want = not served or (not pending and (undershot or bool(needy)))
        if want and candidates and counted < max_rooms:
            first = candidates[0]
            self.rooms[first.id] = Served(
                first.id, now, live.get(first.id), replaces=needy[0].room_id if needy else None
            )
            self._last_change = now
        elif released:
            self._last_change = now

        # FR-LOAD-07: a surplus releases the most advanced room, not within the start-up phase
        served = list(self.rooms.values())
        over = settled and measured_w is not None and measured_w - requested_w > max(dead, room_w / 2)
        if over and len(served) > 1 and all(s.active for s in served) and not released:
            most = max(served, key=excess)
            del self.rooms[most.room_id]
            released.append(most.room_id)
            self._last_change = now

        return Turn(tuple(self.rooms), tuple(released))
