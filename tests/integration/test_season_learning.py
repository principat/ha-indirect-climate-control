"""Integration level: operating mode switch (FR-SEAS-01/02) and learned capacity (FR-PLNR-02/03)."""

from datetime import timedelta
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import DOMAIN, SERVICE_RESET_LEARNED

from .fakes import INSTALLATION, ROOMS, FakeUnits, room_subentries, run_cycle, set_plan

A, B, C = ROOMS
SWITCH = "input_boolean.cooling"
POWER = "sensor.outdoor_power"
LEARNED_HEAT = "sensor.climate_control_learned_capacity_heating"
LEARNED_COOL = "sensor.climate_control_learned_capacity_cooling"
CAPACITY = "sensor.climate_control_capacity"


async def _setup(hass: HomeAssistant, season: bool = True) -> MockConfigEntry:
    data = {**INSTALLATION, **({"season_entity": SWITCH} if season else {})}
    entry = MockConfigEntry(
        domain=DOMAIN, title="Climate Control", data=data, subentries_data=room_subentries()
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _value(hass: HomeAssistant, entity_id: str) -> float:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return float(state.state)


@pytest.mark.req("FR-SEAS-01")
async def test_without_a_switch_the_plant_heats(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 2.0)
    await _setup(hass, season=False)
    assert "heat" in {units.mode(e) for e in ROOMS} and "cool" not in {units.mode(e) for e in ROOMS}


@pytest.mark.req("FR-SEAS-01")
async def test_an_unavailable_or_off_switch_means_heating(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 2.0)
    hass.states.async_set(SWITCH, "unavailable")
    await _setup(hass)
    assert "heat" in {units.mode(e) for e in ROOMS} and "cool" not in {units.mode(e) for e in ROOMS}


@pytest.mark.req("FR-SEAS-01")
@pytest.mark.req("FR-SEAS-02")
async def test_the_switch_turns_the_plant_to_cooling_and_back_via_the_neutral_mode(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    for entity_id, temperature in ((A, 25), (B, 23), (C, 22)):
        units.set(entity_id, "fan_only", temperature)
    set_plan(hass, 2.0)
    hass.states.async_set(SWITCH, "on")
    await _setup(hass)
    assert {units.mode(e) for e in (A, B)} == {"cool"} and units.mode(C) == "fan_only"  # the pair of 2 kW
    assert units.target(A) == 21.0  # beyond the hard maximum: cooled to the setpoint
    soc = hass.states.get("sensor.climate_control_state_of_charge")
    assert soc is not None and float(soc.state) == pytest.approx(13.33, abs=0.01)  # 4 above the setpoint
    assert soc.attributes["worst_room"] == A
    assert _value(hass, "sensor.climate_control_overcharge_percentage") == pytest.approx(
        60.0, abs=0.01
    )  # charge side is below

    hass.states.async_set(SWITCH, "off")  # back to heating
    for entity_id, temperature in ((A, 18), (B, 18), (C, 18)):
        units.set(entity_id, units.mode(entity_id), temperature)
    units.calls.clear()
    await run_cycle(hass)
    assert {units.mode(e) for e in ROOMS} == {"fan_only"}  # first neutral ...
    assert "heat" not in {c[2] for c in units.calls}
    await run_cycle(hass)
    assert "heat" in {units.mode(e) for e in ROOMS} and "cool" not in {
        units.mode(e) for e in ROOMS
    }  # ... then heating


async def _warm_up(
    hass: HomeAssistant, units: FakeUnits, freezer: FrozenDateTimeFactory, minutes: int, sign: int = 1
) -> None:
    """The rooms change by 0.1 K per 0.2 kWh at 1.3 kW, minute by minute."""
    step_k = sign * 1300 / 60 / 1000 / 0.2 * 0.1
    for _ in range(minutes):
        freezer.tick(timedelta(minutes=1))
        set_plan(hass, 2.0)
        hass.states.async_set(POWER, "1300", {"unit_of_measurement": "W"})
        for entity_id in ROOMS:
            state = hass.states.get(entity_id)
            assert state is not None
            units.set(
                entity_id,
                state.state,
                float(state.attributes["current_temperature"]) + step_k,
                state.attributes.get("temperature"),
            )
        await run_cycle(hass)


@pytest.mark.req("FR-PLNR-02")
async def test_capacity_is_learned_from_the_power_sensor_and_the_device_temperatures(
    hass: HomeAssistant, units: FakeUnits, freezer: FrozenDateTimeFactory
) -> None:
    set_plan(hass, 2.0)
    hass.states.async_set(POWER, "1300", {"unit_of_measurement": "W"})
    await _setup(hass, season=False)
    assert _value(hass, LEARNED_HEAT) == 3.0 and _value(hass, CAPACITY) == 45.0  # start value
    await _warm_up(hass, units, freezer, 140)
    learned = hass.states.get(LEARNED_HEAT)
    assert learned is not None
    assert float(learned.state) == pytest.approx(2.0, rel=0.1)
    assert learned.attributes["estimates"] >= 3 and learned.attributes["updated"] is not None
    assert learned.attributes["pending_estimates"] == []  # the first three have replaced the start value
    assert learned.attributes["last_estimate"] == pytest.approx(2.0, rel=0.3)  # the latest single estimate
    assert _value(hass, CAPACITY) == pytest.approx(30.0, rel=0.1)  # the planner gets the learned capacity
    assert _value(hass, LEARNED_COOL) == 3.0  # cooling is learned separately


@pytest.mark.req("FR-PLNR-02")
async def test_cooling_capacity_is_learned_separately_and_drives_the_planner_while_cooling(
    hass: HomeAssistant, units: FakeUnits, freezer: FrozenDateTimeFactory
) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 26)
    set_plan(hass, 2.0)
    hass.states.async_set(SWITCH, "on")
    hass.states.async_set(POWER, "1300", {"unit_of_measurement": "W"})
    await _setup(hass)
    await _warm_up(hass, units, freezer, 140, sign=-1)
    assert _value(hass, LEARNED_COOL) == pytest.approx(2.0, rel=0.1)
    assert _value(hass, LEARNED_HEAT) == 3.0
    assert _value(hass, CAPACITY) == pytest.approx(30.0, rel=0.1)


@pytest.mark.req("FR-PLNR-02")
async def test_learned_values_survive_a_restart(
    hass: HomeAssistant, units: FakeUnits, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    set_plan(hass, 2.0)
    hass.states.async_set(POWER, "1300", {"unit_of_measurement": "W"})
    entry = await _setup(hass, season=False)
    await _warm_up(hass, units, freezer, 140)
    before = _value(hass, LEARNED_HEAT)
    assert before != 3.0
    assert await hass.config_entries.async_unload(entry.entry_id)
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}.learned"]["data"]
    assert stored["heat"]["estimates"] >= 3
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _value(hass, LEARNED_HEAT) == before


@pytest.mark.req("FR-PLNR-03")
async def test_learned_values_are_diagnostic_sensors_and_cannot_be_set(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    set_plan(hass, 0)
    await _setup(hass, season=False)
    registry = er.async_get(hass)
    for entity_id in (LEARNED_HEAT, LEARNED_COOL):
        entry = registry.async_get(entity_id)
        assert entry is not None and entry.entity_category is er.EntityCategory.DIAGNOSTIC
        assert entity_id.startswith("sensor.")


@pytest.mark.req("FR-PLNR-03")
async def test_reset_service_returns_to_the_start_values(
    hass: HomeAssistant, units: FakeUnits, freezer: FrozenDateTimeFactory, hass_storage: dict[str, Any]
) -> None:
    set_plan(hass, 2.0)
    hass.states.async_set(POWER, "1300", {"unit_of_measurement": "W"})
    entry = await _setup(hass, season=False)
    await _warm_up(hass, units, freezer, 140)
    assert _value(hass, LEARNED_HEAT) != 3.0
    await hass.services.async_call(DOMAIN, SERVICE_RESET_LEARNED, blocking=True)
    await hass.async_block_till_done()
    assert _value(hass, LEARNED_HEAT) == 3.0 and _value(hass, CAPACITY) == 45.0
    assert hass_storage[f"{DOMAIN}.{entry.entry_id}.learned"]["data"]["heat"]["estimates"] == 0


@pytest.mark.req("FR-SEAS-01")
async def test_installation_form_offers_the_switch_as_an_optional_field(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    schema = result["data_schema"].schema
    markers = {str(m): m for m in schema}
    assert "season_entity" in markers and "help_season_entity" in markers
    assert type(markers["season_entity"]).__name__ == "Optional"
    plain = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "A", **INSTALLATION})
    assert plain["type"] == FlowResultType.CREATE_ENTRY and "season_entity" not in plain["result"].data
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with_switch = await hass.config_entries.flow.async_configure(
        again["flow_id"], {"name": "B", **INSTALLATION, "season_entity": SWITCH}
    )
    assert with_switch["result"].data["season_entity"] == SWITCH
