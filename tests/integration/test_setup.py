"""Integration level: configuration through the HA test harness (no real instance)."""

from typing import Any

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import DOMAIN

from .fakes import INSTALLATION, PLAN, ROOMS, FakeUnits, room_data, run_cycle, set_plan

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
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], room_data(entity_id, **overrides)
    )
    await hass.async_block_till_done()
    return result


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
        result = await _add_room(
            hass, entry, entity_id, setpoint_c=20 + i, power_class="small" if i else "big"
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
    assert [s.unique_id for s in entry.subentries.values()] == list(ROOMS)
    cfg = entry.runtime_data.cfg
    assert [r.setpoint_c for r in cfg.rooms] == [20, 21, 22]
    assert cfg.class_order == ("big", "small")
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
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], changed)
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
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    keys = {str(k) for k in result["data_schema"].schema}
    assert {"start_ratio", "tie_band_k", "overheat_s", "night_setback_k", "neutral_mode", "cycle_s"} <= keys
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tie_band_k": 0.5, "neutral_mode": "off", "comfort_max_c": 29.5}
    )
    assert result["type"] == FlowResultType.FORM and result["errors"] == {"base": "invalid_parameters"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tie_band_k": 0.5, "neutral_mode": "off"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.cfg.params.tie_band_k == 0.5
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
    result = await hass.config_entries.options.async_init(entry.entry_id)
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
        await hass.config_entries.options.async_init(entry.entry_id),
        await hass.config_entries.subentries.async_init((entry.entry_id, "room"), context={"source": "user"}),
        await entry.start_reconfigure_flow(hass),
    ):
        assert _sections(form) and set(_sections(form).values()) == {(False, True)}

    sub = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "room"), context={"source": "user"}
    )
    units.set("climate.e", "fan_only", 20)
    await hass.config_entries.subentries.async_configure(
        sub["flow_id"], {**room_data("climate.e"), "help_setpoint_c": {"help_expanded": False}}
    )
    await hass.async_block_till_done()
    form = await hass.config_entries.options.async_init(entry.entry_id)
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
    assert hass.states.get("sensor.klima_capacity").state == "105.0"  # type: ignore[union-attr]
    assert hass.states.get("binary_sensor.klima_fallback").state == "off"  # type: ignore[union-attr]

    set_plan(hass, 0)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert units.mode(ROOMS[0]) == "heat"  # now controlled: hard minimum protection
