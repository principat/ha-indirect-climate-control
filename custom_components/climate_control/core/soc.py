"""FR-SOC-01 / FR-SOC-02: buffer state of charge from the worst room, filtered and smoothed."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime
from statistics import median

from .config import Parameters, RoomConfig
from .model import Season


def soc_position(offset: float, p: Parameters) -> float:
    """SOC (clamped) of a point `offset` degrees towards the charged side of the setpoint (FR-SOC-01).

    The setpoint is `soc_below_k / scale` of the way up (40 % by default); every degree is the same share.
    """
    soc = (p.soc_below_k + offset) / p.scale_k * 100.0
    return min(100.0, max(0.0, soc))


def deviation_to_soc(deviation: float, p: Parameters) -> float:
    """SOC of a room whose temperature is `deviation` degrees on the discharged side of its setpoint."""
    return soc_position(-deviation, p)


def worst_room(
    readings: Iterable[tuple[RoomConfig, float]], season: Season = Season.HEAT
) -> tuple[RoomConfig, float] | None:
    """Room with the largest deviation from its own setpoint in the direction of the season.

    Rooms past their setpoint can never be the worst while another room lags behind,
    so overheated rooms do not distort the SOC.
    """
    return max(readings, key=lambda rt: season.sign * (rt[0].setpoint_c - rt[1]), default=None)


class OutlierFilter:
    """Rejects jumps above the limit per cycle. A jump confirmed in the next cycle is accepted."""

    def __init__(self, limit_k: float) -> None:
        self._limit = limit_k
        self._accepted: dict[str, float] = {}
        self._pending: dict[str, float] = {}

    def accept(self, key: str, value: float) -> float:
        last = self._accepted.get(key)
        pending = self._pending.pop(key, None)
        if (
            last is None
            or abs(value - last) <= self._limit
            or (pending is not None and abs(value - pending) <= self._limit)
        ):
            self._accepted[key] = value
            return value
        self._pending[key] = value
        return last


class SocSmoother:
    """Median of the samples within the smoothing window."""

    def __init__(self, window_s: float) -> None:
        self._window = window_s
        self._samples: deque[tuple[datetime, float]] = deque()

    def add(self, now: datetime, value: float) -> float:
        self._samples.append((now, value))
        while (now - self._samples[0][0]).total_seconds() > self._window:
            self._samples.popleft()
        return float(median(v for _, v in self._samples))
