"""FR-PLNR-01: buffer model values the integration provides to the planner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import InstallationConfig
from .soc import temperature_to_soc

Series = tuple[tuple[datetime, float], ...]


@dataclass(frozen=True)
class PlannerInputs:
    capacity_kwh: float
    min_charge_pct: float
    undercharge_pct: float
    max_charge_pct: float
    overcharge_pct: float
    undercharge_cost: float
    overcharge_cost: float
    efficiency_pct: float
    max_discharge_kw: float
    max_charge_kw: float
    charge_cost: float
    min_charge_forecast: Series
    undercharge_forecast: Series
    charge_cost_forecast: Series


def weighted_setpoint(cfg: InstallationConfig) -> float:
    """Area-weighted mean of the room setpoints."""
    area = sum(r.area_m2 for r in cfg.rooms)
    return sum(r.setpoint_c * r.area_m2 for r in cfg.rooms) / area


def is_night(t: datetime, start_h: int, end_h: int) -> bool:
    h = t.hour
    return h >= start_h or h < end_h if start_h > end_h else start_h <= h < end_h


def planner_inputs(cfg: InstallationConfig, now: datetime) -> PlannerInputs:
    """Values for now plus hourly forecasts over the planner horizon (`now` in local time)."""
    p = cfg.params
    lower_c = weighted_setpoint(cfg)
    hard_c = lower_c - p.hard_min_below_k

    def lowered(t: datetime, c: float) -> float:
        return c - p.night_setback_k if is_night(t, p.night_start_h, p.night_end_h) else c

    start = now.replace(minute=0, second=0, microsecond=0)
    hours = [start + timedelta(hours=i) for i in range(p.planner_horizon_h)]
    span = max(1, p.planner_horizon_h - 1)

    def surcharge(i: int) -> float:
        # Falls linearly to zero over the horizon: among equally priced windows the later one wins.
        return round(p.late_charge_surcharge * (1 - i / span), 6)

    def soc(c: float) -> float:
        return round(temperature_to_soc(c, p), 2)

    return PlannerInputs(
        capacity_kwh=round(cfg.capacity_kwh_per_k * (p.soc_max_c - p.soc_min_c), 3),
        min_charge_pct=soc(lowered(now, lower_c)),
        undercharge_pct=soc(lowered(now, hard_c)),
        max_charge_pct=soc(p.comfort_max_c),
        overcharge_pct=soc(p.overload_max_c),
        undercharge_cost=p.undercharge_cost,
        overcharge_cost=p.overcharge_cost,
        efficiency_pct=p.efficiency_pct,
        max_discharge_kw=p.discharge_limit_w / 1000,
        max_charge_kw=cfg.p_max_w / 1000,
        charge_cost=surcharge(0),
        min_charge_forecast=tuple((t, soc(lowered(t, lower_c))) for t in hours),
        undercharge_forecast=tuple((t, soc(lowered(t, hard_c))) for t in hours),
        charge_cost_forecast=tuple((t, surcharge(i)) for i, t in enumerate(hours)),
    )
