"""FR-PLAN-02 / FR-PLAN-03: start threshold with hysteresis, no pulse operation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdConfig:
    p_min_w: float
    start_ratio: float = 0.8
    stop_ratio: float = 0.5


@dataclass(frozen=True)
class RunDecision:
    run: bool
    power_w: float


def decide(planned_w: float, running: bool, cfg: ThresholdConfig) -> RunDecision:
    """Return whether the outdoor unit should run and the power to request.

    Off -> start only at/above start_ratio * p_min. Running -> stay until below
    stop_ratio * p_min. While running, request at least p_min.
    """
    limit = cfg.stop_ratio if running else cfg.start_ratio
    if planned_w >= limit * cfg.p_min_w:
        return RunDecision(True, max(planned_w, cfg.p_min_w))
    return RunDecision(False, 0.0)
