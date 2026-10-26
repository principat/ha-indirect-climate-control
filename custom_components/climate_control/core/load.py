"""FR-LOAD-01 / FR-LOAD-02 / FR-LOAD-05 to FR-LOAD-08: load control by served rooms, power per room learned.

A served room is an indoor unit that heats towards the setpoint of its room. One served room brings the
outdoor unit to Pmin, every further room adds the learned power of its room. Which rooms are served, when a
further one is added and when one leaves is decided by `serving.py`: a room stays served until its unit has
cut off, the room with the largest deviation comes next. A dead band around the request and the limits of the
rooms bound it. It runs on every cycle, there is no time window for a rotation.

Learning: after the number of lanes changed, the outdoor unit's power is watched until it has settled (cycle
means within the dead band over three cycles, with a maximum time that adapts to the plant). The change
divided by the changed lanes updates the power of the rooms involved. Disturbed observations are dropped.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, median
from typing import Any

from .config import InstallationConfig, RoomConfig
from .distribution import Tier
from .model import Season
from .serving import Serving

SETTLE_CYCLES = 3
BOOTSTRAP_ESTIMATES = 3  # the first estimates of a unit replace the start value by their median
RATE = 0.2
MAX_CHANGE = 0.25
FACTOR_MIN, FACTOR_MAX = 0.1, 10.0  # plausible ratio between the observed and the expected change
SETTLE_FACTOR = 3.0  # the maximum wait is this many times the typical settling time


def start_power_w(cfg: InstallationConfig) -> float:
    """FR-LOAD-02: half of the range between Pmin and Pmax per further room (Pmax with three rooms)."""
    return (cfg.p_max_w - cfg.p_min_w) / 2


def expected_load_w(steps: Mapping[str, int], power: Mapping[str, float], p_min_w: float) -> float:
    """Outdoor power for the served rooms: Pmin with one room, each further room adds its power.

    A further room counts with the mean power of the served rooms. Without a room there is no load.
    """
    served = [rid for rid, n in steps.items() if n > 0]
    if not served:
        return 0.0
    mean_w = sum(power.get(rid, 0.0) for rid in served) / len(served)
    return p_min_w + mean_w * (len(served) - 1)


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
        self.released: list[str] = []  # rooms that left in the last cycle
        self.serving = Serving()
        self.expected_w = 0.0
        self._recent: deque[float] = deque(maxlen=SETTLE_CYCLES)
        self._observation: _Observation | None = None
        self._settle_s: deque[float] = deque(maxlen=10)

    # -- state ---------------------------------------------------------------------------------

    def reset(self) -> None:
        """The plant stopped, the season changed or the plan is gone: the next run starts afresh."""
        self.steps = {}
        self.released = []
        self.serving.reset()
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
        live: Mapping[str, float] | None = None,
        present: set[str] | None = None,
    ) -> dict[str, int]:
        """Served rooms (one step each) for the requested power; `tiers`: eligible units, most urgent first.

        `live` are the reported device temperatures of the cycle (a served room is measured on them, never on
        the frozen value), `present` the rooms that are in the control at all (default: the eligible ones).
        `disturbed` tells that something else changed the load since the last cycle (a room under protection,
        a window, a change of the season): a running observation is then not trustworthy.
        """
        ranked = _flat(tiers)
        ids = {r.id for r in ranked}
        if disturbed or any(rid not in ids for rid in self.steps):
            self._observation = None
        power = {r.id: self._power(cfg, r.id) for r in ranked}
        before = dict(self.steps)
        measured = mean(self._recent) if self._recent else None
        turn = self.serving.step(
            now,
            cfg,
            season,
            requested_w,
            measured,
            ranked,
            present if present is not None else ids,
            live or {},
            _max_rooms(power, cfg),
            sum(power.values()) / len(power) if power else 0.0,
        )
        after = {rid: 1 for rid in turn.active}
        self.released = list(turn.released)
        added = {rid for rid in after if rid not in before}
        dropped = {rid for rid in before if rid not in after}
        if len(after) != len(before) and (added or dropped):
            # a run that starts from standby only reaches Pmin (one room): nothing to learn from it
            expected_delta = expected_load_w(after, power, cfg.p_min_w) - expected_load_w(
                before, power, cfg.p_min_w
            )
            changed = {rid: 1 for rid in added} if len(after) > len(before) else {rid: -1 for rid in dropped}
            self._begin(now, changed, expected_delta if before else 0.0)
        self.steps = after
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


def _flat(tiers: Sequence[Tier]) -> list[RoomConfig]:
    return [r for tier in tiers for group in tier for r in group]


def _max_rooms(power: Mapping[str, float], cfg: InstallationConfig) -> int:
    """Largest number of rooms served at once: Pmax bounds it (a further room adds its mean power)."""
    if not power:
        return 0
    mean_w = sum(power.values()) / len(power)
    n_max = len(power)
    if mean_w > 0:
        n_max = min(n_max, 1 + max(0, round((cfg.p_max_w - cfg.p_min_w) / mean_w)))
    return max(1, n_max)
