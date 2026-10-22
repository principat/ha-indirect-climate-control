"""Translate a stored entry (data, room subentries, options) into the core configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_CAPACITY,
    CONF_P_MAX,
    CONF_P_MIN,
    DEFAULT_CAPACITY_KWH_PER_K,
    ROOM_AREA,
    ROOM_CLASS,
    ROOM_ENTITY,
    ROOM_NAME,
    ROOM_POWER,
    ROOM_SETPOINT,
    SUBENTRY_ROOM,
)
from .core.config import InstallationConfig, Parameters, RoomConfig

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def room_data(entry: ConfigEntry) -> list[Mapping[str, Any]]:
    """Room subentries in creation order (= configured order)."""
    return [s.data for s in entry.subentries.values() if s.subentry_type == SUBENTRY_ROOM]


def build_config(entry: ConfigEntry, options: Mapping[str, Any]) -> InstallationConfig | None:
    """None while no indoor unit is configured yet. Raises ConfigError if inconsistent."""
    params = Parameters.from_mapping(dict(options))
    params.validate()
    rooms = tuple(
        RoomConfig(
            id=r[ROOM_ENTITY],
            name=r[ROOM_NAME],
            setpoint_c=float(r[ROOM_SETPOINT]),
            power_class=str(r[ROOM_CLASS]),
            nominal_power_w=float(r[ROOM_POWER]),
            area_m2=float(r.get(ROOM_AREA, 1.0)),
        )
        for r in room_data(entry)
    )
    if not rooms:
        return None
    data = entry.data
    return InstallationConfig(
        p_min_w=float(data[CONF_P_MIN]),
        p_max_w=float(data[CONF_P_MAX]),
        capacity_kwh_per_k=float(data.get(CONF_CAPACITY, DEFAULT_CAPACITY_KWH_PER_K)),
        rooms=rooms,
        params=params,
    )
