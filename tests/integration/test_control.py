"""Integration level: control cycles against fake indoor units and a fake planner output."""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from .fakes import PLAN, ROOMS, FakeUnits, run_cycle, set_plan

A, B, C = ROOMS


def _state(hass: HomeAssistant, entity_id: str):  # noqa: ANN202
    state = hass.states.get(entity_id)
    assert state is not None
    return state


@pytest.mark.req("FR-PLAN-01")
async def test_planned_power_now_and_ahead_is_read(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    set_plan(hass, 2.0, hours=6)
    await setup_entry()
    planned = _state(hass, "sensor.climate_control_planned_power")
    assert float(planned.state) == 2000
    assert len(planned.attributes["forecast"]) == 6
    assert planned.attributes["forecast"][1]["value"] == 2000
    assert _state(hass, "binary_sensor.climate_control_running").state == "on"


@pytest.mark.req("FR-SRC-01")
async def test_only_the_device_temperature_counts(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    hass.states.async_set("sensor.room_a_temperature", "10")
    await setup_entry()
    soc = _state(hass, "sensor.climate_control_state_of_charge")
    assert float(soc.state) == pytest.approx(33.33)  # 20 degC
    units.set(A, "fan_only", 19)
    await run_cycle(hass)
    soc = _state(hass, "sensor.climate_control_state_of_charge")
    assert soc.attributes["worst_room"] == A
    assert float(soc.state) == pytest.approx(30.0)  # median of 33.33 and 26.67


@pytest.mark.req("FR-MODE-01")
async def test_heating_waits_until_cooling_unit_is_neutral(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    units.set(A, "cool", 25, 26)
    set_plan(hass, 2.0)
    await setup_entry()
    assert units.mode(A) == "fan_only"
    assert "heat" not in {units.mode(e) for e in ROOMS}
    await run_cycle(hass)
    assert {units.mode(e) for e in (B, C)} == {"heat"}


@pytest.mark.req("FR-MODE-02")
async def test_setpoint_is_set_again_after_mode_change(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    set_plan(hass, 2.0)
    await setup_entry()
    for entity_id in ROOMS:
        assert units.mode(entity_id) == "heat"
        assert units.target(entity_id) == 21.0  # 20 degC + 1 K offset, not the remembered 18
        own = [c[1] for c in units.calls if c[0] == entity_id]
        assert own == ["set_hvac_mode", "set_temperature"]
    units.calls.clear()
    await run_cycle(hass)
    assert units.calls == []  # nothing changed, nothing sent


@pytest.mark.req("FR-SAFE-01")
async def test_open_window_room_is_not_heated(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    hass.states.async_set("binary_sensor.window_a", "on")
    set_plan(hass, 2.0)
    await setup_entry(a={"window_entity": "binary_sensor.window_a"})
    assert units.mode(A) == "fan_only"
    assert {units.mode(B), units.mode(C)} == {"heat"}
    hass.states.async_set("binary_sensor.window_a", "off")
    await run_cycle(hass)
    assert units.mode(A) == "heat"


@pytest.mark.req("FR-SAFE-02")
async def test_hard_minimum_heats_without_plan(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    units.set(B, "fan_only", 18)
    set_plan(hass, 0)
    await setup_entry()
    assert _state(hass, "binary_sensor.climate_control_running").state == "off"
    assert units.mode(B) == "heat" and units.target(B) == 21.0
    assert units.mode(A) == "fan_only"


@pytest.mark.req("FR-SAFE-03")
async def test_overheated_room_cools_after_one_hour(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,
    freezer: FrozenDateTimeFactory,  # noqa: ANN001
) -> None:
    units.set(C, "fan_only", 24)
    units.set(A, "fan_only", 21)
    units.set(B, "fan_only", 21)
    set_plan(hass, 0)
    await setup_entry()
    assert units.mode(C) == "fan_only"
    for _ in range(4):
        freezer.tick(timedelta(minutes=15))
        set_plan(hass, 0)
        await run_cycle(hass)
    assert units.mode(C) == "cool" and units.target(C) == 21.0


@pytest.mark.req("FR-SAFE-03")
async def test_no_cooling_while_heating(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,
    freezer: FrozenDateTimeFactory,  # noqa: ANN001
) -> None:
    units.set(C, "fan_only", 24)
    units.set(A, "fan_only", 18)
    set_plan(hass, 0)
    await setup_entry({"overheat_s": 0})
    assert units.mode(A) == "heat" and units.mode(C) == "fan_only"


@pytest.mark.req("FR-SAFE-04")
async def test_planner_unavailable_falls_back(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, None)
    await setup_entry()
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "on"
    for entity_id in ROOMS:
        assert units.mode(entity_id) == "heat" and units.target(entity_id) == 21.0


@pytest.mark.req("FR-SAFE-04")
async def test_stale_plan_falls_back(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,
    freezer: FrozenDateTimeFactory,  # noqa: ANN001
) -> None:
    set_plan(hass, 0)
    await setup_entry()
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "off"
    freezer.tick(timedelta(minutes=31))
    await run_cycle(hass)
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "on"
    assert {units.mode(e) for e in ROOMS} == {"heat"}


@pytest.mark.req("FR-PLNR-01")
async def test_planner_model_values_are_published(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    await setup_entry()
    values = {
        key: _state(hass, f"sensor.climate_control_{key}")
        for key in (
            "capacity",
            "min_charge",
            "undercharge",
            "max_charge",
            "overcharge",
            "undercharge_cost",
            "overcharge_cost",
            "efficiency",
            "max_discharge_power",
            "max_charge_power",
            "stage_1_power",
            "stage_2_power",
            "stage_2_surcharge",
            "charge_cost",
        )
    }
    assert float(values["capacity"].state) == 52.5
    assert float(values["efficiency"].state) == 92.0
    assert float(values["max_discharge_power"].state) == 3.5
    assert float(values["min_charge"].state) <= 40.0
    assert len(values["min_charge"].attributes["forecast"]) == 24
    assert values["undercharge_cost"].attributes["unit_of_measurement"].endswith("/kWh")
    fc = values["charge_cost"].attributes["forecast"]
    assert fc[0]["value"] > fc[-1]["value"] == 0


@pytest.mark.req("FR-PLAN-01")
async def test_two_power_stages_are_summed(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, 1.5)
    hass.states.async_set("sensor.stage2", "0.3", {"unit_of_measurement": "kW"})
    entry = await setup_entry()
    hass.config_entries.async_update_entry(entry, data={**entry.data, "plan_entity": [PLAN, "sensor.stage2"]})
    await hass.async_block_till_done()
    assert float(_state(hass, "sensor.climate_control_planned_power").state) == 1800
    hass.states.async_set("sensor.stage2", "unavailable")
    await run_cycle(hass)
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "on"


@pytest.mark.req("FR-GEN-01")
async def test_setpoint_can_come_from_an_entity(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    hass.states.async_set("input_number.setpoint_a", "23.5")
    set_plan(hass, None)  # fallback: every unit heats to its current setpoint
    await setup_entry(a={"setpoint_entity": "input_number.setpoint_a"})
    assert units.target(A) == 23.5 and units.target(B) == 21.0
    hass.states.async_set("input_number.setpoint_a", "22")
    await run_cycle(hass)
    assert units.target(A) == 22.0
    min_charge = float(_state(hass, "sensor.climate_control_min_charge").state)
    hass.states.async_set("input_number.setpoint_a", "unavailable")
    await run_cycle(hass)
    assert units.target(A) == 21.0  # fixed setpoint as substitute
    assert float(_state(hass, "sensor.climate_control_min_charge").state) < min_charge
