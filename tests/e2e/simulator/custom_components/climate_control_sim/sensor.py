"""Simulated outdoor power and planner output."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate.const import HVACMode
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN, SimState

FAN_W = 12.0  # per unit, all seven in fan mode ~85 W


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    sim: SimState = hass.data[DOMAIN]
    entities: list[SensorEntity] = [OutdoorPower(sim), PlannerPower(sim)]
    async_add_entities(entities)
    for entity in entities:
        sim.listeners.append(entity.async_write_ha_state)


class OutdoorPower(SensorEntity):
    _attr_should_poll = False
    _attr_name = "Klima Außen Leistung W"
    _attr_unique_id = f"{DOMAIN}_outdoor_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, sim: SimState) -> None:
        self._sim = sim
        self.entity_id = "sensor.klima_aussen_leistung_w"

    @property
    def native_value(self) -> float:
        units = self._sim.units.values()
        fans = sum(FAN_W for u in units if u.hvac_mode != HVACMode.OFF)
        return fans + sum(u.nominal_power_w for u in units if u.demand)


class PlannerPower(SensorEntity):
    """Planner output: current power in kW plus a `forecast` list of {time, value}."""

    _attr_should_poll = False
    _attr_name = "Sim Planner Power"
    _attr_unique_id = f"{DOMAIN}_planner_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT

    def __init__(self, sim: SimState) -> None:
        self._sim = sim
        self.entity_id = "sensor.sim_planner_power"

    @property
    def available(self) -> bool:
        return bool(self._sim.plan.get("available"))

    @property
    def native_value(self) -> float | None:
        return self._sim.plan.get("power_kw")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"forecast": self._sim.plan.get("forecast", []), "stamp": self._sim.plan.get("stamp")}
