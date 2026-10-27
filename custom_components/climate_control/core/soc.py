"""FR-SOC-01 / FR-SOC-02: buffer state of charge from all rooms, filtered and smoothed."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from .config import RoomConfig
from .model import Season

EDGE = 0.10  # share of the SOC scale of each of the two edge zones; the comfort zone gets the rest


@dataclass(frozen=True)
class Fill:
    """Fill of the three sections of the SOC scale of a room, each from 0 (lower end) to 1 (upper end)."""

    low: float  # lower edge zone: from the absolute limit to the lower end of the control range
    comfort: float  # control range, the setpoint is exactly in the middle (0.5)
    high: float  # upper edge zone: from the upper end of the control range to the absolute limit


def fill(d: float, lo_band: float, lo_limit: float, up_band: float, up_limit: float) -> Fill:
    """Fill for the distance `d` to the setpoint, positive towards the charged side (FR-SOC-01).

    An edge zone without width (control range equal to the absolute limit) is a step at its edge.
    """
    if d >= -lo_band:
        low = 1.0
    elif d <= -lo_limit:
        low = 0.0
    else:
        low = (d + lo_limit) / (lo_limit - lo_band)
    if d <= -lo_band:
        comfort = 0.0
    elif d >= up_band:
        comfort = 1.0
    elif d < 0:
        comfort = 0.5 * (d + lo_band) / lo_band
    else:
        comfort = 0.5 + 0.5 * d / up_band
    if d <= up_band:
        high = 0.0
    elif d >= up_limit:
        high = 1.0
    else:
        high = (d - up_band) / (up_limit - up_band)
    return Fill(low, comfort, high)


def position_pct(d: float, lo_band: float, lo_limit: float, up_band: float, up_limit: float) -> float:
    """SOC (0 to 100) of one room whose temperature is `d` away from its setpoint."""
    f = fill(d, lo_band, lo_limit, up_band, up_limit)
    return 100.0 * (EDGE * f.low + (1 - 2 * EDGE) * f.comfort + EDGE * f.high)


def room_fill(room: RoomConfig, temperature_c: float, season: Season = Season.HEAT) -> Fill:
    """Fill of a room whose device shows `temperature_c`, against its current setpoint."""
    return fill(
        season.sign * (temperature_c - room.setpoint_c),
        room.discharge_band(season),
        room.discharge_limit(season),
        room.charge_band(season),
        room.charge_limit(season),
    )


def soc_of(fills: Sequence[Fill], sigma: float) -> float:
    """SOC of the plant: 10 % mean of the lower edge zones, 80 % weighted mean of the comfort zones and
    10 % mean of the upper edge zones. The weight is the cold half of a bell curve over the comfort zone."""
    n = len(fills)
    low = sum(f.low for f in fills) / n
    high = sum(f.high for f in fills) / n
    # relative to the coldest room, so that a narrow bell cannot underflow to a sum of zero
    coldest = min(f.comfort for f in fills)
    weights = [math.exp(-(f.comfort**2 - coldest**2) / (2 * sigma**2)) for f in fills]
    comfort = sum(w * f.comfort for w, f in zip(weights, fills, strict=True)) / sum(weights)
    return 100.0 * (EDGE * low + (1 - 2 * EDGE) * comfort + EDGE * high)


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
