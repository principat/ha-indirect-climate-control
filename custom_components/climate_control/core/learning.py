"""FR-PLNR-02: the buffer capacity is learned from operation, separately for heating and cooling.

Measured quantity: electrical energy of the outdoor unit per 0.1 K change of the area-weighted mean device
temperature. Every estimate rests on a change of at least `MIN_WINDOW_K` (the devices report in 0.5 K steps,
the weighted mean jumps by up to 0.13 K, so a single 0.1 K step is too coarse). Nothing but the measured power
and the device temperatures is used.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Any

from .model import Season

STEP_K = 0.1  # reference quantity of the learned energy and spacing of the window points
MIN_WINDOW_K = 0.35
START_E01_KWH = 0.3  # = 3 kWh per K
SETTLE_S = 60.0  # a run younger than this is not measured
MIN_WINDOW_S = 60.0
MAX_GAP_S = 300.0  # longer without a sample: the window is dropped
E01_MIN_KWH = 0.03
E01_MAX_KWH = 3.0
BOOTSTRAP_ESTIMATES = (
    3  # the first estimates, taken from disjoint windows, replace the start value by their median
)
RATE = 0.2  # weight of a later estimate
MAX_CHANGE = 0.25  # largest relative change by one estimate


@dataclass
class Learned:
    """Learned value of one season."""

    e01_kwh: float = START_E01_KWH
    estimates: int = 0
    updated: datetime | None = None
    bootstrap: list[float] = field(default_factory=list)

    @property
    def capacity_kwh_per_k(self) -> float:
        return round(self.e01_kwh / STEP_K, 3)


@dataclass
class _Point:
    temperature_c: float
    energy_kwh: float
    at: datetime


class CapacityLearner:
    """Stateful across cycles. Feed it every cycle with `update`."""

    def __init__(self, stored: Mapping[str, Any] | None = None) -> None:
        self.learned = {season: Learned() for season in Season}
        self._reset_window()
        if stored:
            self.restore(stored)

    # -- state ---------------------------------------------------------------------------------

    def capacity_kwh_per_k(self, season: Season) -> float:
        return self.learned[season].capacity_kwh_per_k

    def reset(self) -> None:
        """Back to the start values (for fundamental changes to the plant)."""
        self.learned = {season: Learned() for season in Season}
        self._reset_window()

    def snapshot(self) -> dict[str, Any]:
        return {
            season.value: {
                "e01_kwh": item.e01_kwh,
                "estimates": item.estimates,
                "updated": item.updated.isoformat() if item.updated else None,
                "bootstrap": list(item.bootstrap),
            }
            for season, item in self.learned.items()
        }

    def restore(self, stored: Mapping[str, Any]) -> None:
        for season in Season:
            raw = stored.get(season.value)
            if not isinstance(raw, Mapping):
                continue
            try:
                e01 = float(raw["e01_kwh"])
                if not E01_MIN_KWH <= e01 <= E01_MAX_KWH:
                    continue
                updated = raw.get("updated")
                self.learned[season] = Learned(
                    e01_kwh=e01,
                    estimates=int(raw.get("estimates", 0)),
                    updated=datetime.fromisoformat(updated) if updated else None,
                    bootstrap=[float(v) for v in raw.get("bootstrap", [])][:BOOTSTRAP_ESTIMATES],
                )
            except KeyError, TypeError, ValueError:
                continue

    # -- measurement ---------------------------------------------------------------------------

    def _reset_window(self) -> None:
        self._season: Season | None = None
        self._rooms: frozenset[str] = frozenset()
        self._start: datetime | None = None
        self._last: tuple[datetime, float] | None = None
        self._energy_kwh = 0.0
        self._points: list[_Point] = []

    def update(
        self,
        now: datetime,
        season: Season,
        running: bool,
        temps: Mapping[str, float],
        areas: Mapping[str, float],
        power_w: float | None,
    ) -> bool:
        """One sample. `temps` are the device temperatures of the rooms in the control (windows closed).

        Returns True if the learned value changed.
        """
        if not running or power_w is None or not temps:
            self._reset_window()
            return False
        rooms = frozenset(temps)
        if self._start is None or season is not self._season or rooms != self._rooms:
            self._restart(now, season, rooms, power_w)
            return False
        assert self._last is not None
        last_at, last_w = self._last
        gap_s = (now - last_at).total_seconds()
        if gap_s > MAX_GAP_S or gap_s < 0:
            self._restart(now, season, rooms, power_w)
            return False
        self._energy_kwh += (last_w + power_w) / 2 * gap_s / 3_600_000
        self._last = (now, power_w)
        if (now - self._start).total_seconds() < SETTLE_S:
            return False
        area = sum(areas[r] for r in temps)
        mean_c = sum(t * areas[r] for r, t in temps.items()) / area
        point = _Point(mean_c, self._energy_kwh, now)
        if not self._points:
            self._points = [point]
            return False
        sign = season.sign
        if sign * (mean_c - self._points[0].temperature_c) <= -STEP_K:
            self._points = [point]  # the temperature moves against the season: the window starts again
            return False
        if sign * (mean_c - self._points[-1].temperature_c) < STEP_K:
            return False
        self._points.append(point)
        while (
            len(self._points) > 2
            and sign * (point.temperature_c - self._points[1].temperature_c) >= MIN_WINDOW_K
        ):
            self._points.pop(0)
        return self._estimate(season, now)

    def _restart(self, now: datetime, season: Season, rooms: frozenset[str], power_w: float) -> None:
        self._reset_window()
        self._season, self._rooms, self._start = season, rooms, now
        self._last = (now, power_w)

    def _estimate(self, season: Season, now: datetime) -> bool:
        first, last = self._points[0], self._points[-1]
        delta_k = season.sign * (last.temperature_c - first.temperature_c)
        if delta_k < MIN_WINDOW_K or (last.at - first.at).total_seconds() < MIN_WINDOW_S:
            return False
        estimate = (last.energy_kwh - first.energy_kwh) / delta_k * STEP_K
        if not E01_MIN_KWH <= estimate <= E01_MAX_KWH:
            return False
        item = self.learned[season]
        if item.estimates < BOOTSTRAP_ESTIMATES:
            item.bootstrap.append(estimate)
            self._points = [last]  # the first windows must not overlap
            if len(item.bootstrap) >= BOOTSTRAP_ESTIMATES:
                item.e01_kwh = float(median(item.bootstrap))
                item.bootstrap = []
                item.estimates = BOOTSTRAP_ESTIMATES
            else:
                item.estimates += 1
        else:
            step = RATE * (estimate - item.e01_kwh)
            limit = MAX_CHANGE * item.e01_kwh
            item.e01_kwh = min(E01_MAX_KWH, max(E01_MIN_KWH, item.e01_kwh + max(-limit, min(limit, step))))
            item.estimates += 1
        item.updated = now
        return True
