"""FR-OBS-02: diagnostic values per room."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .config import InstallationConfig
from .model import Season


@dataclass(frozen=True)
class RoomDiagnostics:
    deviation_k: float | None  # setpoint minus device temperature (cooling: the other way round)
    heat_demand_kwh: float | None  # electrical energy up to the setpoint, negative = stored above it
    storage_kwh: float | None  # electrical energy the room can still take up to its overload limit
    step_power_w: float | None = None  # learned power per power step of the unit (FR-LOAD-02)
    offset: float | None = None  # planned offset: power steps times step size, 0 while the unit is not served


def room_diagnostics(
    cfg: InstallationConfig,
    temps: Mapping[str, float],
    season: Season = Season.HEAT,
    step_power: Mapping[str, float] | None = None,
    steps: Mapping[str, int] | None = None,
) -> dict[str, RoomDiagnostics]:
    """Per room, from the temperatures the control used. The buffer capacity is split by area."""
    area = sum(r.area_m2 for r in cfg.rooms)
    result: dict[str, RoomDiagnostics] = {}
    for r in cfg.rooms:
        t = temps.get(r.id)
        offset = round((steps or {}).get(r.id, 0) * r.step, 3)
        if t is None:
            result[r.id] = RoomDiagnostics(None, None, None, (step_power or {}).get(r.id), offset)
            continue
        capacity = cfg.capacity_kwh_per_k * r.area_m2 / area
        deviation = season.sign * (r.setpoint_c - t)
        result[r.id] = RoomDiagnostics(
            deviation_k=round(deviation, 2),
            heat_demand_kwh=round(capacity * deviation, 3),
            storage_kwh=round(max(0.0, capacity * (r.charge_limit(season) + deviation)), 3),
            step_power_w=(step_power or {}).get(r.id),
            offset=offset,
        )
    return result
