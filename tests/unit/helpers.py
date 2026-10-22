"""Shared builders for unit tests (synthetic installation, not the reference case)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.climate_control.core.config import InstallationConfig, Parameters, RoomConfig
from custom_components.climate_control.core.model import Mode, RoomState
from custom_components.climate_control.core.plan import Plan, PlanPoint

T0 = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def room(
    rid: str, setpoint: float = 21.0, cls: str = "big", power: float = 700.0, area: float = 10.0
) -> RoomConfig:
    return RoomConfig(
        id=rid, name=rid.upper(), setpoint_c=setpoint, power_class=cls, nominal_power_w=power, area_m2=area
    )


def installation(*rooms: RoomConfig, **params: object) -> InstallationConfig:
    return InstallationConfig(
        p_min_w=1300,
        p_max_w=3300,
        capacity_kwh_per_k=3.5,
        rooms=rooms or (room("a"), room("b"), room("c")),
        params=Parameters(**params),  # type: ignore[arg-type]
    )


def plan(power_w: float, now: datetime = T0, hours: int = 6) -> Plan:
    start = now.replace(minute=0, second=0, microsecond=0)
    return Plan(tuple(PlanPoint(start + timedelta(hours=i), power_w) for i in range(hours)), now)


def states(temps: dict[str, float], mode: Mode = Mode.FAN, **windows: bool) -> dict[str, RoomState]:
    return {rid: RoomState(mode, t, windows.get(rid, False)) for rid, t in temps.items()}
