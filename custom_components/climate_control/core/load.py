"""FR-LOAD-01 / FR-LOAD-02: load control on temperature events, power per step learned per indoor unit.

The control variable is the number of power steps `n` of each served unit: its setpoint lies `n x step`
above its start threshold, which is the start distance below the device temperature. Two steps on two units
(the minimum stage) bring the outdoor unit to Pmin, every further step adds the learned power per step.
The controller compares it with the requested power and changes the steps of one unit at a time: the room
with the largest deviation first, the rooms within the tie band of it in turn (fewest steps first, then the
power class), so the rooms are brought to one level and then rise together. Lowering takes the fullest room
first. A dead band around the request, a floor of two steps on two units and the absolute limits of the
rooms bound it. It runs on every cycle and every temperature event, there is no time window.

Learning: after an adjustment the outdoor unit's power is watched until it has settled (cycle means within the
dead band over three cycles, with a maximum time that adapts to the plant). The change divided by the changed
steps updates the power per step of the units involved. Disturbed observations are dropped.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, median
from typing import Any

from .config import InstallationConfig, RoomConfig
from .distribution import Tier
from .model import Season

MIN_STAGE = 2  # power steps, spread over two units if possible
SETTLE_CYCLES = 3
BOOTSTRAP_ESTIMATES = 3  # the first estimates of a unit replace the start value by their median
RATE = 0.2
MAX_CHANGE = 0.25
FACTOR_MIN, FACTOR_MAX = 0.1, 10.0  # plausible ratio between the observed and the expected change
SETTLE_FACTOR = 3.0  # the maximum wait is this many times the typical settling time
MAX_ITERATIONS = 200


def start_power_w(cfg: InstallationConfig) -> float:
    """FR-LOAD-02: (Pmax - Pmin) spread over twice the number of units."""
    return (cfg.p_max_w - cfg.p_min_w) / (2 * len(cfg.rooms))


def expected_load_w(steps: Mapping[str, int], power: Mapping[str, float], p_min_w: float) -> float:
    """Outdoor power for the steps: Pmin at the minimum stage (two steps), each further step adds power.

    A further step counts with the mean power per step of the served units weighted by their steps.
    Without a step there is no load.
    """
    total = sum(steps.values())
    if total <= 0:
        return 0.0
    if total <= MIN_STAGE:
        return p_min_w
    mean_w = sum(power[rid] * n for rid, n in steps.items()) / total
    return p_min_w + mean_w * (total - MIN_STAGE)


@dataclass
class StepPower:
    """Learned power per power step of one indoor unit."""

    learned_w: float | None = None
    estimates: int = 0
    bootstrap: list[float] = field(default_factory=list)
    updated: datetime | None = None
    last_estimate_w: float | None = None


class LoadModel:
    """The learned values, kept across restarts. `revision` counts changes (the adapter stores on change)."""

    def __init__(self, stored: Mapping[str, Any] | None = None) -> None:
        self.units: dict[str, StepPower] = {}
        self.revision = 0
        if stored:
            self.restore(stored)

    def power(self, room_id: str, start_w: float) -> float:
        item = self.units.get(room_id)
        return item.learned_w if item is not None and item.learned_w is not None else start_w

    def reset(self) -> None:
        self.units.clear()
        self.revision += 1

    def update_unit(self, room_id: str, estimate_w: float, now: datetime) -> None:
        item = self.units.setdefault(room_id, StepPower())
        item.last_estimate_w = estimate_w
        if item.learned_w is None:
            item.bootstrap.append(estimate_w)
            item.estimates += 1
            if len(item.bootstrap) >= BOOTSTRAP_ESTIMATES:
                item.learned_w = float(median(item.bootstrap))
                item.bootstrap = []
        else:
            limit = MAX_CHANGE * item.learned_w
            step = RATE * (estimate_w - item.learned_w)
            item.learned_w += max(-limit, min(limit, step))
            item.estimates += 1
        item.updated = now
        self.revision += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            rid: {
                "learned_w": item.learned_w,
                "estimates": item.estimates,
                "bootstrap": list(item.bootstrap),
                "updated": item.updated.isoformat() if item.updated else None,
                "last_estimate_w": item.last_estimate_w,
            }
            for rid, item in self.units.items()
        }

    def restore(self, stored: Mapping[str, Any]) -> None:
        for rid, raw in stored.items():
            if not isinstance(raw, Mapping):
                continue
            try:
                learned = raw.get("learned_w")
                updated = raw.get("updated")
                last = raw.get("last_estimate_w")
                self.units[str(rid)] = StepPower(
                    learned_w=None if learned is None else float(learned),
                    estimates=int(raw.get("estimates", 0)),
                    bootstrap=[float(v) for v in raw.get("bootstrap", [])][:BOOTSTRAP_ESTIMATES],
                    updated=datetime.fromisoformat(updated) if updated else None,
                    last_estimate_w=None if last is None else float(last),
                )
            except TypeError, ValueError:
                continue


@dataclass
class _Observation:
    started: datetime
    before_w: float
    changed: dict[str, int]  # change of steps per unit that this observation attributes the power change to
    expected_delta_w: float  # change of the outdoor power the model expected for it
    means: list[float] = field(default_factory=list)


class LoadControl:
    """Stateful across cycles. `feed` the cycle's mean outdoor power, then `update` while the plant runs."""

    def __init__(self, model: LoadModel | None = None) -> None:
        self.model = model if model is not None else LoadModel()
        self.steps: dict[str, int] = {}
        self.expected_w = 0.0
        self._recent: deque[float] = deque(maxlen=SETTLE_CYCLES)
        self._observation: _Observation | None = None
        self._settle_s: deque[float] = deque(maxlen=10)

    # -- state ---------------------------------------------------------------------------------

    def reset(self) -> None:
        """The plant stopped, the season changed or the plan is gone: the next run starts afresh."""
        self.steps = {}
        self.expected_w = 0.0
        self._observation = None

    def discard_observation(self) -> None:
        self._observation = None

    def _power(self, cfg: InstallationConfig, room_id: str) -> float:
        return self.model.power(room_id, start_power_w(cfg))

    # -- measurement and learning ------------------------------------------------------------

    def feed(self, now: datetime, mean_w: float | None, cfg: InstallationConfig) -> None:
        """One cycle's mean outdoor power. Advances an observation that waits for the power to settle."""
        if mean_w is None:
            self._recent.clear()
            self._observation = None
            return
        self._recent.append(mean_w)
        obs = self._observation
        if obs is None:
            return
        obs.means.append(mean_w)
        dead = cfg.params.load_deadband_ratio * cfg.p_min_w
        waited = (now - obs.started).total_seconds()
        responded = any(abs(m - obs.before_w) > dead for m in obs.means)  # the plant has reacted at all
        if responded and len(obs.means) >= SETTLE_CYCLES:
            last = obs.means[-SETTLE_CYCLES:]
            if max(last) - min(last) <= dead:
                self._settle_s.append(waited)
                self._finish(obs, mean(last), now, cfg, dead)
                self._observation = None
                return
        if waited > self._max_wait_s(cfg):
            self._observation = None  # never settled: nothing learned, the earlier values stay

    def _max_wait_s(self, cfg: InstallationConfig) -> float:
        cap = cfg.params.load_settle_max_s
        if len(self._settle_s) < 3:
            return cap
        return min(cap, max(SETTLE_CYCLES * cfg.params.cycle_s, SETTLE_FACTOR * mean(self._settle_s)))

    def _finish(
        self, obs: _Observation, after_w: float, now: datetime, cfg: InstallationConfig, dead: float
    ) -> None:
        delta_w = after_w - obs.before_w
        total = obs.expected_delta_w
        if abs(total) < dead / 2 or abs(delta_w) < dead / 2:
            return
        factor = delta_w / total
        if not FACTOR_MIN <= factor <= FACTOR_MAX:
            return
        for rid in obs.changed:
            self.model.update_unit(rid, self._power(cfg, rid) * factor, now)

    # -- decision ----------------------------------------------------------------------------

    def update(
        self,
        now: datetime,
        cfg: InstallationConfig,
        season: Season,
        requested_w: float,
        tiers: Sequence[Tier],
        disturbed: bool = False,
    ) -> dict[str, int]:
        """Steps per served unit for the requested power. `tiers` are the eligible units, most urgent first.

        `disturbed` tells that something else changed the load since the last cycle (a room under protection,
        a window, a change of the season): a running observation is then not trustworthy.
        """
        dead = cfg.params.load_deadband_ratio * cfg.p_min_w
        ranked = _flat(tiers)
        ids = {r.id for r in ranked}
        lost = [rid for rid in self.steps if rid not in ids]
        if disturbed or lost:
            self._observation = None
        before = {r.id: self.steps.get(r.id, 0) for r in ranked}
        limit = {r.id: max(1, int(r.charge_limit(season) / r.step + 1e-9)) for r in ranked}
        power = {r.id: self._power(cfg, r.id) for r in ranked}
        after = self._adjust(before, limit, power, tiers, requested_w, dead, cfg.p_min_w)
        changed = {rid: after[rid] - before[rid] for rid in after if after[rid] != before[rid]}
        if changed:
            # a run that starts from standby only reaches the minimum stage (Pmin): nothing to learn from it
            expected_delta = expected_load_w(after, power, cfg.p_min_w) - expected_load_w(
                before, power, cfg.p_min_w
            )
            self._begin(now, changed, expected_delta if sum(before.values()) > 0 else 0.0)
        self.steps = {rid: n for rid, n in after.items() if n > 0}
        self.expected_w = expected_load_w(after, power, cfg.p_min_w)
        return dict(self.steps)

    def _begin(self, now: datetime, changed: dict[str, int], expected_delta_w: float) -> None:
        # A new adjustment while another observation is pending disturbs it: both are dropped.
        pending = self._observation is not None
        self._observation = None
        if pending or len(self._recent) < SETTLE_CYCLES or expected_delta_w == 0:
            return
        self._observation = _Observation(
            started=now,
            before_w=float(median(self._recent)),
            changed=changed,
            expected_delta_w=expected_delta_w,
        )

    def _adjust(
        self,
        steps: dict[str, int],
        limit: dict[str, int],
        power: dict[str, float],
        tiers: Sequence[Tier],
        requested_w: float,
        dead: float,
        p_min_w: float,
    ) -> dict[str, int]:
        def expected(n: Mapping[str, int]) -> float:
            return expected_load_w(n, power, p_min_w)

        n = dict(steps)
        for _ in range(MAX_ITERATIONS):
            error = requested_w - expected(n)
            if error > dead:
                candidate = _raise(n, limit, tiers)
            elif error < -dead:
                candidate = self._lower(n, expected, tiers, requested_w)
            else:
                break
            if candidate is None:
                break
            # below the minimum stage the load stays at Pmin, so a step there cannot improve the error
            if abs(requested_w - expected(candidate)) >= abs(error) and sum(n.values()) >= MIN_STAGE:
                break
            n = candidate
        return self._enforce_floor(n, limit, tiers)

    def _lower(
        self,
        n: Mapping[str, int],
        expected: Callable[[Mapping[str, int]], float],
        tiers: Sequence[Tier],
        requested_w: float,
    ) -> dict[str, int] | None:
        """One step less for the fullest served room (of equal fill the one with the most steps)."""
        ranked = _flat(tiers)
        for r in _fullest_first(n, tiers):
            candidate = dict(n)
            candidate[r.id] -= 1
            if not _floor_ok(candidate, ranked):
                continue
            return candidate
        return None

    def _enforce_floor(
        self, n: dict[str, int], limit: Mapping[str, int], tiers: Sequence[Tier]
    ) -> dict[str, int]:
        """The plant never runs below two power steps (spread over two units if there are two)."""
        ranked = _flat(tiers)
        for _ in range(MAX_ITERATIONS):
            if _floor_ok(n, ranked):
                break
            units = sum(1 for v in n.values() if v > 0)
            pick = _pick_up(n, limit, tiers, fresh=units < min(2, len(ranked)))
            if pick is None:
                break
            n = dict(n)
            n[pick.id] += 1
        return n


def _flat(tiers: Sequence[Tier]) -> list[RoomConfig]:
    return [r for tier in tiers for group in tier for r in group]


def _raise(n: Mapping[str, int], limit: Mapping[str, int], tiers: Sequence[Tier]) -> dict[str, int] | None:
    pick = _pick_up(n, limit, tiers)
    if pick is None:
        return None
    candidate = dict(n)
    candidate[pick.id] += 1
    return candidate


def _pick_up(
    n: Mapping[str, int], limit: Mapping[str, int], tiers: Sequence[Tier], fresh: bool = False
) -> RoomConfig | None:
    """The unit to raise: the room with the largest deviation, the rooms within its tie band in turn.

    The tiers are ordered by deviation, so the first tier with a unit that has room left decides. Inside
    the tier the unit with the fewest steps comes first, of equal steps the first of the tier (power class
    group, configured order): the power class decides only on a tie. `fresh` takes a unit without steps.
    """
    for tier in tiers:
        members = [
            r for group in tier for r in group if n[r.id] < limit[r.id] and (not fresh or n[r.id] == 0)
        ]
        if members:
            return min(members, key=lambda r: n[r.id])
    return None


def _fullest_first(n: Mapping[str, int], tiers: Sequence[Tier]) -> list[RoomConfig]:
    """Served units, the last tier (least deviation) first, inside a tier the most steps first."""
    order: list[RoomConfig] = []
    for tier in reversed(tiers):
        members = [r for group in tier for r in group if n[r.id] > 0]
        order.extend(sorted(members, key=lambda r: -n[r.id]))
    return order


def _floor_ok(n: Mapping[str, int], ranked: Sequence[RoomConfig]) -> bool:
    units = sum(1 for v in n.values() if v > 0)
    return sum(n.values()) >= MIN_STAGE and units >= min(2, len(ranked))
