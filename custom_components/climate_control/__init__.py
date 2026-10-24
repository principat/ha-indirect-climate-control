"""Climate Control integration (adapter layer). Business logic lives in core/ (no HA imports)."""

from __future__ import annotations

from typing import Any

import probatio as vol
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    CONF_OUTDOOR_POWER,
    DOMAIN,
    LOGGER,
    ROOM_WINDOW,
    SERVICE_RESET_LEARNED,
    SERVICE_RUN_CYCLE,
    SUBENTRY_ROOM,
)
from .coordinator import ClimateControlConfigEntry, ClimateControlCoordinator
from .core.config import Parameters
from .data import as_list

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

    async def reset_learned(call: ServiceCall) -> None:
        """FR-PLNR-03: only after fundamental changes to the plant."""
        wanted = call.data.get(ATTR_CONFIG_ENTRY_ID)
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            if wanted in (None, entry.entry_id):
                coordinator: ClimateControlCoordinator = entry.runtime_data
                await coordinator.async_reset_learned()

    hass.services.async_register(DOMAIN, SERVICE_RUN_CYCLE, run_cycle, RUN_CYCLE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESET_LEARNED, reset_learned, RUN_CYCLE_SCHEMA)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> bool:
    """Version 1 -> 2: settings moved or removed in 0.2/0.3 are cleaned up in stored entries.

    Version 2 -> 3: window contacts are stored as a list (single id before 0.3).
    """
    if entry.version > 3:
        return False  # downgrade from a newer version
    if entry.version == 1:
        data = {k: v for k, v in entry.data.items() if k not in _OBSOLETE_DATA}
        options = {k: v for k, v in entry.options.items() if k not in _ROOM_LIMITS}
        limits = {k: entry.options[k] for k in _ROOM_LIMITS if k in entry.options}
        for subentry in entry.subentries.values():
            if subentry.subentry_type != SUBENTRY_ROOM:
                continue
            room = {k: v for k, v in subentry.data.items() if k not in _OBSOLETE_ROOM}
            room = {**limits, **room}  # room values win, former installation-wide values fill gaps
            if room != dict(subentry.data):
                hass.config_entries.async_update_subentry(entry, subentry, data=room)
        hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
        LOGGER.info("Migrated %s to configuration version 2", entry.title)
    if entry.version == 2:
        for subentry in entry.subentries.values():
            window = subentry.data.get(ROOM_WINDOW)
            if subentry.subentry_type == SUBENTRY_ROOM and isinstance(window, str):
                room = {**subentry.data, ROOM_WINDOW: as_list(window)}
                hass.config_entries.async_update_subentry(entry, subentry, data=room)
        hass.config_entries.async_update_entry(entry, version=3)
        LOGGER.info("Migrated %s to configuration version 3", entry.title)
    return True


# Removed from the installation in 0.2 (power stages, capacity now internal and learned).
_OBSOLETE_DATA = ("stage1_w", "capacity_kwh_per_k")
# Moved from the installation parameters to each indoor unit in 0.3.
_ROOM_LIMITS = ("comfort_max_c", "overload_max_c")
# Derived from the nominal power since 0.3.
_OBSOLETE_ROOM = ("power_class",)


def _snapshot(entry: ClimateControlConfigEntry) -> tuple[Any, ...]:
    """Everything that affects control. The help switch (FR-CFG-03) is a pure UI setting."""
    params = Parameters.from_mapping(dict(entry.options))
    rooms = tuple((s.subentry_id, tuple(sorted(s.data.items()))) for s in entry.subentries.values())
    return (tuple(sorted(entry.data.items())), params, rooms)


def _check_outdoor_power(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> None:
    """The outdoor unit power sensor is mandatory; entries from before 0.6 miss it and get a repair issue."""
    issue_id = f"outdoor_power_missing_{entry.entry_id}"
    if entry.data.get(CONF_OUTDOOR_POWER):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="outdoor_power_missing",
        translation_placeholders={"name": entry.title},
    )


async def async_setup_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> bool:
    _check_outdoor_power(hass, entry)
    # The configuration the coordinator is built from. Taken, and watched, before the first await: a change made
    # while the entry is still being set up must still trigger a reload, otherwise the control runs on stale rooms.
    loaded = _snapshot(entry)

    async def reload_on_change(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> None:
        if _snapshot(entry) != loaded:
            await hass.config_entries.async_reload(entry.entry_id)

    entry.async_on_unload(entry.add_update_listener(reload_on_change))
    coordinator = ClimateControlCoordinator(hass, entry)
    await coordinator.async_load_learned()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ClimateControlConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, f"outdoor_power_missing_{entry.entry_id}")
