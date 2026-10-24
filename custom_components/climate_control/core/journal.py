"""FR-OBS-01: operating data of the plant and its indoor units, recorded when something changes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


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
    with the reasons known to the control (state of charge, planned and requested power, season).
    """

    def __init__(self) -> None:
        self._running: bool | None = None
        self._units: dict[str, UnitRecord] = {}

    def record(
        self,
        now: datetime,
        running: bool,
        units: Mapping[str, UnitRecord],
        context: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        stamp = now.isoformat()
        if running != self._running:
            rows.append({"time": stamp, "event": "plant", "running": running, **context})
            self._running = running
        for unit_id, unit in units.items():
            if self._units.get(unit_id) != unit:
                rows.append({"time": stamp, "event": "unit", "unit": unit_id, **asdict(unit)})
                self._units[unit_id] = unit
        return rows
