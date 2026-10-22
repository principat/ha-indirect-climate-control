"""FR-GEN-01: installation configuration. Plant values have no defaults in the core."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace

from .model import NEUTRAL, Mode


class ConfigError(ValueError):
    """Raised for an inconsistent configuration."""


SETPOINT_MIN_C = 5.0
SETPOINT_MAX_C = 30.0


def valid_setpoint(raw: object) -> float | None:
    """Setpoint from a variable source, or None if not a plausible number."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return value if SETPOINT_MIN_C <= value <= SETPOINT_MAX_C else None


@dataclass(frozen=True)
class RoomConfig:
    id: str
    name: str
    setpoint_c: float
    power_class: str
    nominal_power_w: float
    area_m2: float = 1.0


@dataclass(frozen=True)
class Parameters:
    """Tunable parameters (functional spec, section 4). Generic start values only."""

    start_ratio: float = 0.8
    stop_ratio: float = 0.5
    tie_band_k: float = 1.0
    heat_offset_k: float = 1.0
    soc_smoothing_s: float = 900.0
    outlier_k: float = 2.0
    overheat_k: float = 3.0
    overheat_s: float = 3600.0
    hard_min_below_k: float = 2.0
    overload_max_c: float = 28.0
    comfort_max_c: float = 24.0
    soc_min_c: float = 15.0
    soc_max_c: float = 30.0
    efficiency_pct: float = 92.0
    discharge_limit_w: float = 3500.0
    night_start_h: int = 21
    night_end_h: int = 6
    night_setback_k: float = 1.0
    late_charge_surcharge: float = 0.001
    undercharge_cost: float = 0.003
    overcharge_cost: float = 0.003
    planner_horizon_h: int = 24
    plan_max_age_s: float = 1800.0
    neutral_mode: Mode = Mode.FAN
    cycle_s: float = 60.0

    @classmethod
    def from_mapping(cls, values: dict[str, object]) -> Parameters:
        """Build from stored options; unknown keys are ignored, missing keys keep the start value."""
        kwargs: dict[str, object] = {}
        for f in fields(cls):
            if f.name in values:
                raw = values[f.name]
                default = getattr(cls(), f.name)
                kwargs[f.name] = type(default)(raw)
        return cls(**kwargs)  # type: ignore[arg-type]

    def as_mapping(self) -> dict[str, object]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def validate(self) -> None:
        if not 0 < self.stop_ratio <= self.start_ratio:
            raise ConfigError("0 < stop ratio <= start ratio required")
        if not self.soc_min_c < self.comfort_max_c < self.overload_max_c <= self.soc_max_c:
            raise ConfigError("SOC scale min < comfort max < overload max <= SOC scale max required")
        if self.neutral_mode not in NEUTRAL:
            raise ConfigError("neutral mode must be fan or off")


@dataclass(frozen=True)
class InstallationConfig:
    p_min_w: float
    p_max_w: float
    capacity_kwh_per_k: float
    rooms: tuple[RoomConfig, ...]
    params: Parameters = field(default_factory=Parameters)

    def __post_init__(self) -> None:
        if not self.rooms:
            raise ConfigError("at least one room is required")
        ids = [r.id for r in self.rooms]
        if len(set(ids)) != len(ids):
            raise ConfigError("room ids must be unique")
        if not 0 < self.p_min_w <= self.p_max_w:
            raise ConfigError("0 < Pmin <= Pmax required")
        if self.capacity_kwh_per_k <= 0:
            raise ConfigError("capacity must be positive")
        self.params.validate()

    @property
    def class_order(self) -> tuple[str, ...]:
        """Power classes in the order they were first used by the configured rooms."""
        return tuple(dict.fromkeys(r.power_class for r in self.rooms))

    def with_setpoints(self, setpoints: Mapping[str, float]) -> InstallationConfig:
        """Copy with current setpoints from a variable source; rooms without a value keep theirs."""
        if not setpoints:
            return self
        rooms = tuple(replace(r, setpoint_c=setpoints[r.id]) if r.id in setpoints else r for r in self.rooms)
        return replace(self, rooms=rooms)

    def room(self, room_id: str) -> RoomConfig:
        return next(r for r in self.rooms if r.id == room_id)
