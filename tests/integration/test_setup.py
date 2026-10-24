"""Integration level: configuration through the HA test harness (no real instance)."""

from dataclasses import fields
from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import DOMAIN
from custom_components.climate_control.core.config import Parameters

from .fakes import INSTALLATION, PLAN, ROOMS, FakeUnits, room_data, run_cycle, set_plan, submit_room

USER_INPUT = {"name": "Klima", **INSTALLATION}


async def _create_installation(hass: HomeAssistant, name: str = "Klima") -> MockConfigEntry:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**USER_INPUT, "name": name})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]  # type: ignore[no-any-return]


async def _add_room(hass: HomeAssistant, entry: MockConfigEntry, entity_id: str, **overrides: Any) -> Any:
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "user"
    result = await submit_room(hass, result["flow_id"], room_data(entity_id, **overrides))
    await hass.async_block_till_done()
    return result


async def _open_group(hass: HomeAssistant, entry: MockConfigEntry, group: str) -> Any:
    """Options open a menu of parameter groups; open one group form."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    return await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": group})


def _sections(result: Any) -> dict[str, Any]:
    """Help sections of a form: key -> (collapsed, default of the helper switch)."""
    out = {}
    for marker, value in result["data_schema"].schema.items():
        if str(marker).startswith("help_"):
            inner = next(iter(value.schema.schema))
            out[str(marker)] = (value.options["collapsed"], inner.default())
    return out


@pytest.mark.req("FR-GEN-01")
@pytest.mark.req("FR-CFG-01")
async def test_installation_first_then_indoor_units_one_by_one(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 2.0)
    entry = await _create_installation(hass)
    assert entry.title == "Klima" and entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.klima_state_of_charge").state == "unavailable"  # type: ignore[union-attr]
    for i, entity_id in enumerate(ROOMS):
        result = await _add_room(hass, entry, entity_id, setpoint_c=20 + i, nominal_power_w=500 if i else 900)
        assert result["type"] == FlowResultType.CREATE_ENTRY
    assert [s.unique_id for s in entry.subentries.values()] == list(ROOMS)
    cfg = entry.runtime_data.cfg
    assert [r.setpoint_c for r in cfg.rooms] == [20, 21, 22]
    assert cfg.class_order == (900.0, 500.0)
    assert float(hass.states.get("sensor.klima_state_of_charge").state) > 0  # type: ignore[union-attr]


@pytest.mark.req("FR-CFG-01")
async def test_indoor_unit_cannot_be_added_twice(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _create_installation(hass)
    assert (await _add_room(hass, entry, ROOMS[0]))["type"] == FlowResultType.CREATE_ENTRY
    result = await _add_room(hass, entry, ROOMS[0])
    assert result["type"] == FlowResultType.FORM and result["errors"] == {"entity_id": "already_configured"}


@pytest.mark.req("FR-CFG-01")
async def test_indoor_unit_can_be_changed_and_removed(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    entry = await setup_entry()
    first = next(iter(entry.subentries.values()))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": SOURCE_RECONFIGURE, "subentry_id": first.subentry_id}
    )
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "reconfigure"
    changed = {
        k: v for k, v in room_data(ROOMS[0], setpoint_c=23.0, name="Wohnen").items() if k != "entity_id"
    }
    result = await submit_room(hass, result["flow_id"], changed)
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.runtime_data.cfg.room(ROOMS[0]).setpoint_c == 23.0
    assert entry.runtime_data.cfg.room(ROOMS[0]).name == "Wohnen"

    assert hass.config_entries.async_remove_subentry(entry, first.subentry_id)
    await hass.async_block_till_done()
    assert [r.id for r in entry.runtime_data.cfg.rooms] == list(ROOMS[1:])
    units.calls.clear()
    await run_cycle(hass)
    assert all(call[0] != ROOMS[0] for call in units.calls)


@pytest.mark.req("FR-GEN-01")
async def test_installation_can_be_reconfigured(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    entry = await setup_entry()
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == FlowResultType.FORM and result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "name": "Haus", "p_min_w": 1200}
    )
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.title == "Haus" and entry.runtime_data.cfg.p_min_w == 1200


@pytest.mark.req("FR-GEN-01")
@pytest.mark.parametrize(
    ("override", "error"),
    [({"p_min_w": 4000}, {"base": "pmin_pmax"}), ({"p_max_w": 0}, {"base": "pmin_pmax"})],
)
async def test_config_flow_rejects_inconsistent_installation(
    hass: HomeAssistant, override: dict[str, object], error: dict[str, str]
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**USER_INPUT, **override})
    assert result["type"] == FlowResultType.FORM and result["errors"] == error


@pytest.mark.req("FR-GEN-01")
async def test_all_parameters_are_options(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    entry = await setup_entry()
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"] == FlowResultType.MENU
    assert menu["menu_options"] == ["plan", "sensors", "control", "soc", "safety", "planner"]
    keys: set[str] = set()
    for group in menu["menu_options"][2:]:  # the parameter groups: planner output and sensors are plant data
        form = await _open_group(hass, entry, group)
        keys |= {str(k) for k in form["data_schema"].schema if not str(k).startswith("help_")}
    assert keys == {f.name for f in fields(Parameters)}  # every parameter in a group
    result = await _open_group(hass, entry, "control")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tie_band_k": 0.5, "neutral_mode": "off", "stop_ratio": 0.9}
    )
    assert result["type"] == FlowResultType.FORM and result["errors"] == {"base": "invalid_parameters"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tie_band_k": 0.5, "neutral_mode": "off"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.cfg.params.tie_band_k == 0.5
    assert entry.options["overheat_s"] == 3600.0  # other groups keep their values
    assert all(units.mode(e) == "off" for e in ROOMS)


@pytest.mark.req("FR-GEN-01")
async def test_entry_loads_and_unloads(hass: HomeAssistant, units: FakeUnits, setup_entry) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    entry = await setup_entry()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.climate_control_state_of_charge") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.req("FR-CFG-02")
async def test_several_installations_run_independently(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    set_plan(hass, 0)
    first = await setup_entry(title="Haus")
    units.set("climate.d", "fan_only", 20)
    second = MockConfigEntry(
        domain=DOMAIN,
        title="Werkstatt",
        data={**INSTALLATION, "plan_entity": ["sensor.other_plan"]},
        options={"fallback_delay_s": 0},
        subentries_data=[
            {"data": room_data("climate.d"), "subentry_type": "room", "title": "D", "unique_id": "climate.d"}
        ],
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    assert first.state is second.state is ConfigEntryState.LOADED
    assert hass.states.get("binary_sensor.haus_fallback").state == "off"  # type: ignore[union-attr]
    assert hass.states.get("binary_sensor.werkstatt_fallback").state == "on"  # type: ignore[union-attr]
    assert units.mode("climate.d") == "heat" and units.mode(ROOMS[0]) == "fan_only"
    units.set("climate.d", "fan_only", 20)
    await hass.services.async_call(DOMAIN, "run_cycle", {"config_entry_id": first.entry_id}, blocking=True)
    assert units.mode("climate.d") == "fan_only"  # only the first installation ran
    assert await hass.config_entries.async_unload(second.entry_id)
    assert first.state is ConfigEntryState.LOADED


@pytest.mark.req("FR-CFG-03")
async def test_help_sections_above_complex_fields_follow_the_switch(
    hass: HomeAssistant,
    units: FakeUnits,
    setup_entry,  # noqa: ANN001
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    result = await _open_group(hass, entry, "control")
    keys = [str(k) for k in result["data_schema"].schema]
    assert keys.index("help_tie_band_k") == keys.index("tie_band_k") - 1  # directly above the field
    assert set(_sections(result).values()) == {(True, False)}  # collapsed by default

    controller = entry.runtime_data.controller
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"help_tie_band_k": {"help_expanded": True}}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.controller is controller  # UI setting only, the control is not reloaded

    for form in (
        await _open_group(hass, entry, "control"),
        await hass.config_entries.subentries.async_init((entry.entry_id, "room"), context={"source": "user"}),
        await entry.start_reconfigure_flow(hass),
    ):
        assert _sections(form) and set(_sections(form).values()) == {(False, True)}

    sub = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": "user"}
    )
    units.set("climate.e", "fan_only", 20)
    await submit_room(
        hass, sub["flow_id"], {**room_data("climate.e"), "help_setpoint_source": {"help_expanded": False}}
    )
    await hass.async_block_till_done()
    form = await _open_group(hass, entry, "control")
    assert set(_sections(form).values()) == {(True, False)}


@pytest.mark.req("FR-CFG-03")
async def test_new_installation_stores_help_switch(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert {"help_plan_entity", "help_p_min_w"} <= set(_sections(result))
    assert "help_name" not in _sections(result)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "plan_entity": [PLAN], "help_p_min_w": {"help_expanded": True}}
    )
    assert result["result"].options == {"help_expanded": True}


@pytest.mark.req("FR-GEN-01")
async def test_without_planner_output_nothing_is_controlled(hass: HomeAssistant, units: FakeUnits) -> None:
    """Setup order: the planner output only exists after the planner uses this integration's sensors."""
    units.set(ROOMS[0], "fan_only", 15)  # far below the hard minimum: would heat if controlled
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    installation = {k: v for k, v in USER_INPUT.items() if k != "plan_entity"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], installation)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    await hass.async_block_till_done()
    for entity_id in ROOMS:
        await _add_room(hass, entry, entity_id)
    await run_cycle(hass)
    assert units.calls == []
    assert hass.states.get("sensor.klima_state_of_charge").state != "unavailable"  # type: ignore[union-attr]
    assert hass.states.get("sensor.klima_capacity").state == "45.0"  # type: ignore[union-attr]
    assert hass.states.get("binary_sensor.klima_fallback").state == "off"  # type: ignore[union-attr]

    set_plan(hass, 0)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert units.mode(ROOMS[0]) == "heat"  # now controlled: hard minimum protection


@pytest.mark.req("FR-GEN-01")
async def test_limits_are_set_per_indoor_unit(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = await _create_installation(hass)
    result = await _add_room(
        hass, entry, ROOMS[0], band_up=4.0, limit_up=3.0
    )  # control range beyond the limit
    assert result["type"] == FlowResultType.FORM and result["errors"] == {"base": "room_limits"}
    result = await submit_room(
        hass, result["flow_id"], room_data(ROOMS[0], band_down=1.0, band_up=1.5, limit_down=2.5, limit_up=4.0)
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    room = entry.runtime_data.cfg.room(ROOMS[0])
    assert (room.band_down, room.band_up, room.limit_down, room.limit_up) == (1.0, 1.5, 2.5, 4.0)
    keys = [
        str(k)
        for g in ("control", "soc", "safety", "planner")
        for k in (await _open_group(hass, entry, g))["data_schema"].schema
    ]
    assert not {"overload_max_c", "comfort_max_c", "hard_min_below_k", "soc_min_c", "soc_max_c"} & set(keys)
    assert {"soc_below_k", "soc_above_k"} <= set(keys)


@pytest.mark.req("FR-BAND-01")
async def test_the_band_fields_are_optional_and_default_to_the_standard_values(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    set_plan(hass, 0)
    entry = await _create_installation(hass)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": "user"}
    )
    defaults = {
        str(m): m.default()
        for m in result["data_schema"].schema
        if str(m) in ("band_down", "band_up", "limit_down", "limit_up")
    }
    assert defaults == {"band_down": 2.0, "band_up": 2.0, "limit_down": 3.0, "limit_up": 3.0}
    minimal = {"entity_id": ROOMS[0], "name": "A", "setpoint_c": 21.0, "nominal_power_w": 700, "area_m2": 10}
    result = await submit_room(hass, result["flow_id"], minimal)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    room = entry.runtime_data.cfg.room(ROOMS[0])
    assert (room.band_down, room.band_up, room.limit_down, room.limit_up) == (2.0, 2.0, 3.0, 3.0)


@pytest.mark.req("FR-GEN-01")
async def test_stored_version_1_configuration_is_migrated(hass: HomeAssistant, units: FakeUnits) -> None:
    from homeassistant.helpers import entity_registry as er

    set_plan(hass, 0)
    old_room = {**room_data(ROOMS[0]), "power_class": "standard"}
    own_limits = {**room_data(ROOMS[1]), "comfort_max_c": 22.0, "overload_max_c": 25.0}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Climate Control",
        version=1,
        data={**INSTALLATION, "stage1_w": 1500, "capacity_kwh_per_k": 3.5},
        options={"comfort_max_c": 23.0, "overload_max_c": 27.0, "tie_band_k": 0.5},
        subentries_data=[
            {"data": old_room, "subentry_type": "room", "title": "A", "unique_id": ROOMS[0]},
            {"data": own_limits, "subentry_type": "room", "title": "B", "unique_id": ROOMS[1]},
        ],
    )
    entry.add_to_hass(hass)
    # An entity created by an older version keeps its id, only its display name follows the new naming.
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_min_charge",
        config_entry=entry,
        suggested_object_id="cc_untergrenze",
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 4
    assert "stage1_w" not in entry.data and "capacity_kwh_per_k" not in entry.data
    assert entry.options == {"tie_band_k": 0.5}
    rooms = [dict(s.data) for s in entry.subentries.values()]
    assert "power_class" not in rooms[0]
    # version 4: the fixed temperatures are gone, the standard distances to the setpoint apply
    assert all("comfort_max_c" not in r and "overload_max_c" not in r for r in rooms)
    room = entry.runtime_data.cfg.room(ROOMS[0])
    assert (room.band_down, room.band_up, room.limit_down, room.limit_up) == (2.0, 2.0, 3.0, 3.0)
    assert entry.runtime_data.cfg.capacity_kwh_per_k == 3.0
    state = hass.states.get("sensor.cc_untergrenze")
    assert state is not None and state.attributes["friendly_name"] == "Climate Control Min Charge Level"


@pytest.mark.req("FR-GEN-01")
async def test_planner_output_is_set_under_configure(
    hass: HomeAssistant, units: FakeUnits, setup_entry
) -> None:  # noqa: ANN001
    """The planner output is connected after the planner exists, so it is also part of the options menu."""
    set_plan(hass, 0)
    entry = await setup_entry()
    hass.config_entries.async_update_entry(
        entry, data={k: v for k, v in entry.data.items() if k != "plan_entity"}
    )
    await hass.async_block_till_done()
    units.set(ROOMS[0], "fan_only", 15)
    await run_cycle(hass)
    assert units.mode(ROOMS[0]) == "fan_only"  # commissioning: nothing is controlled

    form = await _open_group(hass, entry, "plan")
    assert form["type"] == FlowResultType.FORM and "help_plan_entity" in _sections(form)
    result = await hass.config_entries.options.async_configure(form["flow_id"], {"plan_entity": [PLAN]})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data["plan_entity"] == [PLAN]
    assert units.mode(ROOMS[0]) == "heat"  # controlled now: hard minimum protection

    form = await _open_group(hass, entry, "plan")
    result = await hass.config_entries.options.async_configure(form["flow_id"], {})
    await hass.async_block_till_done()
    assert "plan_entity" not in entry.data  # cleared again: back to commissioning


async def _reconfigure_room(hass: HomeAssistant, entry: MockConfigEntry, entity_id: str) -> Any:
    subentry = next(s for s in entry.subentries.values() if s.unique_id == entity_id)
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": SOURCE_RECONFIGURE, "subentry_id": subentry.subentry_id}
    )


def _suggested(form: Any, field: str) -> Any:
    marker = next(m for m in form["data_schema"].schema if str(m) == field)
    return marker.description["suggested_value"]


@pytest.mark.req("FR-SAFE-01")
async def test_window_contacts_can_be_edited_when_stored_as_single_id(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    """Entries before 0.3 stored one contact as text; the multi-select needs a list to stay editable."""
    set_plan(hass, 0)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Klima",
        version=3,  # already current: the form itself must cope with a stored single id
        data={**INSTALLATION},
        subentries_data=[
            {
                "data": room_data(ROOMS[0], window_entity="binary_sensor.fs_terrassentur_contact"),
                "subentry_type": "room",
                "title": "A",
                "unique_id": ROOMS[0],
            }
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    form = await _reconfigure_room(hass, entry, ROOMS[0])
    assert _suggested(form, "window_entity") == ["binary_sensor.fs_terrassentur_contact"]

    changed = {k: v for k, v in room_data(ROOMS[0]).items() if k != "entity_id"}
    changed["window_entity"] = ["binary_sensor.fs_terrassentur_contact", "binary_sensor.fs_couch_contact"]
    result = await submit_room(hass, form["flow_id"], changed)
    assert result["reason"] == "reconfigure_successful"
    stored = next(iter(entry.subentries.values())).data["window_entity"]
    assert stored == ["binary_sensor.fs_terrassentur_contact", "binary_sensor.fs_couch_contact"]


@pytest.mark.req("FR-SAFE-01")
async def test_single_window_contact_is_migrated_to_a_list(hass: HomeAssistant, units: FakeUnits) -> None:
    set_plan(hass, 0)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Klima",
        version=2,
        data={**INSTALLATION},
        subentries_data=[
            {
                "data": room_data(ROOMS[0], window_entity="binary_sensor.fs_terrassentur_contact"),
                "subentry_type": "room",
                "title": "A",
                "unique_id": ROOMS[0],
            },
            {"data": room_data(ROOMS[1]), "subentry_type": "room", "title": "B", "unique_id": ROOMS[1]},
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 4
    rooms = [dict(s.data) for s in entry.subentries.values()]
    assert rooms[0]["window_entity"] == ["binary_sensor.fs_terrassentur_contact"]
    assert "window_entity" not in rooms[1]


@pytest.mark.req("FR-GEN-01")
async def test_outdoor_power_sensor_is_mandatory(hass: HomeAssistant) -> None:
    from homeassistant.data_entry_flow import InvalidData

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert "help_outdoor_power_entity" in _sections(result)
    without = {k: v for k, v in USER_INPUT.items() if k != "outdoor_power_entity"}
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(result["flow_id"], without)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].data["outdoor_power_entity"] == "sensor.outdoor_power"


@pytest.mark.req("FR-GEN-01")
async def test_entry_without_outdoor_power_sensor_gets_a_repair_until_it_is_set(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    from homeassistant.helpers import issue_registry as ir

    set_plan(hass, 0)
    data = {k: v for k, v in INSTALLATION.items() if k != "outdoor_power_entity"}  # entry from before 0.6
    entry = MockConfigEntry(domain=DOMAIN, title="Klima", version=3, data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, f"outdoor_power_missing_{entry.entry_id}")
    assert issue is not None and issue.translation_key == "outdoor_power_missing"
    assert entry.state is ConfigEntryState.LOADED  # the control keeps working meanwhile

    form = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(form["flow_id"], {**USER_INPUT})
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, f"outdoor_power_missing_{entry.entry_id}") is None


@pytest.mark.req("FR-CFG-01")
async def test_an_indoor_unit_added_while_the_entry_is_being_set_up_is_not_lost(
    hass: HomeAssistant, units: FakeUnits, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The change lands between building the control and finishing the setup: it must still reload."""
    from homeassistant.config_entries import ConfigSubentry

    from custom_components.climate_control.coordinator import ClimateControlCoordinator

    set_plan(hass, 0)
    units.set("climate.extra", "fan_only", 20)
    entry = MockConfigEntry(domain=DOMAIN, title="Klima", version=3, data=dict(INSTALLATION))
    entry.add_to_hass(hass)
    original = ClimateControlCoordinator.async_load_learned

    async def load_and_add(self: ClimateControlCoordinator) -> None:
        await original(self)
        if entry.subentries:  # the reload sees the unit already
            return
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=room_data("climate.extra"),
                subentry_type="room",
                title="Extra",
                unique_id="climate.extra",
            ),
        )

    monkeypatch.setattr(ClimateControlCoordinator, "async_load_learned", load_and_add)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    monkeypatch.undo()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.cfg is not None
    assert [r.id for r in entry.runtime_data.cfg.rooms] == ["climate.extra"]  # reloaded with the new unit


@pytest.mark.req("FR-GEN-01")
async def test_outdoor_power_and_cooling_switch_are_set_under_configure(
    hass: HomeAssistant, units: FakeUnits
) -> None:
    """Both can be changed in the options as well, without going through the reconfiguration."""
    from homeassistant.helpers import issue_registry as ir

    set_plan(hass, 0)
    data = {k: v for k, v in INSTALLATION.items() if k != "outdoor_power_entity"}  # entry from before 0.6
    entry = MockConfigEntry(domain=DOMAIN, title="Klima", version=4, data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"outdoor_power_missing_{entry.entry_id}") is not None

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert "sensors" in menu["menu_options"]
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "sensors"})
    assert form["type"] == FlowResultType.FORM and form["step_id"] == "sensors"
    assert {"help_outdoor_power_entity", "help_season_entity"} <= set(_sections(form))
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {"outdoor_power_entity": "sensor.outdoor_power", "season_entity": "input_boolean.cooling"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data["outdoor_power_entity"] == "sensor.outdoor_power"
    assert entry.data["season_entity"] == "input_boolean.cooling"
    assert entry.state is ConfigEntryState.LOADED  # reloaded with the new values
    assert (
        registry.async_get_issue(DOMAIN, f"outdoor_power_missing_{entry.entry_id}") is None
    )  # the repair is gone

    form = await _open_group(hass, entry, "sensors")  # the stored values are shown again
    defaults = {str(m): m.description["suggested_value"] for m in form["data_schema"].schema if m.description}
    assert defaults == {
        "outdoor_power_entity": "sensor.outdoor_power",
        "season_entity": "input_boolean.cooling",
    }
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"outdoor_power_entity": "sensor.outdoor_power"}
    )
    await hass.async_block_till_done()
    assert "season_entity" not in entry.data  # emptied: no switch, the plant heats
    assert entry.data["outdoor_power_entity"] == "sensor.outdoor_power"


@pytest.mark.req("FR-GEN-01")
async def test_reconfiguring_reloads_the_entry_once_and_without_a_deprecation_warning(
    hass: HomeAssistant, units: FakeUnits, caplog: pytest.LogCaptureFixture
) -> None:
    from unittest.mock import patch

    import custom_components.climate_control as integration

    set_plan(hass, 0)
    entry = MockConfigEntry(domain=DOMAIN, title="Klima", version=4, data=dict(INSTALLATION))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    with patch.object(integration, "async_setup_entry", wraps=integration.async_setup_entry) as setup:
        form = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {**USER_INPUT, "p_max_w": 3000}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert entry.data["p_max_w"] == 3000
    assert setup.call_count == 1  # reloaded by the update listener only
    assert "should use it for scheduling a reload" not in caplog.text
