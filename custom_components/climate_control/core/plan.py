"""FR-PLAN-01 / FR-SAFE-04: the planned power over time and its validity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class PlanPoint:
    start: datetime
    power_w: float


@dataclass(frozen=True)
class Plan:
    points: tuple[PlanPoint, ...]
    received: datetime
    until: datetime | None = None  # explicit end, used for combined plans

    def power_at(self, t: datetime) -> float | None:
        """Planned power of the interval containing t (None if t is outside the plan)."""
        if not self.points or t < self.points[0].start or t >= self.valid_until():
            return None
        current = self.points[0]
        for point in self.points:
            if point.start > t:
                break
            current = point
        return current.power_w

    def horizon(self, now: datetime, hours: float) -> tuple[PlanPoint, ...]:
        """The current interval and all intervals starting within the next `hours`."""
        end = now + timedelta(hours=hours)
        current = [p for p in self.points if p.start <= now][-1:]
        return tuple(current + [p for p in self.points if now < p.start < end])

    def valid_until(self) -> datetime:
        """End of the last interval. Its length is taken from the interval before it."""
        if self.until is not None:
            return self.until
        if not self.points:
            return self.received
        if len(self.points) == 1:
            return datetime.max.replace(tzinfo=UTC)
        step = self.points[-1].start - self.points[-2].start
        return self.points[-1].start + step

    def is_stale(self, now: datetime, max_age_s: float) -> bool:
        if (now - self.received).total_seconds() > max_age_s:
            return True
        return self.power_at(now) is None


def _parse_time(value: object, tz_default: datetime) -> datetime:
    t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if t.tzinfo is None:
        t = t.replace(tzinfo=tz_default.tzinfo)
    return t


def plan_from_forecast(state: object, unit: str | None, forecast: object, received: datetime) -> Plan | None:
    """Build a plan from a planner output: current value plus a forecast attribute.

    Accepted forecast layouts: a list of mappings with a time key (`time` or `start_time`) and
    a value key (`value`), or a mapping from time to value. Unit kW is converted to W.
    Without a forecast the current value alone is used as a plan starting at `received`.
    Returns None if nothing numeric is available.
    """
    factor = 1000.0 if (unit or "").strip().lower() == "kw" else 1.0
    raw: list[tuple[object, object]] = []
    if isinstance(forecast, Mapping):
        raw = list(forecast.items())
    elif isinstance(forecast, list):
        for item in forecast:
            if isinstance(item, Mapping):
                raw.append((item.get("time", item.get("start_time")), item.get("value")))
    points: list[PlanPoint] = []
    for t, v in raw:
        try:
            points.append(PlanPoint(_parse_time(t, received), float(v) * factor))  # type: ignore[arg-type]
        except TypeError, ValueError:
            continue
    if not points:
        try:
            points = [PlanPoint(received, float(state) * factor)]  # type: ignore[arg-type]
        except TypeError, ValueError:
            return None
    points.sort(key=lambda p: p.start)
    return Plan(tuple(points), received)


def combine(plans: Sequence[Plan | None]) -> Plan | None:
    """Sum of several planner outputs, e.g. the flows of two connections.

    Missing output (None) makes the whole plan missing (planner failure). The combined plan
    is as old as its oldest part and ends with the shortest part.
    """
    if not plans or any(p is None for p in plans):
        return None
    parts = [p for p in plans if p is not None]
    if len(parts) == 1:
        return parts[0]
    until = min(p.valid_until() for p in parts)
    starts = sorted({pt.start for p in parts for pt in p.points if pt.start < until})
    points = tuple(PlanPoint(t, sum(p.power_at(t) or 0.0 for p in parts)) for t in starts)
    return Plan(points, min(p.received for p in parts), until)
