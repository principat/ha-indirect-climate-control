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
    assert "heat" in {
        units.mode(e) for e in (B, C)
    }  # one room carries the plant, the cooling unit stays neutral
    assert units.mode(A) == "fan_only"


@pytest.mark.req("FR-MODE-02")
async def test_setpoint_is_set_again_after_mode_change(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    set_plan(hass, 2.0)
    await setup_entry()
    heating = [e for e in ROOMS if units.mode(e) == "heat"]
    assert heating == [
        A
    ]  # one room first (equal deviations: the first), the second follows half a rotation later
    assert units.target(A) == 24.0  # the limit of the room (setpoint 21 + 3), not the remembered 18
    own = [c[1] for c in units.calls if c[0] == A]
    assert own == ["set_hvac_mode", "set_temperature"]
    units.calls.clear()
    await run_cycle(hass)
    assert units.calls == []  # nothing changed, nothing sent


@pytest.mark.req("FR-SAFE-01")
async def test_open_window_room_is_not_heated(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
    freezer: FrozenDateTimeFactory,
) -> None:
    hass.states.async_set("binary_sensor.window_a", "on")
    set_plan(hass, 3.3)  # three rooms are wanted: the room with the open window is left out
    await setup_entry(a={"window_entity": "binary_sensor.window_a"})
    assert units.mode(A) == "fan_only"
    assert units.mode(B) == "heat"
    hass.states.async_set("binary_sensor.window_a", "off")
    freezer.tick(timedelta(seconds=61))
    set_plan(hass, 3.3)
    await run_cycle(hass)  # the window is closed: the next lane takes the room with the largest deviation
    assert units.mode(A) == "heat"


@pytest.mark.req("FR-SAFE-02")
async def test_hard_minimum_heats_without_plan(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    units.set(B, "fan_only", 17)  # 4 below the setpoint: beyond the absolute limit of 3
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
    units.set(A, "fan_only", 17)
    set_plan(hass, 0)
    await setup_entry({"overheat_s": 0})
    assert units.mode(A) == "heat" and units.mode(C) == "fan_only"


@pytest.mark.req("FR-SAFE-04")
async def test_planner_unavailable_waits_then_falls_back_step_by_step(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
    freezer: FrozenDateTimeFactory,
) -> None:
    set_plan(hass, None)
    await setup_entry(a={"nominal_power_w": 500}, b={"nominal_power_w": 700}, c={"nominal_power_w": 900})
    fallback = "binary_sensor.climate_control_fallback"
    assert _state(hass, fallback).state == "off"  # waiting: nothing is switched
    assert {units.mode(e) for e in ROOMS} == {"fan_only"} and units.calls == []
    freezer.tick(timedelta(minutes=9))
    await run_cycle(hass)
    assert _state(hass, fallback).state == "off" and units.calls == []
    assert _state(hass, fallback).attributes["plan_missing_s"] == 540

    freezer.tick(timedelta(minutes=1))
    await run_cycle(hass)  # the wait is over: first group
    assert _state(hass, fallback).state == "on"
    assert [units.mode(e) for e in ROOMS] == ["heat", "fan_only", "fan_only"]
    assert units.target(A) == 21.0
    for expected in (["heat", "heat", "fan_only"], ["heat", "heat", "heat"]):
        freezer.tick(timedelta(minutes=2))
        await run_cycle(hass)
        assert [units.mode(e) for e in ROOMS] == expected


@pytest.mark.req("FR-SAFE-04")
async def test_stale_plan_waits_then_falls_back(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
    freezer: FrozenDateTimeFactory,
) -> None:
    set_plan(hass, 0)
    await setup_entry()
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "off"
    freezer.tick(timedelta(minutes=31))
    await run_cycle(hass)  # plan is stale now: the wait starts
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "off"
    assert {units.mode(e) for e in ROOMS} == {"fan_only"}
    freezer.tick(timedelta(minutes=10))
    await run_cycle(hass)
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "on"
    assert {units.mode(e) for e in ROOMS} == {"heat"}  # equal nominal power: one group


@pytest.mark.req("FR-SAFE-04")
async def test_plan_returning_during_the_wait_changes_nothing(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
    freezer: FrozenDateTimeFactory,
) -> None:
    set_plan(hass, None)  # as right after a restart: the planner is not ready yet
    await setup_entry()
    freezer.tick(timedelta(minutes=4))
    set_plan(hass, 0)
    await run_cycle(hass)
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "off"
    assert units.calls == []


@pytest.mark.req("FR-PLNR-01")
async def test_planner_model_values_are_published(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    await setup_entry()
    # Names follow the HAEO 0.4.1 fields they feed (entity ids derive from them on a new installation).
    names = {
        "capacity": "capacity",
        "min_charge": "min_charge_level",
        "undercharge": "undercharge_percentage",
        "max_charge": "max_charge_level",
        "overcharge": "overcharge_percentage",
        "undercharge_cost": "undercharge_cost",
        "overcharge_cost": "overcharge_cost",
        "efficiency": "charge_efficiency",
        "max_discharge_power": "max_discharge_power",
        "max_charge_power": "max_power_source_to_target",
        "charge_cost": "charge_cost",
    }
    values = {key: _state(hass, f"sensor.climate_control_{slug}") for key, slug in names.items()}
    assert values["min_charge"].attributes["friendly_name"] == "Climate Control Min Charge Level"
    assert float(values["capacity"].state) == 45.0  # default 3 kWh/K x 15 K
    assert float(values["efficiency"].state) == 92.0
    assert float(values["max_discharge_power"].state) == 3.5
    assert float(values["min_charge"].state) <= 40.0
    assert len(values["min_charge"].attributes["forecast"]) == 24
    assert values["undercharge_cost"].attributes["unit_of_measurement"].endswith("/kWh")
    fc = values["charge_cost"].attributes["forecast"]
    assert fc[0]["value"] > fc[-1]["value"] == 0


@pytest.mark.req("FR-PLAN-01")
async def test_several_planner_outputs_are_summed(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
    freezer: FrozenDateTimeFactory,
) -> None:
    set_plan(hass, 1.5)
    hass.states.async_set("sensor.stage2", "0.3", {"unit_of_measurement": "kW"})
    entry = await setup_entry()
    hass.config_entries.async_update_entry(entry, data={**entry.data, "plan_entity": [PLAN, "sensor.stage2"]})
    await hass.async_block_till_done()
    assert float(_state(hass, "sensor.climate_control_planned_power").state) == 1800
    hass.states.async_set("sensor.stage2", "unavailable")  # one output fails: the plan is missing as a whole
    await run_cycle(hass)
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "off"  # waiting first
    freezer.tick(timedelta(minutes=10))
    await run_cycle(hass)
    assert _state(hass, "binary_sensor.climate_control_fallback").state == "on"


@pytest.mark.req("FR-GEN-01")
async def test_setpoint_can_come_from_an_entity(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    hass.states.async_set("input_number.setpoint_a", "23.5")
    set_plan(hass, None)  # fallback without waiting: every unit heats to its current setpoint
    await setup_entry({"fallback_delay_s": 0}, a={"setpoint_entity": "input_number.setpoint_a"})
    assert units.target(A) == 23.5  # largest deviation: first step of the fallback
    hass.states.async_set("input_number.setpoint_a", "22")
    await run_cycle(hass)
    assert units.target(A) == 22.0
    min_charge = float(_state(hass, "sensor.climate_control_min_charge_level").state)
    hass.states.async_set("input_number.setpoint_a", "unavailable")
    await run_cycle(hass)
    assert units.target(A) == 22.0  # the entity has no valid value: the last valid one counts
    # the limits follow the setpoint, so the percentage the planner sees does not move with it
    assert float(_state(hass, "sensor.climate_control_min_charge_level").state) == min_charge


@pytest.mark.req("FR-OBS-02")
async def test_diagnostic_sensors_per_indoor_unit(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    units.set(A, "fan_only", 19)
    set_plan(hass, 0)
    entry = await setup_entry()
    ent_reg = er.async_get(hass)
    own = [
        e for e in ent_reg.entities.values() if e.config_entry_id == entry.entry_id and e.config_subentry_id
    ]
    assert len(own) == 5 * len(ROOMS)
    assert {e.entity_category for e in own} == {er.EntityCategory.DIAGNOSTIC}
    first = next(iter(entry.subentries.values()))
    room_entities = {e.translation_key: e.entity_id for e in own if e.config_subentry_id == first.subentry_id}
    device = dr.async_get(hass).async_get(
        next(e for e in own if e.config_subentry_id == first.subentry_id).device_id
    )
    assert device is not None and device.name == "A"
    assert float(_state(hass, room_entities["room_deviation"]).state) == 2.0
    # default capacity 3 kWh/K, three rooms of 10 m2 -> 1 kWh/K per room
    assert float(_state(hass, room_entities["room_heat_demand"]).state) == pytest.approx(1 * 2, abs=0.001)
    assert float(_state(hass, room_entities["room_storage"]).state) == pytest.approx(
        1 * 5, abs=0.001
    )  # up to 3 above the setpoint, 2 below it


@pytest.mark.req("FR-SAFE-01")
async def test_any_of_several_window_contacts_opens_the_room(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
    freezer: FrozenDateTimeFactory,
) -> None:
    hass.states.async_set("binary_sensor.window_a1", "off")
    hass.states.async_set("binary_sensor.window_a2", "on")
    set_plan(hass, 3.3)
    await setup_entry(a={"window_entity": ["binary_sensor.window_a1", "binary_sensor.window_a2"]})
    assert units.mode(A) == "fan_only" and units.mode(B) == "heat"
    hass.states.async_set("binary_sensor.window_a2", "off")
    freezer.tick(timedelta(seconds=61))
    set_plan(hass, 3.3)
    await run_cycle(hass)
    assert units.mode(A) == "heat"


@pytest.mark.req("FR-PLAN-02")
async def test_started_plant_keeps_running_for_the_minimum_run_time(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
    freezer: FrozenDateTimeFactory,
) -> None:
    running = "binary_sensor.climate_control_running"
    set_plan(hass, 2.0)
    await setup_entry()
    assert _state(hass, running).state == "on" and "heat" in {units.mode(e) for e in ROOMS}
    freezer.tick(timedelta(minutes=2))
    set_plan(hass, 0)  # the planner flips to 0, as HAEO does every other update
    await run_cycle(hass)
    assert _state(hass, running).state == "on" and "heat" in {units.mode(e) for e in ROOMS}
    assert float(_state(hass, "sensor.climate_control_requested_power").state) == 1300  # held at Pmin
    freezer.tick(timedelta(minutes=7))
    set_plan(hass, 0)
    await run_cycle(hass)
    assert _state(hass, running).state == "on"  # 9 minutes after the start
    freezer.tick(timedelta(minutes=1))
    set_plan(hass, 0)
    await run_cycle(hass)
    assert _state(hass, running).state == "off" and {units.mode(e) for e in ROOMS} == {"fan_only"}
    set_plan(hass, 2.0)  # no minimum pause: the plant may start again right away
    await run_cycle(hass)
    assert _state(hass, running).state == "on"


@pytest.mark.req("FR-OBS-01")
async def test_operating_data_is_recorded_when_something_changes(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    import json
    from pathlib import Path

    set_plan(hass, 2.0)
    entry = await setup_entry()
    path = Path(hass.config.path("climate_control", f"{entry.entry_id}.jsonl"))
    await hass.async_block_till_done()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["event"] == "plant" and rows[0]["soc_pct"] is not None
    assert {r["unit"] for r in rows if r["event"] == "unit"} == set(ROOMS)  # the starting state of every unit
    heating = [r for r in rows if r["event"] == "unit" and r["mode"] == "heat"]
    assert len({r["unit"] for r in heating}) == 1 and heating[0]["target_c"] == 24.0
    orders = [r for r in rows if r["event"] == "command" and r["mode"] == "heat"]
    assert [r["unit"] for r in orders] == [heating[0]["unit"]] and orders[0]["steps"] == 1
    size = path.stat().st_size
    await run_cycle(hass)  # nothing changed: nothing recorded
    assert path.stat().st_size == size
    hass.states.async_set("sensor.outdoor_power", "1210.5", {"unit_of_measurement": "W"})
    await run_cycle(hass)  # the outdoor power moved: it is recorded with its value
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    power = [r for r in rows if r["event"] == "power"]
    assert power and power[-1]["power_w"] > 0
    size = path.stat().st_size
    units.set(A, "heat", 20.5, units.target(A))  # the device temperature of one unit moved (one step)
    await run_cycle(hass)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["unit"] == A and rows[-1]["temperature_c"] == 20.5
    grown = path.stat().st_size
    assert grown > size
    await run_cycle(hass)
    assert path.stat().st_size == grown
