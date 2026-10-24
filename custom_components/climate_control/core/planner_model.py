"""FR-PLNR-01: buffer model values the integration provides to the planner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import InstallationConfig, RoomConfig
from .model import Season
from .soc import soc_position

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


def weighted(cfg: InstallationConfig, value: Callable[[RoomConfig], float]) -> float:
    """Area-weighted mean of a room value over all rooms."""
    area = sum(r.area_m2 for r in cfg.rooms)
    return sum(value(r) * r.area_m2 for r in cfg.rooms) / area


def is_night(t: datetime, start_h: int, end_h: int) -> bool:
    h = t.hour
    return h >= start_h or h < end_h if start_h > end_h else start_h <= h < end_h


def planner_inputs(cfg: InstallationConfig, now: datetime, season: Season = Season.HEAT) -> PlannerInputs:
    """Values for now plus hourly forecasts over the planner horizon (`now` in local time).

    The limits follow the setpoints (FR-BAND-01): the control range around the setpoint is the part of the
    buffer the planner may use freely, the absolute limits end the penalty zones. Cooling (FR-SEAS-02) swaps
    the sides, the SOC scale stays the same.
    """
    p = cfg.params

    def pct(offset: float) -> float:
        return round(soc_position(offset, p), 2)

    def extra(t: datetime) -> float:
        return p.night_setback_k if is_night(t, p.night_start_h, p.night_end_h) else 0.0

    # SOC positions of the area-weighted distances, towards the discharged side where they are negative.
    lower_band = weighted(cfg, lambda r: r.discharge_band(season))
    lower_limit = weighted(cfg, lambda r: r.discharge_limit(season))
    start = now.replace(minute=0, second=0, microsecond=0)
    hours = [start + timedelta(hours=i) for i in range(p.planner_horizon_h)]
    span = max(1, p.planner_horizon_h - 1)

    def surcharge(i: int) -> float:
        # Falls linearly to zero over the horizon: among equally priced windows the later one wins.
        return round(p.late_charge_surcharge * (1 - i / span), 6)

    return PlannerInputs(
        capacity_kwh=round(cfg.capacity_kwh_per_k * p.scale_k, 3),
        min_charge_pct=pct(-(lower_band + extra(now))),
        undercharge_pct=pct(-(lower_limit + extra(now))),
        max_charge_pct=pct(weighted(cfg, lambda r: r.charge_band(season))),
        overcharge_pct=pct(weighted(cfg, lambda r: r.charge_limit(season))),
        undercharge_cost=p.undercharge_cost,
        overcharge_cost=p.overcharge_cost,
        efficiency_pct=p.efficiency_pct,
        max_discharge_kw=p.discharge_limit_w / 1000,
        max_charge_kw=cfg.p_max_w / 1000,
        charge_cost=surcharge(0),
        min_charge_forecast=tuple((t, pct(-(lower_band + extra(t)))) for t in hours),
        undercharge_forecast=tuple((t, pct(-(lower_limit + extra(t)))) for t in hours),
        charge_cost_forecast=tuple((t, surcharge(i)) for i, t in enumerate(hours)),
    )
