"""Translate a stored entry (data, room subentries, options) into the core configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_CAPACITY,
    CONF_P_MAX,
    CONF_P_MIN,
    CONF_UNIT,
    DEFAULT_CAPACITY_KWH_PER_K,
    ROOM_AREA,
    ROOM_BAND_DOWN,
    ROOM_BAND_UP,
    ROOM_ENTITY,
    ROOM_LIMIT_DOWN,
    ROOM_LIMIT_UP,
    ROOM_NAME,
    ROOM_POWER,
    ROOM_SETPOINT,
    ROOM_STEP,
    SUBENTRY_ROOM,
)
from .core.config import InstallationConfig, Parameters, RoomConfig
from .core.units import TemperatureUnit

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def as_list(value: object) -> list[str]:
    """Entity selection stored as a single id (entries before 0.3) or as a list."""
    if not value:
        return []
    return [value] if isinstance(value, str) else [str(v) for v in value]  # type: ignore[attr-defined]


def installation_unit(data: Mapping[str, Any]) -> TemperatureUnit:
    try:
        return TemperatureUnit(data.get(CONF_UNIT, TemperatureUnit.CELSIUS))
    except ValueError:
        return TemperatureUnit.CELSIUS


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
            nominal_power_w=float(r[ROOM_POWER]),
            area_m2=float(r.get(ROOM_AREA, 1.0)),
            band_down=float(r.get(ROOM_BAND_DOWN, RoomConfig.band_down)),
            band_up=float(r.get(ROOM_BAND_UP, RoomConfig.band_up)),
            limit_down=float(r.get(ROOM_LIMIT_DOWN, RoomConfig.limit_down)),
            limit_up=float(r.get(ROOM_LIMIT_UP, RoomConfig.limit_up)),
            step=float(r.get(ROOM_STEP, RoomConfig.step)),
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
