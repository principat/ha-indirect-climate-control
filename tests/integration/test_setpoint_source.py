"""Integration level: the setpoint of an indoor unit is a fixed value or an entity, never both (FR-CFG-04)."""

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import DOMAIN

from .fakes import INSTALLATION, ROOMS, FakeUnits, room_data, run_cycle, set_plan

A, B, C = ROOMS
SETPOINT = "input_number.setpoint_a"
FORM = {"entity_id": A, "name": "A", "nominal_power_w": 700, "area_m2": 10}


async def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Klima", version=4, data=dict(INSTALLATION))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _start(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": "user"}
    )


def _stored(entry: MockConfigEntry) -> dict[str, Any]:
    return dict(next(iter(entry.subentries.values())).data)


@pytest.mark.req("FR-CFG-04")
async def test_the_first_step_offers_the_choice_and_no_setpoint_field(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    set_plan(hass, 0)
    entry = await _entry(hass)
    form = await _start(hass, entry)
    schema = {str(m): (m, v) for m, v in form["data_schema"].schema.items()}
    assert "setpoint_c" not in schema and "setpoint_entity" not in schema  # one value is asked, not two
    marker, selector = schema["setpoint_source"]
    assert marker.default() == "constant" and selector.config["options"] == ["constant", "entity"]
    assert "help_setpoint_source" in schema


@pytest.mark.req("FR-CFG-04")
async def test_a_fixed_value_stores_only_the_value(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _entry(hass)
    form = await _start(hass, entry)
    step = await hass.config_entries.subentries.async_configure(
        form["flow_id"], {**FORM, "setpoint_source": "constant"}
    )
    assert step["type"] == FlowResultType.FORM and step["step_id"] == "setpoint_constant"
    assert {str(m) for m in step["data_schema"].schema} >= {"setpoint_c", "help_setpoint_c"}
    done = await hass.config_entries.subentries.async_configure(step["flow_id"], {"setpoint_c": 21.5})
    assert done["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    data = _stored(entry)
    assert (
        data["setpoint_c"] == 21.5 and data["setpoint_source"] == "constant" and "setpoint_entity" not in data
    )
    assert entry.runtime_data.cfg.room(A).setpoint_c == 21.5


@pytest.mark.req("FR-CFG-04")
async def test_an_entity_stores_only_the_entity(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _entry(hass)
    form = await _start(hass, entry)
    step = await hass.config_entries.subentries.async_configure(
        form["flow_id"], {**FORM, "setpoint_source": "entity"}
    )
    assert step["type"] == FlowResultType.FORM and step["step_id"] == "setpoint_entity"
    assert {str(m) for m in step["data_schema"].schema} >= {"setpoint_entity", "help_setpoint_entity"}
    done = await hass.config_entries.subentries.async_configure(
        step["flow_id"], {"setpoint_entity": SETPOINT}
    )
    assert done["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    data = _stored(entry)
    assert (
        data["setpoint_entity"] == SETPOINT
        and data["setpoint_source"] == "entity"
        and "setpoint_c" not in data
    )


@pytest.mark.req("FR-CFG-04")
async def test_switching_the_source_drops_the_other_value(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _entry(hass)
    first = await _start(hass, entry)
    step = await hass.config_entries.subentries.async_configure(
        first["flow_id"], {**FORM, "setpoint_source": "constant"}
    )
    await hass.config_entries.subentries.async_configure(step["flow_id"], {"setpoint_c": 21.0})
    await hass.async_block_till_done()
    subentry = next(iter(entry.subentries.values()))

    async def reconfigure(source: str, value: dict[str, Any]) -> None:
        flow = await hass.config_entries.subentries.async_init(
            (entry.entry_id, "room"),
            context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id},
        )
        assert flow["step_id"] == "reconfigure"
        base = {k: v for k, v in FORM.items() if k != "entity_id"}
        nxt = await hass.config_entries.subentries.async_configure(
            flow["flow_id"], {**base, "setpoint_source": source}
        )
        assert nxt["step_id"] == f"setpoint_{'entity' if source == 'entity' else 'constant'}"
        done = await hass.config_entries.subentries.async_configure(nxt["flow_id"], value)
        assert done["type"] == FlowResultType.ABORT and done["reason"] == "reconfigure_successful"
        await hass.async_block_till_done()

    await reconfigure("entity", {"setpoint_entity": SETPOINT})
    data = _stored(entry)
    assert data["setpoint_source"] == "entity" and data["setpoint_entity"] == SETPOINT
    assert "setpoint_c" not in data  # the fixed value is gone
    await reconfigure("constant", {"setpoint_c": 19.5})
    data = _stored(entry)
    assert data["setpoint_source"] == "constant" and data["setpoint_c"] == 19.5
    assert "setpoint_entity" not in data  # the entity is gone


@pytest.mark.req("FR-CFG-04")
async def test_a_room_with_an_entity_is_not_controlled_before_the_first_value_and_keeps_the_last_valid_one(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    set_plan(hass, 0)
    units.set(A, "fan_only", 17)  # 4 below a setpoint of 21: beyond the absolute limit
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Klima",
        version=4,
        data=dict(INSTALLATION),
        options={"heat_offset_k": 0.0},  # FR-OFS-01 off: the test reads the device as it is
        subentries_data=[
            {
                "data": {
                    k: v
                    for k, v in {
                        **room_data(A),
                        "setpoint_source": "entity",
                        "setpoint_entity": SETPOINT,
                    }.items()
                    if k != "setpoint_c"
                },
                "subentry_type": "room",
                "title": "A",
                "unique_id": A,
            }
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert units.mode(A) == "fan_only"  # no valid setpoint yet: the room is left alone, even under the limit
    hass.states.async_set(SETPOINT, "21")
    await run_cycle(hass)
    assert units.mode(A) == "heat" and units.target(A) == 21.0  # now 4 below its setpoint: protected
    hass.states.async_set(SETPOINT, "unavailable")
    await run_cycle(hass)
    assert entry.runtime_data.data.result.temperatures[A] == 17.0
    assert units.mode(A) == "heat"  # the last valid setpoint of 21 still counts


@pytest.mark.req("FR-CFG-04")
async def test_entries_from_before_the_choice_derive_the_source(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    from custom_components.climate_control.data import setpoint_source

    assert setpoint_source({"setpoint_c": 21.0}) == "constant"
    assert setpoint_source({"setpoint_c": 21.0, "setpoint_entity": SETPOINT}) == "entity"
    assert (
        setpoint_source({"setpoint_c": 21.0, "setpoint_entity": SETPOINT, "setpoint_source": "constant"})
        == "constant"
    )
    # an old entry that had both: the entity counts and the stored fixed value is the one to start with
    set_plan(hass, 0)
    hass.states.async_set(SETPOINT, "unavailable")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Klima",
        version=4,
        data=dict(INSTALLATION),
        options={"heat_offset_k": 0.0},  # FR-OFS-01 off: the test reads the device as it is
        subentries_data=[
            {
                "data": room_data(A, setpoint_c=19.0, setpoint_entity=SETPOINT),
                "subentry_type": "room",
                "title": "A",
                "unique_id": A,
            }
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data.result.temperatures[A] == 20.0
    hass.states.async_set(SETPOINT, "23")
    await run_cycle(hass)
    assert (
        float(hass.states.get("sensor.a_deviation_from_setpoint").state) == 3.0
    )  # setpoint 23 against 20 degC
