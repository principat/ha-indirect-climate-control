"""FR-GEN-01: installation configuration. Plant values have no defaults in the core."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace

from .model import NEUTRAL, Mode, Season


class ConfigError(ValueError):
    """Raised for an inconsistent configuration."""


SETPOINT_MIN_C = 5.0
SETPOINT_MAX_C = 30.0


def valid_setpoint(raw: object, low: float = SETPOINT_MIN_C, high: float = SETPOINT_MAX_C) -> float | None:
    """Setpoint from a variable source, or None if not a plausible number (bounds in the plant's unit)."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
    return value if low <= value <= high else None


@dataclass(frozen=True)
class RoomConfig:
    id: str
    name: str
    setpoint_c: float  # in the plant's temperature unit (FR-UNIT-01); the control only uses differences
    nominal_power_w: float
    area_m2: float = 1.0
    # FR-BAND-01: distances to the current setpoint, in the plant's unit
    band_down: float = 2.0  # control range below the setpoint: the planner may use the buffer freely
    band_up: float = 2.0
    limit_down: float = 3.0  # absolute limit below the setpoint: protection heats even without plan
    limit_up: float = 3.0  # absolute limit above the setpoint: no further heating (overload limit)
    step: float = 0.5  # smallest change of the device temperature the unit reports (informational)

    # The buffer is charged towards "up" when heating and towards "down" when cooling (FR-SEAS-02).
    def discharge_band(self, season: Season) -> float:
        return self.band_down if season is Season.HEAT else self.band_up

    def charge_band(self, season: Season) -> float:
        return self.band_up if season is Season.HEAT else self.band_down

    def discharge_limit(self, season: Season) -> float:
        return self.limit_down if season is Season.HEAT else self.limit_up

    def charge_limit(self, season: Season) -> float:
        return self.limit_up if season is Season.HEAT else self.limit_down

    @property
    def power_class(self) -> float:
        """Power class = group of indoor units with the same nominal power (glossary)."""
        return self.nominal_power_w


@dataclass(frozen=True)
class Parameters:
    """Tunable parameters (functional spec, section 4). Generic start values only."""

    start_ratio: float = 0.8
    stop_ratio: float = 0.5
    tie_band_k: float = 1.0
    soc_smoothing_s: float = 900.0
    outlier_k: float = 2.0
    overheat_k: float = 3.0
    overheat_s: float = 3600.0
    soc_below_k: float = 6.0  # SOC scale: 0 % at this distance below the setpoint (FR-SOC-01)
    soc_above_k: float = 9.0  # 100 % at this distance above it
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
    min_run_s: float = 600.0
    load_deadband_ratio: float = 0.1  # FR-LOAD-01: share of Pmin around the request where nothing is adjusted
    load_settle_max_s: float = (
        600.0  # FR-LOAD-02: longest wait for the outdoor power to settle after an adjustment
    )
    cutoff_k: float = 3.5  # FR-LOAD-05: distance above the setpoint where the unit cuts off (cooling: below)
    join_margin_k: float = 1.0  # FR-LOAD-06: the next room starts this far below the cut-off distance
    activation_rise_k: float = 1.0  # FR-LOAD-06: rise of the device temperature that makes a room active
    startup_s: float = 600.0  # FR-LOAD-07: the measured power does not count after a start or a change
    settle_s: float = 600.0  # FR-SRC-02: settling time of the readings after the units went neutral
    fallback_delay_s: float = 600.0
    fallback_step_s: float = 120.0

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
        if self.soc_below_k <= 0 or self.soc_above_k <= 0:
            raise ConfigError("SOC scale below and above the setpoint must be positive")
        if self.neutral_mode not in NEUTRAL:
            raise ConfigError("neutral mode must be fan or off")
        if self.fallback_delay_s < 0 or self.fallback_step_s <= 0:
            raise ConfigError("fallback delay >= 0 and fallback step > 0 required")
        if self.min_run_s < 0:
            raise ConfigError("minimum run time must not be negative")
        if not 0 <= self.load_deadband_ratio < 1 or self.load_settle_max_s <= 0:
            raise ConfigError("load dead band in [0, 1) and a positive settling time required")
        if self.cutoff_k <= 0 or not 0 < self.join_margin_k < self.cutoff_k:
            raise ConfigError("cut-off distance > 0 and 0 < join margin < cut-off distance required")
        if self.activation_rise_k <= 0:
            raise ConfigError("the activation rise must be positive")
        if self.startup_s < 0 or self.settle_s < 0:
            raise ConfigError("start-up and settling time must not be negative")

    @property
    def scale_k(self) -> float:
        """Width of the SOC scale in degrees of the plant's unit."""
        return self.soc_below_k + self.soc_above_k


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
        for r in self.rooms:
            if r.step <= 0:
                raise ConfigError(f"{r.id}: reading step must be positive")
            if not 0 < r.band_down <= r.limit_down or not 0 < r.band_up <= r.limit_up:
                raise ConfigError(f"{r.id}: 0 < control range <= absolute limit required in both directions")

    @property
    def class_order(self) -> tuple[float, ...]:
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
