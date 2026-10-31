"""Integration level: operating modes, heating offset and fan level (FR-OPM-*, FR-OFS-01, FR-FAN-01)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.climate_control.const import DOMAIN

from .fakes import ROOMS, FakeUnits, room_data, run_cycle, set_plan, submit_room

A, B, C = ROOMS
SELECT = "select.climate_control_operating_mode"
POWER = "sensor.outdoor_power"
MODES = ["hems_optimized", "hems_buffer", "manufacturer", "manufacturer_cycle"]
ALWAYS_NIGHT = {"night_start_h": 0, "night_end_h": 24}  # the night setback applies at any time of day
NEVER_NIGHT = {"night_start_h": 0, "night_end_h": 0}


def _sensor(hass: HomeAssistant, entry: Any, key: str) -> Any:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, key
    state = hass.states.get(entity_id)
    assert state is not None
    return state


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": SELECT, "option": option}, blocking=True
    )
    await hass.async_block_till_done()


def _power(hass: HomeAssistant, watts: float) -> None:
    hass.states.async_set(POWER, str(watts), {"unit_of_measurement": "W"})


@pytest.mark.req("FR-OPM-01")
async def test_the_operating_mode_is_a_choice_that_survives_a_restart(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    state = hass.states.get(SELECT)
    assert state is not None and state.state == "hems_optimized"  # the default
    assert state.attributes["options"] == MODES
    await _select(hass, "manufacturer")
    assert hass.states.get(SELECT).state == "manufacturer"  # type: ignore[union-attr]
    assert entry.runtime_data.data.operating_mode.value == "manufacturer"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(SELECT).state == "manufacturer"  # type: ignore[union-attr]
    await _select(hass, "hems_optimized")
    assert entry.runtime_data.operating_mode.value == "hems_optimized"


@pytest.mark.req("FR-OPM-02")
async def test_the_manufacturer_control_passes_the_setpoints_and_ignores_the_plan(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 3.3)  # the plan asks for full power, the manufacturer control does not follow it
    entry = await setup_entry(NEVER_NIGHT)
    await _select(hass, "manufacturer")
    assert {units.mode(e) for e in ROOMS} == {"heat"}
    assert {units.target(e) for e in ROOMS} == {21.0}  # the setpoint of the rooms, passed through
    assert hass.states.get("binary_sensor.climate_control_running").state == "off"  # type: ignore[union-attr]
    assert float(_sensor(hass, entry, "capacity").state) == 0.0  # no buffer left to the planner


@pytest.mark.req("FR-OPM-02")
async def test_the_manufacturer_control_applies_the_night_setback(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    await setup_entry(ALWAYS_NIGHT)
    await _select(hass, "manufacturer")
    assert {units.target(e) for e in ROOMS} == {20.0}  # 21 minus the setback of 1


@pytest.mark.req("FR-OPM-03")
async def test_the_cycle_optimization_moves_the_setpoint_while_the_outdoor_unit_is_in_standby(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    _power(hass, 100)  # below the stop threshold of 650 W
    await setup_entry({**NEVER_NIGHT, "standby_delay_s": 0})
    await _select(hass, "manufacturer_cycle")
    assert {units.mode(e) for e in ROOMS} == {"heat"}
    assert {units.target(e) for e in ROOMS} == {20.0}  # standby: lowered by 1
    _power(hass, 2000)
    await run_cycle(hass)  # the mean of the last two readings is above the threshold again
    assert {units.target(e) for e in ROOMS} == {21.0}


@pytest.mark.req("FR-OPM-04")
async def test_the_charge_cost_carries_the_cooldown_surcharge_after_the_run_ended(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 2.0)
    entry = await setup_entry({"min_run_s": 0})
    assert float(_sensor(hass, entry, "charge_cost").state) == pytest.approx(0.001)  # late charging only
    set_plan(hass, 0)
    await run_cycle(hass)  # the run ends: standby
    assert hass.states.get("binary_sensor.climate_control_running").state == "off"  # type: ignore[union-attr]
    assert float(_sensor(hass, entry, "charge_cost").state) == pytest.approx(0.002)  # plus the cooldown
    set_plan(hass, 2.0)
    await run_cycle(hass)  # a new run: the surcharge is gone
    assert float(_sensor(hass, entry, "charge_cost").state) == pytest.approx(0.001)


@pytest.mark.req("FR-OPM-05")
async def test_the_buffer_control_keeps_the_comfort_setpoint_and_reports_the_buffer_scale(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry(NEVER_NIGHT)
    await _select(hass, "hems_buffer")
    assert {units.mode(e) for e in ROOMS} == {"heat"}
    assert {units.target(e) for e in ROOMS} == {21.0}  # the units hold the comfort temperature themselves
    assert (
        float(_sensor(hass, entry, "soc").state) == 0.0
    )  # rooms at 20: the lowered setpoint, bottom of the scale
    assert float(_sensor(hass, entry, "max_charge").state) == 100.0
    assert float(_sensor(hass, entry, "min_charge").state) == pytest.approx(33.33)  # by day: the setpoint
    for entity_id in ROOMS:
        units.set(entity_id, "heat", 22.0, 21.0)
    await run_cycle(hass)  # 2 of the 3 K of every scale: 66.7 %, median with the 0 % before: 33.3
    assert float(_sensor(hass, entry, "soc").state) == pytest.approx(100 / 3, abs=0.01)


@pytest.mark.req("FR-OPM-06")
async def test_the_requested_power_raises_the_setpoints_in_steps(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 1.3)  # 1300 W of 3300 W: 5 of the 12 buffer steps
    entry = await setup_entry(NEVER_NIGHT)
    await _select(hass, "hems_buffer")
    targets = sorted(units.target(e) for e in ROOMS)  # type: ignore[type-var]
    assert targets == [21.5, 22.0, 22.0]  # steps of 0.5, distributed round robin
    assert entry.runtime_data.data.result.requested_w == pytest.approx(1300)
    set_plan(hass, 0)
    await run_cycle(hass)
    assert {units.target(e) for e in ROOMS} == {21.0}  # no plan: back to the comfort setpoint


@pytest.mark.req("FR-FAN-01")
async def test_the_fan_level_is_raised_while_heating_and_reset_afterwards(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 20, fan="auto")
    set_plan(hass, 2.0)
    await setup_entry({"min_run_s": 0}, a={"fan_heat": "high"}, b={"fan_heat": "high"})
    assert units.mode(A) == "heat" and units.fan(A) == "high"  # heating under our control: raised
    assert units.fan(B) == "auto"  # neutral: untouched
    assert units.fan(C) == "auto"  # no level configured: untouched
    set_plan(hass, 0)
    await run_cycle(hass)
    assert units.mode(A) == "fan_only"
    assert units.fan(A) == "auto"  # reset to the level from before
    assert [c for c in units.calls if c[0] == C and c[1] == "set_fan_mode"] == []


@pytest.mark.req("FR-FAN-01")
async def test_the_fan_level_after_heating_can_be_configured_and_the_manufacturer_control_resets_it(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 20, fan="auto")
    set_plan(hass, 2.0)
    await setup_entry(NEVER_NIGHT, a={"fan_heat": "high", "fan_neutral": "low"})
    assert units.mode(A) == "heat" and units.fan(A) == "high"
    await _select(hass, "manufacturer")  # the manufacturer control keeps the unit heating, without the boost
    assert units.mode(A) == "heat" and units.fan(A) == "low"


@pytest.mark.req("FR-FAN-01")
async def test_the_fan_levels_are_optional_fields_of_an_indoor_unit(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    assert entry.runtime_data.cfg.room(A).fan_heat is None
    first = next(iter(entry.subentries.values()))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": SOURCE_RECONFIGURE, "subentry_id": first.subentry_id}
    )
    assert result["type"] == FlowResultType.FORM
    assert {"fan_heat", "fan_neutral", "help_fan_heat", "help_fan_neutral"} <= {
        str(k) for k in result["data_schema"].schema
    }
    values = {k: v for k, v in room_data(A, fan_heat="high", fan_neutral="auto").items() if k != "entity_id"}
    result = await submit_room(hass, result["flow_id"], values)
    assert result["type"] == FlowResultType.ABORT
    await hass.async_block_till_done()
    room = entry.runtime_data.cfg.room(A)
    assert (room.fan_heat, room.fan_neutral) == ("high", "auto")


@pytest.mark.req("FR-OFS-01")
async def test_the_heating_offset_is_taken_off_the_reading_and_the_setpoint_stays(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 23)  # 2 above the setpoint of 21, the offset of the unit
    set_plan(hass, 0)
    entry = await setup_entry({"heat_offset_k": 2.0})
    assert float(_sensor(hass, entry, "soc").state) == pytest.approx(50.0)  # every room is on its setpoint
    for entity_id in ROOMS:
        units.set(entity_id, "fan_only", 21)  # 19 after the offset: 2 below the setpoint
    set_plan(hass, 2.0)
    await run_cycle(hass)
    heating = [e for e in ROOMS if units.mode(e) == "heat"]
    assert heating and all(units.target(e) == 21.0 for e in heating)  # the setpoint is not raised
