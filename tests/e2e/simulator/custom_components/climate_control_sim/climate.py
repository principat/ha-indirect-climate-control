"""Simulated indoor units."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN, SimState

COOL_CLASS = {HVACMode.COOL, HVACMode.DRY}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    sim: SimState = hass.data[DOMAIN]
    entities = [SimClimate(sim, object_id, unit) for object_id, unit in sim.conf["units"].items()]
    async_add_entities(entities)


class SimClimate(ClimateEntity):
    _attr_should_poll = False
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5
    _attr_max_temp = 30

    def __init__(self, sim: SimState, object_id: str, unit: dict[str, Any]) -> None:
        self._sim = sim
        self._unit = unit
        self.entity_id = f"climate.{object_id}"
        self._attr_unique_id = f"{DOMAIN}_{object_id}"
        self._attr_name = unit["name"]
        self.nominal_power_w: float = unit["nominal_power_w"]
        sim.units[object_id] = self
        self.reset()

    def reset(self) -> None:
        self._attr_hvac_mode = HVACMode.FAN_ONLY
        self._attr_current_temperature = int(self._unit["temperature"])
        self._attr_target_temperature = None
        if self.hass:
            self.async_write_ha_state()

    def set_reading(self, temperature: int) -> None:
        self._attr_current_temperature = int(temperature)
        self.async_write_ha_state()

    @property
    def demand(self) -> bool:
        """True while the unit asks the outdoor unit for heating or cooling power."""
        t, cur = self._attr_target_temperature, self._attr_current_temperature
        if t is None or cur is None:
            return False
        return (self.hvac_mode == HVACMode.HEAT and t > cur) or (self.hvac_mode == HVACMode.COOL and t < cur)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        others = [u for u in self._sim.units.values() if u is not self]
        if hvac_mode == HVACMode.HEAT and any(u.hvac_mode in COOL_CLASS for u in others):
            hvac_mode = HVACMode.COOL  # conflict at the outdoor unit
        self._attr_hvac_mode = hvac_mode
        remembered = {
            HVACMode.HEAT: self._sim.conf["remembered_heat"],
            HVACMode.COOL: self._sim.conf["remembered_cool"],
        }
        self._attr_target_temperature = remembered.get(hvac_mode)
        self.async_write_ha_state()
        self._sim.notify()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if self.hvac_mode in (HVACMode.HEAT, HVACMode.COOL) and ATTR_TEMPERATURE in kwargs:
            self._attr_target_temperature = float(kwargs[ATTR_TEMPERATURE])
            self.async_write_ha_state()
            self._sim.notify()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
