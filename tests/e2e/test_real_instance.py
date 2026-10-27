"""e2e: checks against a real Home Assistant instance with the simulated reference case (NF-CFG-01)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import aiohttp
import pytest
import requests
import yaml

DOMAIN = "climate_control"
SIM = "climate_control_sim"
PLAN = "sensor.sim_planner_power"
SWITCH = "input_boolean.sim_cooling"
REFERENCE = yaml.safe_load(Path("config/reference-case.yaml").read_text(encoding="utf-8"))
UNITS = [r["indoor_unit"] for r in REFERENCE["rooms"]]
SETPOINT = 21.0  # reference case has no setpoints yet (TODO in config/)


def _url(ha: requests.Session, path: str) -> str:
    return f"{ha.base_url}{path}"  # type: ignore[attr-defined]


def _post(ha: requests.Session, path: str, payload: dict[str, Any] | None = None) -> Any:
    r = ha.post(_url(ha, path), json=payload or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def _state(ha: requests.Session, entity_id: str) -> dict[str, Any]:
    r = ha.get(_url(ha, f"/api/states/{entity_id}"), timeout=30)
    r.raise_for_status()
    return dict(r.json())


def _service(ha: requests.Session, domain: str, service: str, **data: Any) -> None:
    _post(ha, f"/api/services/{domain}/{service}", data)


def _cycle(ha: requests.Session) -> None:
    _service(ha, DOMAIN, "run_cycle")


@pytest.fixture(scope="module")
def entry(ha: requests.Session) -> dict[str, Any]:
    """Configure the integration for the reference case through the real config flow."""
    for old in ha.get(_url(ha, "/api/config/config_entries/entry"), timeout=30).json():
        if old["domain"] == DOMAIN:
            ha.delete(_url(ha, f"/api/config/config_entries/entry/{old['entry_id']}"), timeout=30)
    _service(ha, SIM, "reset")
    _service(ha, SIM, "set_plan", power_kw=0)
    inst = REFERENCE["installation"]
    flow = _post(ha, "/api/config/config_entries/flow", {"handler": DOMAIN})
    assert flow["type"] == "form" and flow["step_id"] == "user"
    flow = _post(
        ha,
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {
            "name": "Climate Control",
            "plan_entity": [PLAN],
            "p_min_w": inst["pmin_w"],
            "p_max_w": inst["pmax_w"],
            "outdoor_power_entity": inst["outdoor_power_sensor"],
            "season_entity": SWITCH,
        },
    )
    assert flow["type"] == "create_entry", flow
    result = dict(flow["result"])
    for room in REFERENCE["rooms"]:
        _add_room(ha, result["entry_id"], room)
    # The minimum run time is covered on unit and integration level; here a started plant would still run
    # when the next test starts and mask what that test looks at.
    _set_option(ha, result["entry_id"], "control", "min_run_s", 0)
    # Likewise the frozen device temperatures: a running unit would freeze the readings the next test sets.
    _set_option(ha, result["entry_id"], "control", "settle_s", 0)
    return result


def _room_input(room: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": room["id"],
        "setpoint_c": SETPOINT,
        "nominal_power_w": 500,
        "area_m2": room["area_m2"],
    }


def _submit_room(ha: requests.Session, flow: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """FR-CFG-04: the form with the choice of the setpoint source, then the setpoint itself."""
    form = {k: v for k, v in values.items() if k != "setpoint_c"}
    url = f"/api/config/config_entries/subentries/flow/{flow['flow_id']}"
    flow = _post(ha, url, {**form, "setpoint_source": "constant"})
    assert flow["type"] == "form" and flow["step_id"] == "setpoint_constant", flow
    return _post(
        ha,
        f"/api/config/config_entries/subentries/flow/{flow['flow_id']}",
        {"setpoint_c": values["setpoint_c"]},
    )


def _add_room(ha: requests.Session, entry_id: str, room: dict[str, Any]) -> None:
    """FR-CFG-01: one indoor unit at a time."""
    flow = _post(ha, "/api/config/config_entries/subentries/flow", {"handler": [entry_id, "room"]})
    assert flow["type"] == "form" and flow["step_id"] == "user", flow
    flow = _submit_room(ha, flow, {"entity_id": room["indoor_unit"], **_room_input(room)})
    assert flow["type"] == "create_entry", flow


def _ws(ha: requests.Session, message: dict[str, Any]) -> Any:
    """One websocket command (subentry list/delete have no REST endpoint)."""

    async def run() -> Any:
        url = f"{ha.base_url}/api/websocket".replace("http", "ws", 1)  # type: ignore[attr-defined]
        token = ha.headers["Authorization"].split(" ", 1)[1]
        async with aiohttp.ClientSession() as session, session.ws_connect(url) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            assert (await ws.receive_json())["type"] == "auth_ok"
            await ws.send_json({"id": 1, **message})
            reply = await ws.receive_json()
            assert reply["success"], reply
            return reply["result"]

    return asyncio.run(run())


@pytest.fixture
def sim(ha: requests.Session, entry: dict[str, Any]) -> requests.Session:
    """Fresh simulated devices (all fan, 20 degC) and a zero plan before each test."""
    _service(ha, SIM, "reset")
    _service(ha, SIM, "set_plan", power_kw=0)
    _cycle(ha)
    return ha


@pytest.mark.req("NF-CFG-01")
def test_instance_configuration_is_valid(ha: requests.Session) -> None:
    result = _post(ha, "/api/config/core/check_config")
    assert result["result"] == "valid", result


@pytest.mark.req("NF-CFG-01")
@pytest.mark.req("FR-GEN-01")
def test_reference_case_loads_with_all_rooms(ha: requests.Session, entry: dict[str, Any]) -> None:
    entries = ha.get(_url(ha, "/api/config/config_entries/entry"), timeout=30).json()
    assert any(e["entry_id"] == entry["entry_id"] and e["state"] == "loaded" for e in entries)
    for entity_id in (
        "sensor.climate_control_state_of_charge",
        "sensor.climate_control_planned_power",
        "sensor.climate_control_min_charge_level",
        "binary_sensor.climate_control_running",
        "binary_sensor.climate_control_fallback",
    ):
        assert _state(ha, entity_id)["state"] not in ("unavailable", "unknown"), entity_id
    assert len(UNITS) == 7


@pytest.mark.req("FR-PLAN-01")
def test_plan_now_and_ahead_is_read(sim: requests.Session) -> None:
    _service(sim, SIM, "set_plan", power_kw=2.0, hours=6)
    _cycle(sim)
    planned = _state(sim, "sensor.climate_control_planned_power")
    assert float(planned["state"]) == 2000
    assert [p["value"] for p in planned["attributes"]["forecast"]] == [2000.0] * 6
    assert _state(sim, "binary_sensor.climate_control_running")["state"] == "on"


@pytest.mark.req("FR-MODE-02")
def test_setpoint_is_set_again_after_switch_to_heat(sim: requests.Session) -> None:
    _service(sim, SIM, "set_plan", power_kw=2.0)
    _cycle(sim)
    heating = [u for u in UNITS if _state(sim, u)["state"] == "heat"]
    assert heating, "plan of 2 kW must start units"
    for unit in heating:
        # The simulated unit restores its remembered 18 degC; the integration sets the room's setpoint again.
        target = _state(sim, unit)["attributes"]["temperature"]
        assert target == SETPOINT


def _wait_loaded(ha: requests.Session, entry_id: str, timeout: float = 60, stable_s: float = 2.0) -> None:
    """Wait until the entry is loaded and stays loaded.

    Every change of the configuration reloads the entry in the background, one after the other. Right after a
    change it still reads `loaded` before the reload begins, so one reading is not enough: it must stay loaded
    for `stable_s` without a reload starting.
    """
    deadline = time.time() + timeout
    loaded_since: float | None = None
    while time.time() < deadline:
        entries = ha.get(_url(ha, "/api/config/config_entries/entry"), timeout=30).json()
        loaded = any(e["entry_id"] == entry_id and e["state"] == "loaded" for e in entries)
        if not loaded:
            loaded_since = None
        elif loaded_since is None:
            loaded_since = time.time()
        elif time.time() - loaded_since >= stable_s:
            return
        time.sleep(0.2)
    raise AssertionError(f"entry {entry_id} did not stay loaded")


def _set_option(ha: requests.Session, entry_id: str, group: str, name: str, value: float) -> None:
    """Change one parameter through the real options dialog (menu -> group form)."""
    flow = _post(ha, "/api/config/config_entries/options/flow", {"handler": entry_id})
    assert flow["type"] == "menu", flow
    flow = _post(ha, f"/api/config/config_entries/options/flow/{flow['flow_id']}", {"next_step_id": group})
    assert flow["type"] == "form", flow
    flow = _post(ha, f"/api/config/config_entries/options/flow/{flow['flow_id']}", {name: value})
    assert flow["type"] == "create_entry", flow
    _wait_loaded(ha, entry_id)  # a changed option reloads the entry in the background


def _wait_then_fall_back(sim: requests.Session, entry: dict[str, Any]) -> None:
    _cycle(sim)
    fallback = _state(sim, "binary_sensor.climate_control_fallback")
    assert fallback["state"] == "off"  # waiting: the units stay as they are
    assert "plan_missing_s" in fallback["attributes"]
    assert {_state(sim, u)["state"] for u in UNITS} == {"fan_only"}
    # The wait cannot be fast-forwarded on a real instance: set it to 0, then back to the default.
    _set_option(sim, entry["entry_id"], "safety", "fallback_delay_s", 0)
    try:
        _cycle(sim)
        assert _state(sim, "binary_sensor.climate_control_fallback")["state"] == "on"
        for unit in UNITS:  # all simulated units have the same nominal power: one group
            state = _state(sim, unit)
            assert state["state"] == "heat" and state["attributes"]["temperature"] == SETPOINT
    finally:
        _set_option(sim, entry["entry_id"], "safety", "fallback_delay_s", 600)


@pytest.mark.req("FR-SAFE-04")
def test_planner_failure_waits_then_falls_back(sim: requests.Session, entry: dict[str, Any]) -> None:
    _service(sim, SIM, "set_plan", power_kw=0, available=False)
    _wait_then_fall_back(sim, entry)


@pytest.mark.req("FR-SAFE-04")
def test_expired_plan_waits_then_falls_back(sim: requests.Session, entry: dict[str, Any]) -> None:
    _service(sim, SIM, "set_plan", power_kw=2.0, hours=2, offset_h=-5)
    _wait_then_fall_back(sim, entry)


@pytest.mark.req("FR-CFG-01")
def test_indoor_units_are_changed_and_removed_one_by_one(ha: requests.Session, entry: dict[str, Any]) -> None:
    entry_id = entry["entry_id"]
    subentries = _ws(ha, {"type": "config_entries/subentries/list", "entry_id": entry_id})
    assert [s["unique_id"] for s in subentries] == UNITS
    last = subentries[-1]
    room = REFERENCE["rooms"][-1]

    flow = _post(
        ha,
        "/api/config/config_entries/subentries/flow",
        {"handler": [entry_id, "room"], "subentry_id": last["subentry_id"]},
    )
    assert flow["step_id"] == "reconfigure", flow
    flow = _submit_room(ha, flow, {**_room_input(room), "name": "Bad neu"})
    assert flow["type"] == "abort" and flow["reason"] == "reconfigure_successful", flow

    _ws(
        ha,
        {
            "type": "config_entries/subentries/delete",
            "entry_id": entry_id,
            "subentry_id": last["subentry_id"],
        },
    )
    remaining = _ws(ha, {"type": "config_entries/subentries/list", "entry_id": entry_id})
    assert [s["unique_id"] for s in remaining] == UNITS[:-1]
    _add_room(ha, entry_id, room)
    titles = [s["title"] for s in _ws(ha, {"type": "config_entries/subentries/list", "entry_id": entry_id})]
    assert titles[-1] == room["id"] and len(titles) == len(UNITS)


@pytest.mark.req("FR-SEAS-01")
def test_the_switch_selects_cooling_and_heating_via_the_neutral_mode(sim: requests.Session) -> None:
    try:
        for reading in (22, 24, 25):  # the plausibility filter takes a step of 2 per cycle at most
            for unit in UNITS:
                _service(sim, SIM, "set_reading", unit=unit.split(".", 1)[1], temperature=reading)
            _cycle(sim)
        _service(sim, SIM, "set_plan", power_kw=2.0)
        _service(sim, "input_boolean", "turn_on", entity_id=SWITCH)
        _cycle(sim)
        cooling = [u for u in UNITS if _state(sim, u)["state"] == "cool"]
        assert cooling and not [u for u in UNITS if _state(sim, u)["state"] == "heat"]
        targets = [_state(sim, unit)["attributes"]["temperature"] for unit in cooling]
        # the served unit gets the setpoint of its room, a room beyond its limit that is not served is
        # cooled to the setpoint as well (protection)
        assert set(targets) == {SETPOINT}
        # The state of charge runs the other way: warm rooms are a low cold store (heating would show 50 %).
        assert float(_state(sim, "sensor.climate_control_state_of_charge")["state"]) < 60.0

        _service(sim, "input_boolean", "turn_off", entity_id=SWITCH)
        for unit in UNITS:
            _service(sim, SIM, "set_reading", unit=unit.split(".", 1)[1], temperature=22)
        _cycle(sim)
        assert {_state(sim, u)["state"] for u in UNITS} == {"fan_only"}  # neutral first
        _cycle(sim)
        assert "heat" in {_state(sim, u)["state"] for u in UNITS}
    finally:
        _service(sim, "input_boolean", "turn_off", entity_id=SWITCH)


@pytest.mark.req("FR-SEAS-02")
def test_cooling_mirrors_the_values_sent_to_the_planner(sim: requests.Session) -> None:
    try:
        _service(sim, "input_boolean", "turn_on", entity_id=SWITCH)
        _cycle(sim)
        # cooling charges downwards: the absolute limit below the setpoint is the overload limit (100 %)
        assert float(_state(sim, "sensor.climate_control_overcharge_percentage")["state"]) == 100.0
        # the learned capacities are diagnostic sensors with their start value
        for key in ("heating", "cooling"):
            assert float(_state(sim, f"sensor.climate_control_learned_capacity_{key}")["state"]) > 0
    finally:
        _service(sim, "input_boolean", "turn_off", entity_id=SWITCH)


@pytest.mark.req("FR-PLNR-02")
@pytest.mark.req("FR-PLNR-03")
def test_learned_capacity_can_be_reset_by_the_service(sim: requests.Session) -> None:
    _service(sim, DOMAIN, "reset_learned_capacity")
    _cycle(sim)
    assert float(_state(sim, "sensor.climate_control_learned_capacity_heating")["state"]) == 3.0
    assert (
        float(_state(sim, "sensor.climate_control_capacity")["state"]) == 15.0
    )  # 3 kWh/K x 4 K of control range / 80 %


@pytest.mark.req("FR-CFG-04")
def test_the_setpoint_is_a_fixed_value_or_an_entity_chosen_in_the_configuration(
    sim: requests.Session, entry: dict[str, Any]
) -> None:
    entry_id = entry["entry_id"]
    first = _ws(sim, {"type": "config_entries/subentries/list", "entry_id": entry_id})[0]
    room = REFERENCE["rooms"][0]
    deviation = f"sensor.{room['id']}_deviation_from_setpoint"
    base = {k: v for k, v in _room_input(room).items() if k != "setpoint_c"}
    assert float(_state(sim, deviation)["state"]) == 1.0  # fixed setpoint 21, device reading 20

    def reconfigure(source: str, value: dict[str, Any]) -> dict[str, Any]:
        flow = _post(
            sim,
            "/api/config/config_entries/subentries/flow",
            {"handler": [entry_id, "room"], "subentry_id": first["subentry_id"]},
        )
        assert flow["step_id"] == "reconfigure", flow
        url = "/api/config/config_entries/subentries/flow/{}"
        nxt = _post(sim, url.format(flow["flow_id"]), {**base, "setpoint_source": source})
        assert nxt["type"] == "form" and nxt["step_id"] == f"setpoint_{source}", (
            nxt
        )  # the value is asked next
        done = _post(sim, url.format(nxt["flow_id"]), value)
        assert done["type"] == "abort" and done["reason"] == "reconfigure_successful", done
        _wait_loaded(sim, entry_id)
        _cycle(sim)
        return done

    try:
        reconfigure("entity", {"setpoint_entity": "input_number.sim_setpoint"})  # the helper stands at 23
        assert float(_state(sim, deviation)["state"]) == 3.0
        _service(sim, "input_number", "set_value", entity_id="input_number.sim_setpoint", value=24)
        _cycle(sim)
        assert float(_state(sim, deviation)["state"]) == 4.0  # the value is read in every cycle
    finally:
        reconfigure("constant", {"setpoint_c": SETPOINT})
    assert float(_state(sim, deviation)["state"]) == 1.0  # a fixed value again, the entity no longer counts
    _service(sim, "input_number", "set_value", entity_id="input_number.sim_setpoint", value=28)
    _cycle(sim)
    assert float(_state(sim, deviation)["state"]) == 1.0
