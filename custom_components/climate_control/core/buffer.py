"""FR-OPM-05 / FR-OPM-06: buffer control. The units keep the comfort temperature themselves, the buffer is the
range above the setpoint of each room (below it when cooling) and is charged by raising setpoints in steps."""

from __future__ import annotations

from collections.abc import Sequence

from .config import RoomConfig
from .model import Season


def scale_k(room: RoomConfig, season: Season, setback: float) -> float:
    """Width of the buffer scale of a room: the night setback below the setpoint plus the range above it."""
    return setback + room.charge_band(season)


def stored_k(room: RoomConfig, temperature: float, season: Season, setback: float) -> float:
    """How far the device temperature of a room is inside its buffer scale, counted from the lowest point of
    the scale (the setpoint lowered by the night setback)."""
    low = room.setpoint_c - season.sign * setback
    return min(scale_k(room, season, setback), max(0.0, season.sign * (temperature - low)))


def is_full(room: RoomConfig, temperature: float, season: Season) -> bool:
    """The room has reached the end of its buffer range above the setpoint."""
    return season.sign * (temperature - room.setpoint_c) >= room.charge_band(season)


def buffer_soc(readings: Sequence[tuple[RoomConfig, float]], season: Season, setback: float) -> float:
    """SOC (0 to 100): the buffer scales of all rooms are added, so are the stored parts (FR-OPM-05).
    The night setback is the part of the buffer below the setpoint."""
    total = sum(scale_k(r, season, setback) for r, _ in readings)
    if total <= 0:
        return 0.0
    return 100.0 * sum(stored_k(r, t, season, setback) for r, t in readings) / total


def room_steps(room: RoomConfig, season: Season) -> int:
    """Setpoint steps the buffer range of a room consists of (at least one)."""
    return max(1, round(room.charge_band(season) / room.step))


def power_steps(requested_w: float, p_max_w: float, total_steps: int) -> int:
    """FR-OPM-06: the maximum power is spread over all buffer steps; the request is rounded to whole steps."""
    if total_steps <= 0 or requested_w <= 0:
        return 0
    return min(total_steps, max(1, round(requested_w / (p_max_w / total_steps))))


def allocate(capacity: Sequence[tuple[str, int]], steps: int, start: int = 0) -> dict[str, int]:
    """Round robin: one step per room in turn, beginning at `start`, until all `steps` are placed or every
    room has reached its capacity."""
    result = {rid: 0 for rid, _ in capacity}
    n = len(capacity)
    remaining = steps
    while remaining > 0 and n:
        placed = False
        for i in range(n):
            rid, cap = capacity[(start + i) % n]
            if remaining > 0 and result[rid] < cap:
                result[rid] += 1
                remaining -= 1
                placed = True
        if not placed:
            break
    return result
