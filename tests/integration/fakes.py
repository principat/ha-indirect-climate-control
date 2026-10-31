"""Fake indoor units and a fake planner output for integration tests."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from custom_components.climate_control.const import DOMAIN, SERVICE_RUN_CYCLE

PLAN = "sensor.planner_power"
ROOMS = ("climate.a", "climate.b", "climate.c")
REMEMBERED = {"heat": 18.0, "cool": 26.0}


class FakeUnits:
    """Indoor units that behave like the reference devices: remembered setpoint per mode,
    no setpoint in fan/dry, whole-degree readings. Records every service call in order."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.calls: list[tuple[str, str, Any]] = []
        hass.services.async_register("climate", "set_hvac_mode", self._set_mode)
        hass.services.async_register("climate", "set_temperature", self._set_temp)
        hass.services.async_register("climate", "set_fan_mode", self._set_fan)

    def set(
        self,
        entity_id: str,
        mode: str,
        temperature: float,
        target: float | None = None,
        fan: str | None = None,
    ) -> None:
        attrs = {"current_temperature": temperature, "temperature": target, "friendly_name": entity_id}
        if fan is not None:
            attrs["fan_mode"] = fan
        self.hass.states.async_set(entity_id, mode, attrs)

    def fan(self, entity_id: str) -> str | None:
        return self.hass.states.get(entity_id).attributes.get("fan_mode")  # type: ignore[union-attr]

    def mode(self, entity_id: str) -> str:
        return self.hass.states.get(entity_id).state  # type: ignore[union-attr]

    def target(self, entity_id: str) -> float | None:
        return self.hass.states.get(entity_id).attributes.get("temperature")  # type: ignore[union-attr]

    async def _set_mode(self, call: ServiceCall) -> None:
        for entity_id in _ids(call):
            mode = call.data["hvac_mode"]
            self.calls.append((entity_id, "set_hvac_mode", mode))
            old = self.hass.states.get(entity_id)
            assert old is not None
            attrs = old.attributes
            self.set(
                entity_id, mode, attrs["current_temperature"], REMEMBERED.get(mode), attrs.get("fan_mode")
            )

    async def _set_temp(self, call: ServiceCall) -> None:
        for entity_id in _ids(call):
            self.calls.append((entity_id, "set_temperature", call.data["temperature"]))
            old = self.hass.states.get(entity_id)
            assert old is not None
            self.hass.states.async_set(
                entity_id, old.state, {**old.attributes, "temperature": call.data["temperature"]}
            )

    async def _set_fan(self, call: ServiceCall) -> None:
        for entity_id in _ids(call):
            self.calls.append((entity_id, "set_fan_mode", call.data["fan_mode"]))
            old = self.hass.states.get(entity_id)
            assert old is not None
            attrs = {**old.attributes, "fan_mode": call.data["fan_mode"]}
            self.hass.states.async_set(entity_id, old.state, attrs)


def _ids(call: ServiceCall) -> list[str]:
    ids = call.data["entity_id"]
    return [ids] if isinstance(ids, str) else list(ids)


async def submit_room(hass: HomeAssistant, flow_id: str, values: dict[str, Any]) -> Any:
    """Submit a room like the user does: the form with the setpoint source, then the setpoint itself."""
    form = {k: v for k, v in values.items() if k not in ("setpoint_c", "setpoint_entity")}
    source = "entity" if values.get("setpoint_entity") else "constant"
    result = await hass.config_entries.subentries.async_configure(
        flow_id, {**form, "setpoint_source": source}
    )
    if result["type"] == "form" and result["step_id"] in ("setpoint_constant", "setpoint_entity"):
        value = (
            {"setpoint_entity": values["setpoint_entity"]}
            if source == "entity"
            else {"setpoint_c": values["setpoint_c"]}
        )
        result = await hass.config_entries.subentries.async_configure(result["flow_id"], value)
    return result


def set_plan(hass: HomeAssistant, kw: float | None, hours: int = 6) -> None:
    """Planner output in kW with an hourly forecast; None = planner unavailable."""
    if kw is None:
        hass.states.async_set(PLAN, "unavailable")
        return
    now = dt_util.utcnow()
    start = now.replace(minute=0, second=0, microsecond=0)
    forecast = [{"time": (start + timedelta(hours=i)).isoformat(), "value": kw} for i in range(hours)]
    hass.states.async_set(
        PLAN, str(kw), {"unit_of_measurement": "kW", "forecast": forecast, "stamp": now.isoformat()}
    )


async def run_cycle(hass: HomeAssistant) -> None:
    await hass.services.async_call(DOMAIN, SERVICE_RUN_CYCLE, blocking=True)
    await hass.async_block_till_done()


INSTALLATION = {
    "plan_entity": [PLAN],
    "outdoor_power_entity": "sensor.outdoor_power",
    "p_min_w": 1300,
    "p_max_w": 3300,
}


def room_data(entity_id: str, **overrides: Any) -> dict[str, Any]:
    room = {
        "entity_id": entity_id,
        "name": entity_id.split(".")[1].upper(),
        "setpoint_c": 21.0,
        "nominal_power_w": 700,
        "area_m2": 10,
    }
    room.update(overrides)
    return room


def room_subentries(**room_overrides: dict[str, Any]) -> list[ConfigSubentryData]:
    subentries = []
    for entity_id in ROOMS:
        data = room_data(entity_id, **room_overrides.get(entity_id.split(".")[1], {}))
        subentries.append(
            ConfigSubentryData(data=data, subentry_type="room", title=data["name"], unique_id=entity_id)
        )
    return subentries
