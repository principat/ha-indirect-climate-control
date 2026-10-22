"""Climate Control integration (adapter layer). Business logic lives in core/ (no HA imports)."""

from __future__ import annotations

from typing import Any

import probatio as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_CONFIG_ENTRY_ID, DOMAIN, SERVICE_RUN_CYCLE
from .coordinator import ClimateControlConfigEntry, ClimateControlCoordinator
from .core.config import Parameters

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
RUN_CYCLE_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def run_cycle(call: ServiceCall) -> None:
        """Run a control cycle now on one installation or on all of them."""
        wanted = call.data.get(ATTR_CONFIG_ENTRY_ID)
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            if wanted in (None, entry.entry_id):
                coordinator: ClimateControlCoordinator = entry.runtime_data
                await coordinator.async_refresh()

    hass.services.async_register(DOMAIN, SERVICE_RUN_CYCLE, run_cycle, RUN_CYCLE_SCHEMA)
    return True


def _snapshot(entry: ClimateControlConfigEntry) -> tuple[Any, ...]:
    """Everything that affects control. The help switch (FR-CFG-03) is a pure UI setting."""
    params = Parameters.from_mapping(dict(entry.options))
    rooms = tuple((s.subentry_id, tuple(sorted(s.data.items()))) for s in entry.subentries.values())
    return (tuple(sorted(entry.data.items())), params, rooms)


async def async_setup_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> bool:
    coordinator = ClimateControlCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    loaded = _snapshot(entry)

    async def reload_on_change(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> None:
        if _snapshot(entry) != loaded:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(reload_on_change))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
