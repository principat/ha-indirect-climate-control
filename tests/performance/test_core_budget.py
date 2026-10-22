"""Performance budget of the core: one simulated day of control cycles.

Runs without Home Assistant (also under arm64 emulation): the core package is imported directly.
Budgets are generous on purpose (shared CI runners); the printed numbers are the actual result.
"""

from __future__ import annotations

import importlib
import os
import random
import statistics
import sys
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest


def _core(name: str) -> ModuleType:
    try:
        return importlib.import_module(f"custom_components.climate_control.core.{name}")
    except ImportError:  # no Home Assistant installed: import the core package on its own
        sys.path.insert(0, str(Path(__file__).parents[2] / "custom_components" / "climate_control"))
        return importlib.import_module(f"core.{name}")


config = _core("config")
controller = _core("controller")
model = _core("model")
plan_mod = _core("plan")
planner_model = _core("planner_model")

T0 = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
CYCLES_PER_DAY = 1440  # cycle 60 s
# Time budgets are for native execution; raise for emulation (e.g. PERF_BUDGET_FACTOR=10 under QEMU).
FACTOR = float(os.environ.get("PERF_BUDGET_FACTOR", "1"))


def _installation(rooms: int) -> object:
    classes = ("small", "large")
    return config.InstallationConfig(
        p_min_w=1300,
        p_max_w=3300,
        stage1_w=1500,
        capacity_kwh_per_k=3.5,
        rooms=tuple(
            config.RoomConfig(f"r{i}", f"R{i}", 21.0, classes[i % 2], 400.0 + 200 * (i % 2), 12.0)
            for i in range(rooms)
        ),
        params=config.Parameters(planner_horizon_h=48),
    )


def _day(rooms: int, trace_memory: bool) -> tuple[list[float], int]:
    """Run one simulated day; return per-cycle times (s) and memory growth (bytes, if traced).

    Memory tracing slows Python down several times, so time and memory are measured in separate runs.
    """
    rnd = random.Random(1)
    cfg = _installation(rooms)
    ctrl = controller.Controller(cfg)
    temps = {f"r{i}": 20.0 for i in range(rooms)}
    modes = dict.fromkeys(temps, model.Mode.FAN)
    times: list[float] = []
    if trace_memory:
        tracemalloc.start()
    mem_after_warmup = 0
    for c in range(CYCLES_PER_DAY):
        now = T0 + timedelta(minutes=c)
        for rid in temps:
            temps[rid] = min(29.0, max(15.0, temps[rid] + rnd.choice((-1, 0, 0, 0, 1))))
        start = now.replace(minute=0)
        kw = (0.0, 1.1, 2.5, 3.3)[(c // 90) % 4]
        forecast = [{"time": (start + timedelta(hours=h)).isoformat(), "value": kw} for h in range(48)]
        states = {
            rid: model.RoomState(modes[rid], temps[rid], rid == "r1" and 600 < c < 700) for rid in temps
        }
        t = time.perf_counter()
        plan = plan_mod.plan_from_forecast(str(kw), "kW", forecast, now)
        result = ctrl.step(now, plan, states, {"r0": 22.0})
        planner_model.planner_inputs(cfg, now)
        if not trace_memory:  # the list itself would show up as memory growth
            times.append(time.perf_counter() - t)
        for rid, cmd in result.commands.items():
            modes[rid] = cmd.mode
        if trace_memory and c == 100:
            mem_after_warmup = tracemalloc.get_traced_memory()[0]
    if not trace_memory:
        return times, 0
    mem_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    return times, mem_end - mem_after_warmup


@pytest.mark.parametrize("rooms", [7, 30])
def test_one_day_of_cycles_stays_within_budget(rooms: int) -> None:
    times, _ = _day(rooms, trace_memory=False)
    _, growth = _day(rooms, trace_memory=True)
    mean_ms = statistics.mean(times) * 1000
    p99_ms = sorted(times)[int(len(times) * 0.99)] * 1000
    max_ms = max(times) * 1000
    print(
        f"\n[core] {rooms} rooms, {len(times)} cycles: mean {mean_ms:.3f} ms, p99 {p99_ms:.3f} ms, "
        f"max {max_ms:.3f} ms, memory growth after warm-up {growth / 1024:.1f} KiB"
    )
    # Budget per 60 s cycle: far below one event-loop slice (HA warns at 100 ms+ blocking).
    assert mean_ms < 5 * FACTOR
    assert max_ms < 50 * FACTOR
    # Bounded state: smoothing window, filters and timers do not grow over the day.
    assert growth < 64 * 1024
