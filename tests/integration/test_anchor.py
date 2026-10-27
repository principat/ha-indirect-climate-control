"""Integration level: display offset and remembered values (FR-SOC-03 to FR-SOC-05)."""

from __future__ import annotations

from typing import Any

import probatio as vol
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.climate_control.const import (
    DOMAIN,
    SERVICE_SET_DISPLAY_OFFSET,
    SERVICE_SET_LARGEST_DEVIATION,
)

from .fakes import ROOMS, FakeUnits, run_cycle, set_plan


def _state(hass: HomeAssistant, entry_id: str, key: str) -> Any:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry_id}_{key}")
    assert entity_id, key
    return hass.states.get(entity_id)


@pytest.mark.req("FR-SOC-04")
async def test_the_display_offset_and_the_largest_deviation_are_diagnostic_values(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    registry = er.async_get(hass)
    for key in ("display_offset", "largest_deviation"):
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
        assert entity_id and registry.async_get(entity_id).entity_category == er.EntityCategory.DIAGNOSTIC
    assert float(_state(hass, entry.entry_id, "display_offset").state) == 3.5  # the start value
    assert _state(hass, entry.entry_id, "largest_deviation").state == "unknown"  # not measured yet


@pytest.mark.req("FR-SOC-04")
async def test_the_start_value_and_the_adaptation_limits_are_options_of_the_plant(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry(options={"display_offset_k": 4.0})
    assert float(_state(hass, entry.entry_id, "display_offset").state) == 4.0
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(menu["flow_id"], {"next_step_id": "soc"})
    schema = {str(m): (m, v) for m, v in form["data_schema"].schema.items()}
    assert schema["display_offset_k"][0].default() == 4.0
    assert schema["offset_threshold_pct"][0].default() == 10.0
    assert schema["offset_target_pct"][0].default() == 5.0
    assert schema["offset_cap_factor"][0].default() == 1.25
    assert {"help_display_offset_k", "help_offset_cap_factor"} <= set(schema)
    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], {"display_offset_k": 3.0, "offset_target_pct": 20.0}
    )
    assert saved["type"] == FlowResultType.FORM and saved["errors"] == {"base": "invalid_parameters"}


@pytest.mark.req("FR-SOC-05")
async def test_the_values_can_be_set_by_hand_and_survive_a_restart(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    await hass.services.async_call(DOMAIN, SERVICE_SET_DISPLAY_OFFSET, {"value": 4.25}, blocking=True)
    await hass.services.async_call(DOMAIN, SERVICE_SET_LARGEST_DEVIATION, {"value": 3.5}, blocking=True)
    await hass.async_block_till_done()
    assert float(_state(hass, entry.entry_id, "display_offset").state) == 4.25
    assert float(_state(hass, entry.entry_id, "largest_deviation").state) == 3.5
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    anchor = entry.runtime_data.controller.anchor
    assert (anchor.offset, anchor.largest) == (4.25, 3.5)  # kept over the restart
    await run_cycle(hass)
    assert float(_state(hass, entry.entry_id, "display_offset").state) == 4.25
    await hass.services.async_call(DOMAIN, SERVICE_SET_LARGEST_DEVIATION, {}, blocking=True)  # empty
    await hass.async_block_till_done()
    assert entry.runtime_data.controller.anchor.largest is None
    assert _state(hass, entry.entry_id, "largest_deviation").state == "unknown"


@pytest.mark.req("FR-SOC-05")
async def test_a_negative_value_is_refused_and_the_service_can_address_one_installation(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 0)
    entry = await setup_entry()
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, SERVICE_SET_DISPLAY_OFFSET, {"value": -1}, blocking=True)
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_DISPLAY_OFFSET, {"value": 2.0, "config_entry_id": "other"}, blocking=True
    )
    assert entry.runtime_data.controller.anchor.offset == 3.5  # another installation: not this one
    await hass.services.async_call(
        DOMAIN, SERVICE_SET_DISPLAY_OFFSET, {"value": 2.0, "config_entry_id": entry.entry_id}, blocking=True
    )
    assert entry.runtime_data.controller.anchor.offset == 2.0


@pytest.mark.req("FR-SOC-03")
async def test_the_published_soc_is_built_from_the_remembered_temperatures(
    hass: HomeAssistant, units: FakeUnits, setup_entry: Any
) -> None:
    set_plan(hass, 2.0)
    entry = await setup_entry(options={"soc_smoothing_s": 0.0})
    await run_cycle(hass)  # a unit works now: the work period starts with the readings of 20
    soc_idle = entry.runtime_data.data.result.soc_pct
    for entity_id in ROOMS:
        units.set(entity_id, "heat", 23.0)  # 3 K more than at the start: not beyond the display offset
    await run_cycle(hass)
    assert entry.runtime_data.data.result.soc_pct == soc_idle
    for entity_id in ROOMS:
        units.set(entity_id, "heat", 24.5)  # beyond: the remembered values follow with the offset
    await run_cycle(hass)
    assert entry.runtime_data.data.result.soc_pct > soc_idle
