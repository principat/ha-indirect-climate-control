"""One control cycle: plan, safety, fallback, distribution and mode changes combined."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from .config import InstallationConfig, RoomConfig
from .distribution import rank, select
from .model import WITH_SETPOINT, Command, Mode, RoomState
from .modes import next_modes
from .plan import Plan
from .soc import OutlierFilter, SocSmoother, temperature_to_soc, worst_room
from .threshold import ThresholdConfig, decide


@dataclass(frozen=True)
class CycleResult:
    commands: dict[str, Command]
    soc_pct: float | None
    worst_room: str | None
    planned_w: float | None
    requested_w: float
    running: bool
    fallback: bool
    served: tuple[str, ...]
    plan_missing_s: float = 0.0  # how long the plan has been missing or stale (0 = plan valid)
    temperatures: dict[str, float] = field(default_factory=dict)  # filtered device temperatures used


class Controller:
    """Stateful across cycles: run state, overheat timers, SOC filter and smoothing."""

    def __init__(self, cfg: InstallationConfig) -> None:
        self.cfg = cfg
        p = cfg.params
        self._threshold = ThresholdConfig(cfg.p_min_w, p.start_ratio, p.stop_ratio)
        self._filter = OutlierFilter(p.outlier_k)
        self._smoother = SocSmoother(p.soc_smoothing_s)
        self._overheat_since: dict[str, datetime] = {}
        self._plan_missing_since: datetime | None = None
        self.running = False

    def step(
        self,
        now: datetime,
        plan: Plan | None,
        rooms: Mapping[str, RoomState],
        setpoints: Mapping[str, float] | None = None,
    ) -> CycleResult:
        """`setpoints` overrides the configured setpoint of a room for this cycle (variable source)."""
        cfg = self.cfg.with_setpoints(setpoints or {})
        p = cfg.params
        temps: dict[str, float] = {}
        for room in cfg.rooms:
            state = rooms.get(room.id)
            if state is None or state.temperature_c is None:
                continue
            # FR-SRC-01: the indoor unit's own reading, whole degrees.
            temps[room.id] = self._filter.accept(room.id, float(round(state.temperature_c)))
        active = [
            r
            for r in cfg.rooms
            if r.id in temps and not rooms[r.id].window_open and rooms[r.id].mode is not None
        ]

        soc: float | None = None
        worst = worst_room((r, temps[r.id]) for r in active)
        if worst is not None:
            soc = round(self._smoother.add(now, temperature_to_soc(worst[1], p)), 2)

        for r in active:
            if temps[r.id] >= r.setpoint_c + p.overheat_k:
                self._overheat_since.setdefault(r.id, now)
            else:
                self._overheat_since.pop(r.id, None)

        targets: dict[str, Command] = {}
        planned_w = plan.power_at(now) if plan is not None else None
        plan_missing = plan is None or plan.is_stale(now, p.plan_max_age_s)
        if plan_missing:
            if self._plan_missing_since is None:
                self._plan_missing_since = now
            missing_s = (now - self._plan_missing_since).total_seconds()
        else:
            self._plan_missing_since = None
            missing_s = 0.0
        # FR-SAFE-04: the building is slow, so a missing plan is waited out before the fallback starts.
        fallback = plan_missing and missing_s >= p.fallback_delay_s
        requested_w = 0.0
        served: tuple[RoomConfig, ...] = ()
        if plan_missing and not fallback:
            # Waiting: units stay as they are (the protection rules below still apply).
            targets = {r.id: Command(rooms[r.id].mode) for r in active}  # type: ignore[arg-type]
        elif fallback:
            # Fallback: units are switched to heating with their standard setpoints step by step,
            # largest deviation first, one power class group per step. Running units stay on.
            self.running = False
            tiers = rank([(r, r.setpoint_c - temps[r.id]) for r in active], p.tie_band_k, cfg.class_order)
            groups = [group for tier in tiers for group in tier]
            steps = 1 + int((missing_s - p.fallback_delay_s) // p.fallback_step_s)
            activated = {r.id for group in groups[:steps] for r in group}
            targets = {
                r.id: Command(Mode.HEAT, r.setpoint_c) if r.id in activated else Command(rooms[r.id].mode)  # type: ignore[arg-type]
                for r in active
            }
        else:
            # FR-PLAN-02/03/04: the plan alone decides whether the outdoor unit runs.
            decision = decide(planned_w or 0.0, self.running, self._threshold)
            self.running = decision.run
            requested_w = decision.power_w
            if decision.run:
                eligible = [r for r in active if temps[r.id] < r.overload_max_c]
                tiers = rank(
                    [(r, r.setpoint_c - temps[r.id]) for r in eligible], p.tie_band_k, cfg.class_order
                )
                served = select(tiers, requested_w)
            for r in active:
                if r in served:
                    target = min(temps[r.id] + p.heat_offset_k, r.overload_max_c)
                    targets[r.id] = Command(Mode.HEAT, target)
                else:
                    targets[r.id] = Command(p.neutral_mode)

        # FR-SAFE-02: below the hard minimum a room heats regardless of the plan (also while waiting).
        for r in active:
            if temps[r.id] < r.setpoint_c - p.hard_min_below_k:
                current = targets[r.id]
                target = max(r.setpoint_c, current.target_c or r.setpoint_c)
                targets[r.id] = Command(Mode.HEAT, target)
        # FR-SAFE-03: overheated for long enough -> cool, only while no unit is to heat.
        if not any(c.mode == Mode.HEAT for c in targets.values()):
            for r in active:
                since = self._overheat_since.get(r.id)
                if since is not None and (now - since).total_seconds() >= p.overheat_s:
                    targets[r.id] = Command(Mode.COOL, r.setpoint_c)

        # FR-SAFE-01: a room with an open window is taken out of the control.
        for r in cfg.rooms:
            state = rooms.get(r.id)
            if state is not None and state.window_open and state.mode is not None:
                targets[r.id] = Command(p.neutral_mode)

        current_modes = {rid: s.mode for rid, s in rooms.items() if s.mode is not None and rid in targets}
        modes = next_modes(current_modes, {rid: c.mode for rid, c in targets.items()}, p.neutral_mode)
        commands = {
            rid: Command(m, targets[rid].target_c if m in WITH_SETPOINT and m == targets[rid].mode else None)
            for rid, m in modes.items()
        }
        return CycleResult(
            commands=commands,
            soc_pct=soc,
            worst_room=worst[0].id if worst else None,
            planned_w=planned_w,
            requested_w=requested_w,
            running=self.running,
            fallback=fallback,
            served=tuple(r.id for r in served),
            plan_missing_s=missing_s,
            temperatures=temps,
        )
