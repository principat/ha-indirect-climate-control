"""FR-SOC-01 / FR-SOC-02: buffer state of charge from the worst room, filtered and smoothed."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime
from statistics import median

from .config import Parameters, RoomConfig
from .model import Season


def temperature_to_soc(t: float, p: Parameters, season: Season = Season.HEAT) -> float:
    """Linear SOC scale, clamped. Heating: min = 0 %, max = 100 %. Cooling: mirrored (FR-SEAS-02)."""
    soc = (t - p.soc_min_c) / (p.soc_max_c - p.soc_min_c) * 100.0
    if season is Season.COOL:
        soc = 100.0 - soc
    return min(100.0, max(0.0, soc))


def worst_room(
    readings: Iterable[tuple[RoomConfig, float]], season: Season = Season.HEAT
) -> tuple[RoomConfig, float] | None:
    """Room with the largest deviation from its own setpoint in the direction of the season.

    Rooms past their setpoint can never be the worst while another room lags behind,
    so overheated rooms do not distort the SOC.
    """
    return min(readings, key=lambda rt: season.sign * (rt[1] - rt[0].setpoint_c), default=None)


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
