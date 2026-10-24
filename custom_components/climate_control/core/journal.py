"""FR-OBS-01: operating data of the plant, its outdoor power and its indoor units, recorded on change."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

POWER_STEP_W = 20.0  # the outdoor power is recorded when it moved at least this much since the last record


@dataclass(frozen=True)
class UnitRecord:
    """What is recorded of one indoor unit."""

    mode: str | None
    temperature_c: float | None  # device temperature as reported
    target_c: float | None  # setpoint the unit currently holds
    fan: str | None


class Journal:
    """Turns the state of every cycle into records. Only changes produce a record, so the volume stays small.

    The first cycle writes the starting state. A `plant` record marks every start and stop of the outdoor unit
    with the reasons known to the control (state of charge, planned and requested power, season). The outdoor
    power of the plant is recorded in a `power` record whenever it moved by `POWER_STEP_W` since the last one.
    """

    def __init__(self) -> None:
        self._running: bool | None = None
        self._units: dict[str, UnitRecord] = {}
        self._power_w: float | None = None

    def record(
        self,
        now: datetime,
        running: bool,
        units: Mapping[str, UnitRecord],
        context: Mapping[str, Any],
        power_w: float | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        stamp = now.isoformat()
        if running != self._running:
            rows.append({"time": stamp, "event": "plant", "running": running, **context})
            self._running = running
        if power_w is not None and (self._power_w is None or abs(power_w - self._power_w) >= POWER_STEP_W):
            rows.append({"time": stamp, "event": "power", "power_w": round(power_w, 1)})
            self._power_w = power_w
        for unit_id, unit in units.items():
            if self._units.get(unit_id) != unit:
                rows.append({"time": stamp, "event": "unit", "unit": unit_id, **asdict(unit)})
                self._units[unit_id] = unit
        return rows
