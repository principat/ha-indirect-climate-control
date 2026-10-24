"""Integration level: Fahrenheit plants (FR-UNIT-01)."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import DOMAIN

from .fakes import INSTALLATION, ROOMS, FakeUnits, room_subentries, run_cycle, set_plan

A, B, C = ROOMS
FAHRENHEIT_ROOM = {"setpoint_c": 70.0}  # 21 degC; the distances keep their numbers (1 K becomes 1 degF)
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
async def test_fahrenheit_plant_works_with_the_numbers_as_they_are(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 68)  # 2 below the setpoint of 70
    set_plan(hass, 2.0)
    await _setup(hass)
    assert _value(hass, "sensor.climate_control_state_of_charge") == pytest.approx(26.67, abs=0.01)
    assert "heat" in {units.mode(e) for e in ROOMS}
    assert (
        units.target(A) == 67.0
    )  # 68 - start distance 2 + 2 power steps of 0.5, in degF as the device reports
    units.calls.clear()
    await run_cycle(hass)
    assert units.calls == []  # nothing to change, nothing sent


@pytest.mark.req("FR-UNIT-01")
async def test_absolute_limit_protection_works_in_fahrenheit(hass: HomeAssistant, units: FakeUnits) -> None:
    units.set(B, "fan_only", 66)  # 4 below the setpoint of 70: beyond the absolute limit of 3
    for entity_id in (A, C):
        units.set(entity_id, "fan_only", 70)
    set_plan(hass, 0)
    await _setup(hass)
    assert units.mode(B) == "heat" and units.target(B) == 70.0  # the setpoint, in degF
    assert units.mode(A) == "fan_only"


@pytest.mark.req("FR-UNIT-01")
async def test_setpoint_entity_values_are_fahrenheit_too(hass: HomeAssistant, units: FakeUnits) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 68)
    set_plan(hass, 0)
    hass.states.async_set("input_number.setpoint_a", "71")
    with_entity = {**FAHRENHEIT_ROOM, "setpoint_entity": "input_number.setpoint_a"}
    await _setup(hass, a=with_entity, b=FAHRENHEIT_ROOM, c=FAHRENHEIT_ROOM)
    assert _value(hass, "sensor.a_deviation_from_setpoint") == pytest.approx(3.0)
    hass.states.async_set("input_number.setpoint_a", "100")  # not plausible as a setpoint in degF (max. 86)
    await run_cycle(hass)
    assert _value(hass, "sensor.a_deviation_from_setpoint") == pytest.approx(2.0)  # the fixed 70 counts
    hass.states.async_set(
        "input_number.setpoint_a", "22"
    )  # a Celsius number is not plausible in degF (min. 41)
    await run_cycle(hass)
    assert _value(hass, "sensor.a_deviation_from_setpoint") == pytest.approx(2.0)


@pytest.mark.req("FR-UNIT-01")
async def test_the_capacity_follows_the_scale_in_the_unit_of_the_plant(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    set_plan(hass, 0)
    entry = await _setup(hass)
    assert _value(hass, "sensor.climate_control_capacity") == 45.0  # 3 kWh per degree x (6 below + 9 above)
    await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(entry, options={"soc_below_k": 10.0, "soc_above_k": 15.0})
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
    assert schema["band_up"][1].config["unit_of_measurement"] == "°F"  # distances are in the unit as well
    assert schema["limit_down"][0].default() == 3.0
    values = {
        "entity_id": "climate.extra",
        "name": "X",
        "setpoint_c": 70.0,
        "band_up": 4.0,  # wider than the absolute limit of 3
        "nominal_power_w": 700,
        "area_m2": 10,
    }
    refused = await hass.config_entries.subentries.async_configure(result["flow_id"], values)
    assert refused["type"] == FlowResultType.FORM and refused["errors"] == {"base": "room_limits"}
    accepted = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**values, "limit_up": 5.0}
    )
    assert accepted["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.req("FR-UNIT-01")
async def test_options_show_the_differences_in_the_unit_of_the_plant(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    set_plan(hass, 0)
    entry = await _setup(hass)
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "soc"})
    schema = {str(m): (m, v) for m, v in form["data_schema"].schema.items()}
    assert schema["soc_below_k"][0].default() == 6.0 and schema["soc_above_k"][0].default() == 9.0
    assert schema["soc_below_k"][1].config["unit_of_measurement"] == "°F"
    saved = await hass.config_entries.options.async_configure(form["flow_id"], {"soc_smoothing_s": 600})
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["soc_below_k"] == 6.0 and entry.options["soc_above_k"] == 9.0
