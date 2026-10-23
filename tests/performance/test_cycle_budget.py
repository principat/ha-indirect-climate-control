"""Performance budget of a full control cycle inside Home Assistant (7 indoor units).

Measures the time a cycle occupies the event loop, the service calls sent to the indoor units and the
state changes that end up in the recorder database. Budgets are generous (shared CI runners).
"""

from __future__ import annotations

import statistics
import time

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import EVENT_STATE_CHANGED  # noqa: E402
from homeassistant.core import Event, HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.climate_control.const import DOMAIN  # noqa: E402
from custom_components.climate_control.sensor import CCSensor  # noqa: E402
from tests.integration.fakes import INSTALLATION, FakeUnits, room_data, set_plan  # noqa: E402

UNITS = [f"climate.unit_{i}" for i in range(7)]
CYCLES = 200


async def _setup(hass: HomeAssistant, units: FakeUnits) -> MockConfigEntry:
    for entity_id in UNITS:
        units.set(entity_id, "fan_only", 20)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Climate Control",
        data=dict(INSTALLATION),
        options={"planner_horizon_h": 48},
        subentries_data=[
            {"data": room_data(e), "subentry_type": "room", "title": e, "unique_id": e} for e in UNITS
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_cycle_time_and_load_on_home_assistant(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 2.0, hours=48)
    entry = await _setup(hass, units)
    coordinator = entry.runtime_data
    own = {e.entity_id for e in hass.data["entity_registry"].entities.values() if e.platform == DOMAIN}
    changes: list[str] = []

    def count(event: Event) -> None:
        if event.data["entity_id"] in own:
            changes.append(event.data["entity_id"])

    hass.bus.async_listen(EVENT_STATE_CHANGED, count)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    units.calls.clear()
    changes.clear()

    # Steady state: nothing changes -> no commands, no recorder rows.
    steady: list[float] = []
    for _ in range(CYCLES):
        t = time.perf_counter()
        await coordinator.async_refresh()
        steady.append(time.perf_counter() - t)
    await hass.async_block_till_done()
    steady_calls, steady_changes = len(units.calls), len(changes)

    # Busy state: a device temperature changes every cycle.
    busy: list[float] = []
    for c in range(CYCLES):
        units.set(UNITS[c % 7], hass.states.get(UNITS[c % 7]).state, 19 + c % 3)  # type: ignore[union-attr]
        t = time.perf_counter()
        await coordinator.async_refresh()
        busy.append(time.perf_counter() - t)
        await hass.async_block_till_done()

    def ms(values: list[float]) -> str:
        return f"mean {statistics.mean(values) * 1000:.2f} ms, max {max(values) * 1000:.2f} ms"

    print(
        f"\n[ha] 7 units, {CYCLES} cycles each. steady: {ms(steady)}, {steady_calls} service calls, "
        f"{steady_changes} state changes. busy: {ms(busy)}, {len(units.calls)} service calls, "
        f"{len(changes) - steady_changes} state changes"
    )
    assert steady_calls == 0
    assert steady_changes == 0
    assert statistics.mean(steady) * 1000 < 20
    assert statistics.mean(busy) * 1000 < 100  # stress case; shared CI runners vary a lot


def test_forecast_attributes_are_not_recorded() -> None:
    """Forecast lists change hourly and are large; they must not fill the recorder database."""
    assert "forecast" in CCSensor._unrecorded_attributes
