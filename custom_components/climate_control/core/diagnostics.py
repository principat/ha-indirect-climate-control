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


def room_diagnostics(
    cfg: InstallationConfig, temps: Mapping[str, float], season: Season = Season.HEAT
) -> dict[str, RoomDiagnostics]:
    """Per room, from the temperatures the control used. The buffer capacity is split by area."""
    area = sum(r.area_m2 for r in cfg.rooms)
    result: dict[str, RoomDiagnostics] = {}
    for r in cfg.rooms:
        t = temps.get(r.id)
        if t is None:
            result[r.id] = RoomDiagnostics(None, None, None)
            continue
        capacity = cfg.capacity_kwh_per_k * r.area_m2 / area
        deviation = season.sign * (r.setpoint_c - t)
        result[r.id] = RoomDiagnostics(
            deviation_k=round(deviation, 2),
            heat_demand_kwh=round(capacity * deviation, 3),
            storage_kwh=round(max(0.0, capacity * (r.charge_limit(season) + deviation)), 3),
        )
    return result
