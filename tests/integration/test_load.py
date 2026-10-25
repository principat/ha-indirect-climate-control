"""Integration level: load control (FR-LOAD-01) and the power per step learned per unit (FR-LOAD-02)."""

from datetime import timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.climate_control.const import DOMAIN, SERVICE_RESET_LEARNED

from .fakes import ROOMS, FakeUnits, run_cycle, set_plan, submit_room

A, B, C = ROOMS
POWER = "sensor.outdoor_power"


async def _minute(hass: HomeAssistant, freezer: FrozenDateTimeFactory, watts: float, kw: float) -> None:
    freezer.tick(timedelta(minutes=1))
    set_plan(hass, kw)
    hass.states.async_set(POWER, str(watts), {"unit_of_measurement": "W"})
    await run_cycle(hass)


@pytest.mark.req("FR-LOAD-01")
async def test_the_step_size_is_an_optional_field_of_the_indoor_unit_in_the_unit_of_the_plant(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": "user"}
    )
    schema = {str(m): (m, v) for m, v in result["data_schema"].schema.items()}
    marker, selector = schema["step"]
    assert marker.default() == 0.5 and selector.config["unit_of_measurement"] == "°C"
    assert "help_step" in schema
    minimal = {
        "entity_id": "climate.extra",
        "name": "X",
        "setpoint_c": 21.0,
        "nominal_power_w": 700,
        "area_m2": 10,
    }
    added = await submit_room(hass, result["flow_id"], minimal)  # the field is optional
    assert added["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.cfg.room("climate.extra").step == 0.5


@pytest.mark.req("FR-LOAD-01")
async def test_the_setpoint_of_the_served_unit_lies_one_step_beyond_its_start_threshold(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 2.0)
    entry = await setup_entry(a={"step": 1.0})
    result = entry.runtime_data.data.result
    assert result.steps == {A: 1}  # one room first, the second follows half a rotation time later
    assert units.target(A) == pytest.approx(20 - 2 + 1.0)  # one step of 1.0 above the start threshold
    assert result.expected_w == 1300.0
    assert units.mode(B) == "fan_only" and units.mode(C) == "fan_only"


@pytest.mark.req("FR-LOAD-03")
@pytest.mark.req("FR-LOAD-04")
async def test_the_next_room_starts_first_and_the_room_that_gives_way_goes_to_standby_afterwards(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 1.3)
    await setup_entry()
    assert [e for e in ROOMS if units.mode(e) == "heat"] == [A]  # the minimum load: one room
    units.set(A, "heat", 21.0, units.target(A))  # A rose by more than its step: the next room is up
    await run_cycle(hass)
    assert units.mode(B) == "heat"  # the next room has started ...
    assert units.mode(A) == "heat"  # ... while A still runs
    await run_cycle(hass)  # B shows its setpoint now
    assert units.mode(A) == "fan_only" and units.mode(B) == "heat"  # A is aired until its turn comes again


@pytest.mark.req("FR-LOAD-02")
async def test_the_power_per_step_is_a_diagnostic_sensor_per_indoor_unit_with_the_start_value(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    registry = er.async_get(hass)
    sensors = [
        e
        for e in registry.entities.values()
        if e.config_entry_id == entry.entry_id and e.translation_key == "room_step_power"
    ]
    assert len(sensors) == len(ROOMS)
    assert {e.entity_category for e in sensors} == {er.EntityCategory.DIAGNOSTIC}
    for sensor in sensors:
        assert float(hass.states.get(sensor.entity_id).state) == pytest.approx(
            1000.0
        )  # (Pmax - Pmin) / 2 per further room


@pytest.mark.req("FR-OBS-02")
async def test_the_planned_offset_is_a_diagnostic_sensor_per_indoor_unit(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 2.0)
    entry = await setup_entry(a={"step": 1.0})
    result = entry.runtime_data.data.result
    registry = er.async_get(hass)
    by_room = {}
    for e in registry.entities.values():
        if e.config_entry_id == entry.entry_id and e.translation_key == "room_offset":
            by_room[e.entity_id.split(".")[1][0].upper()] = float(hass.states.get(e.entity_id).state)
    assert set(by_room) == {"A", "B", "C"}
    for entity_id, room in zip(ROOMS, "ABC", strict=True):
        step = 1.0 if entity_id == A else 0.5
        assert by_room[room] == pytest.approx(result.steps.get(entity_id, 0) * step)
    assert sum(by_room.values()) > 0  # the served units have a planned offset, the others none


@pytest.mark.req("FR-LOAD-02")
async def test_the_power_per_step_is_learned_from_the_outdoor_power_and_survives_a_restart(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry: Any,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    set_plan(hass, 0)
    hass.states.async_set(POWER, "20", {"unit_of_measurement": "W"})
    entry = await setup_entry()
    for _ in range(4):
        await _minute(hass, freezer, 20, 0)  # the idle power before the plant starts
    await _minute(hass, freezer, 20, 2.0)  # the plant starts, the load control sets the steps
    assert entry.runtime_data.data.result.steps
    for watts in (400, 900, 1400, 1950, 2000, 2000, 2000):  # the outdoor power follows with a lag
        await _minute(hass, freezer, watts, 2.0)
    # a run from standby only teaches nothing; the next change of the request while it runs does
    await _minute(hass, freezer, 2000, 3.0)
    for watts in (2300, 2700, 2900, 2950, 2950, 2950, 2950, 2950):
        await _minute(hass, freezer, watts, 3.0)
    model = entry.runtime_data.controller.load_model
    assert model.units, "nothing was learned"
    assert all(item.estimates >= 1 for item in model.units.values())
    assert await hass.config_entries.async_unload(entry.entry_id)
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}.learned"]["data"]["load"]
    assert set(stored) == set(model.units)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert set(entry.runtime_data.controller.load_model.units) == set(stored)  # restored


@pytest.mark.req("FR-LOAD-02")
async def test_the_reset_service_also_resets_the_power_per_step(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    model = entry.runtime_data.controller.load_model
    for value in (300.0, 400.0, 500.0):
        model.update_unit(
            A,
            value,
            entry.runtime_data.data.result.planned_w and None or __import__("datetime").datetime.now(),
        )
    assert model.power(A, 333.0) == 400.0
    await hass.services.async_call(DOMAIN, SERVICE_RESET_LEARNED, blocking=True)
    await hass.async_block_till_done()
    assert not model.units
