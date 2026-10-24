"""Integration level: Fahrenheit plants (FR-UNIT-01)."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import DOMAIN

from .fakes import INSTALLATION, ROOMS, FakeUnits, room_subentries, run_cycle, set_plan

A, B, C = ROOMS
FAHRENHEIT_ROOM = {"setpoint_c": 70.0, "comfort_max_c": 75.0, "overload_max_c": 82.0}  # 21, 24, 28 degC
ALL_ROOMS = {"a": FAHRENHEIT_ROOM, "b": FAHRENHEIT_ROOM, "c": FAHRENHEIT_ROOM}


async def _setup(
    hass: HomeAssistant, options: dict[str, Any] | None = None, **rooms: dict[str, Any]
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Climate Control",
        data={**INSTALLATION, "temperature_unit": "fahrenheit"},
        options=options or {},
        subentries_data=room_subentries(**(rooms or ALL_ROOMS)),
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _value(hass: HomeAssistant, entity_id: str) -> float:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return float(state.state)


@pytest.mark.req("FR-UNIT-01")
async def test_fahrenheit_devices_give_the_same_state_of_charge_and_get_fahrenheit_setpoints(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 68)  # 20 degC
    set_plan(hass, 2.0)
    await _setup(hass)
    assert _value(hass, "sensor.climate_control_state_of_charge") == pytest.approx(33.33, abs=0.01)
    assert {units.mode(e) for e in ROOMS} == {"heat"}
    assert units.target(A) == 70.0  # 20 degC + 1 K offset = 21 degC = 69.8 degF, sent in whole degrees
    units.calls.clear()
    await run_cycle(hass)
    assert units.calls == []  # the sent value is recognised as the current one: no repeated commands


@pytest.mark.req("FR-UNIT-01")
async def test_hard_minimum_protection_works_in_fahrenheit(hass: HomeAssistant, units: FakeUnits) -> None:
    units.set(B, "fan_only", 64)  # 17.8 degC: 3.3 K below the setpoint of 70 degF
    for entity_id in (A, C):
        units.set(entity_id, "fan_only", 70)
    set_plan(hass, 0)
    await _setup(hass)
    assert units.mode(B) == "heat" and units.target(B) == 70.0  # the setpoint, in degF
    assert units.mode(A) == "fan_only"


@pytest.mark.req("FR-UNIT-01")
async def test_setpoint_entity_values_are_fahrenheit_too(hass: HomeAssistant, units: FakeUnits) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 68)  # 20 degC
    set_plan(hass, 0)
    hass.states.async_set("input_number.setpoint_a", "71")  # 21.67 degC
    with_entity = {**FAHRENHEIT_ROOM, "setpoint_entity": "input_number.setpoint_a"}
    await _setup(hass, a=with_entity, b=FAHRENHEIT_ROOM, c=FAHRENHEIT_ROOM)
    assert _value(hass, "sensor.a_deviation_from_setpoint") == pytest.approx(1.67, abs=0.01)  # in K
    hass.states.async_set(
        "input_number.setpoint_a", "100"
    )  # 37.8 degC: not plausible, the fixed 70 degF counts
    await run_cycle(hass)
    assert _value(hass, "sensor.a_deviation_from_setpoint") == pytest.approx(1.11, abs=0.01)


@pytest.mark.req("FR-UNIT-01")
async def test_the_capacity_follows_the_scale_in_fahrenheit(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _setup(hass)
    assert _value(hass, "sensor.climate_control_capacity") == 45.0  # 3 kWh/K x (86 - 59) degF = 15 K
    await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, options={"soc_min_c": 50.0, "soc_max_c": 95.0})  # 25 K wide
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _value(hass, "sensor.climate_control_capacity") == 75.0


@pytest.mark.req("FR-UNIT-01")
async def test_unit_is_chosen_in_the_installation_form_celsius_is_the_default(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    markers = {str(m): m for m in result["data_schema"].schema}
    assert "temperature_unit" in markers and "help_temperature_unit" in markers
    assert markers["temperature_unit"].default() == "celsius"
    base = {"name": "A", **INSTALLATION}
    plain = await hass.config_entries.flow.async_configure(result["flow_id"], base)
    assert plain["result"].data["temperature_unit"] == "celsius"
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    chosen = await hass.config_entries.flow.async_configure(
        again["flow_id"], {**base, "name": "B", "temperature_unit": "fahrenheit"}
    )
    assert chosen["result"].data["temperature_unit"] == "fahrenheit"


@pytest.mark.req("FR-UNIT-01")
async def test_forms_of_a_fahrenheit_plant_use_fahrenheit(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _setup(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": "user"}
    )
    schema = {str(m): (m, v) for m, v in result["data_schema"].schema.items()}
    marker, selector = schema["setpoint_c"]
    assert marker.default() == 70.0 and selector.config["unit_of_measurement"] == "°F"
    assert selector.config["min"] == 41.0 and selector.config["max"] == 86.0
    assert schema["overload_max_c"][0].default() == 82.0
    values = {
        "entity_id": "climate.extra",
        "name": "X",
        "setpoint_c": 70.0,
        "comfort_max_c": 75.0,
        "overload_max_c": 90.0,  # 32 degC: beyond the scale
        "nominal_power_w": 700,
        "area_m2": 10,
    }
    refused = await hass.config_entries.subentries.async_configure(result["flow_id"], values)
    assert refused["type"] == FlowResultType.FORM and refused["errors"] == {"base": "room_limits"}
    accepted = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**values, "overload_max_c": 82.0}
    )
    assert accepted["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.req("FR-UNIT-01")
async def test_options_show_and_keep_the_scale_in_fahrenheit(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _setup(hass)
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "soc"})
    defaults = {
        str(m): m.default() for m in form["data_schema"].schema if str(m) in ("soc_min_c", "soc_max_c")
    }
    assert defaults == {"soc_min_c": 59.0, "soc_max_c": 86.0}
    saved = await hass.config_entries.options.async_configure(form["flow_id"], {"soc_smoothing_s": 600})
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert (
        entry.options["soc_min_c"] == 59.0 and entry.options["soc_max_c"] == 86.0
    )  # not the Celsius defaults
