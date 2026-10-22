"""Simulated indoor units, outdoor power and planner output for the e2e instance.

Behaviour follows the reference devices: a heat request while another unit is in the cool
class makes the unit jump to cooling (conflict at the outdoor unit), a switch to heat/cool
restores the unit's own remembered setpoint, fan/dry have no setpoint, readings are whole degrees.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import probatio as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

DOMAIN = "climate_control_sim"

UNIT_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("temperature", default=20): vol.Coerce(int),
        vol.Optional("nominal_power_w", default=500): vol.Coerce(float),
    }
)
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("units"): {cv.slug: UNIT_SCHEMA},
                vol.Optional("remembered_heat", default=18.0): vol.Coerce(float),
                vol.Optional("remembered_cool", default=26.0): vol.Coerce(float),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


class SimState:
    """Shared state of all simulated devices."""

    def __init__(self, conf: dict[str, Any]) -> None:
        self.conf = conf
        self.units: dict[str, Any] = {}  # object_id -> SimClimate
        self.plan: dict[str, Any] = {"available": False}
        self.listeners: list[Any] = []

    def notify(self) -> None:
        for listener in self.listeners:
            listener()


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    sim = SimState(config[DOMAIN])
    hass.data[DOMAIN] = sim

    async def set_reading(call: ServiceCall) -> None:
        sim.units[call.data["unit"]].set_reading(call.data["temperature"])
        sim.notify()

    async def set_plan(call: ServiceCall) -> None:
        now = dt_util.utcnow()
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=call.data["offset_h"])
        kw = call.data["power_kw"]
        sim.plan = {
            "available": call.data["available"],
            "power_kw": kw,
            "stamp": now.isoformat(),
            "forecast": [
                {"time": (start + timedelta(hours=i)).isoformat(), "value": kw}
                for i in range(call.data["hours"])
            ],
        }
        sim.notify()

    async def reset(call: ServiceCall) -> None:
        for unit in sim.units.values():
            unit.reset()
        sim.notify()

    hass.services.async_register(
        DOMAIN,
        "set_reading",
        set_reading,
        vol.Schema({vol.Required("unit"): cv.slug, vol.Required("temperature"): vol.Coerce(int)}),
    )
    hass.services.async_register(
        DOMAIN,
        "set_plan",
        set_plan,
        vol.Schema(
            {
                vol.Required("power_kw"): vol.Coerce(float),
                vol.Optional("hours", default=24): vol.Coerce(int),
                vol.Optional("offset_h", default=0): vol.Coerce(int),
                vol.Optional("available", default=True): cv.boolean,
            }
        ),
    )
    hass.services.async_register(DOMAIN, "reset", reset)
    for platform in (Platform.CLIMATE, Platform.SENSOR):
        hass.async_create_task(async_load_platform(hass, platform, DOMAIN, {}, config))
    return True
