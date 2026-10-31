"""FR-PLNR-01: buffer model values the integration provides to the planner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import InstallationConfig, RoomConfig
from .model import OperatingMode, Season
from .soc import EDGE, position_pct

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


def planner_inputs(
    cfg: InstallationConfig,
    now: datetime,
    season: Season = Season.HEAT,
    operating: OperatingMode = OperatingMode.HEMS_OPTIMIZED,
    cooldown_left_s: float = 0.0,
) -> PlannerInputs:
    """Values for now plus hourly forecasts over the planner horizon (`now` in local time).

    The limits follow the setpoints (FR-BAND-01): the control range around the setpoint is the part of the
    buffer the planner may use freely, the absolute limits end the penalty zones. Cooling (FR-SEAS-02) swaps
    the sides, the places of the limits on the SOC scale stay the same (FR-SOC-01).

    The operating mode (FR-OPM-01) changes what the planner may use: the manufacturer control leaves it no
    buffer (capacity 0, FR-OPM-02), the buffer control only the range above the setpoint (FR-OPM-05). After
    the plant went to standby the charge cost carries a surcharge while the cooldown lasts (FR-OPM-04).
    """
    p = cfg.params

    # SOC positions of the area-weighted distances, towards the discharged side where they are negative.
    lower_band = weighted(cfg, lambda r: r.discharge_band(season))
    lower_limit = weighted(cfg, lambda r: r.discharge_limit(season))
    upper_band = weighted(cfg, lambda r: r.charge_band(season))
    upper_limit = weighted(cfg, lambda r: r.charge_limit(season))

    def pct(offset: float) -> float:
        return round(position_pct(offset, lower_band, lower_limit, upper_band, upper_limit), 2)

    def extra(t: datetime) -> float:
        return p.night_setback_k if is_night(t, p.night_start_h, p.night_end_h) else 0.0

    start = now.replace(minute=0, second=0, microsecond=0)
    hours = [start + timedelta(hours=i) for i in range(p.planner_horizon_h)]
    span = max(1, p.planner_horizon_h - 1)

    cooling_until = now + timedelta(seconds=cooldown_left_s)

    def surcharge(i: int) -> float:
        # Falls linearly to zero over the horizon: among equally priced windows the later one wins.
        value = p.late_charge_surcharge * (1 - i / span)
        # FR-OPM-04: windows that overlap the cooldown cost a little more, a tie breaker and no more
        slot = start + timedelta(hours=i)
        if cooldown_left_s > 0 and slot < cooling_until and slot + timedelta(hours=1) > now:
            value += p.cooldown_surcharge
        return round(value, 6)

    if operating is OperatingMode.HEMS_BUFFER:
        # FR-OPM-05: the scale runs from the setpoint lowered by the night setback (0 %) to the end of the
        # range above the setpoint (100 %). By day the lowest point in use is the setpoint itself, at night it
        # is the lowered setpoint (0 %): the planner may leave the night setback unused.
        scale = p.night_setback_k + upper_band
        day_pct = round(100.0 * p.night_setback_k / scale, 2) if scale > 0 else 0.0

        def floor_pct(t: datetime) -> float:
            return 0.0 if is_night(t, p.night_start_h, p.night_end_h) else day_pct

        lowest = tuple((t, floor_pct(t)) for t in hours)
        return PlannerInputs(
            capacity_kwh=round(cfg.capacity_kwh_per_k * scale, 3),
            min_charge_pct=floor_pct(now),
            undercharge_pct=floor_pct(now),
            max_charge_pct=100.0,
            overcharge_pct=100.0,
            undercharge_cost=p.undercharge_cost,
            overcharge_cost=p.overcharge_cost,
            efficiency_pct=p.efficiency_pct,
            max_discharge_kw=p.discharge_limit_w / 1000,
            max_charge_kw=cfg.p_max_w / 1000,
            charge_cost=surcharge(0),
            min_charge_forecast=lowest,
            undercharge_forecast=lowest,
            charge_cost_forecast=tuple((t, surcharge(i)) for i, t in enumerate(hours)),
        )

    return PlannerInputs(
        # the planner counts linearly: exact in the comfort zone (80 % of the scale), approximate at the edges
        capacity_kwh=0.0
        if operating.manufacturer
        else round(cfg.capacity_kwh_per_k * (lower_band + upper_band) / (1 - 2 * EDGE), 3),
        min_charge_pct=pct(-(lower_band + extra(now))),
        undercharge_pct=pct(-(lower_limit + extra(now))),
        max_charge_pct=pct(upper_band),
        overcharge_pct=pct(upper_limit),
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
