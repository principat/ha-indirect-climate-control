"""Translate a stored entry (data, room subentries, options) into the core configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_CAPACITY,
    CONF_P_MAX,
    CONF_P_MIN,
    CONF_UNIT,
    DEFAULT_CAPACITY_KWH_PER_K,
    ROOM_AREA,
    ROOM_COMFORT_MAX,
    ROOM_ENTITY,
    ROOM_NAME,
    ROOM_OVERLOAD_MAX,
    ROOM_POWER,
    ROOM_SETPOINT,
    SUBENTRY_ROOM,
)
from .core.config import InstallationConfig, Parameters, RoomConfig
from .core.units import TemperatureUnit, from_celsius, to_celsius

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def as_list(value: object) -> list[str]:
    """Entity selection stored as a single id (entries before 0.3) or as a list."""
    if not value:
        return []
    return [value] if isinstance(value, str) else [str(v) for v in value]  # type: ignore[attr-defined]


SCALE_FIELDS = ("soc_min_c", "soc_max_c")  # the only absolute temperatures among the parameters


def installation_unit(data: Mapping[str, Any]) -> TemperatureUnit:
    try:
        return TemperatureUnit(data.get(CONF_UNIT, TemperatureUnit.CELSIUS))
    except ValueError:
        return TemperatureUnit.CELSIUS


def core_parameters(options: Mapping[str, Any], unit: TemperatureUnit) -> Parameters:
    """Parameters for the core (degrees Celsius). Stored scale values are in the plant's unit."""
    params = Parameters.from_mapping(dict(options))
    changes: dict[str, Any] = {f: to_celsius(float(options[f]), unit) for f in SCALE_FIELDS if f in options}
    return replace(params, **changes) if changes else params


def ui_parameters(options: Mapping[str, Any], unit: TemperatureUnit) -> Parameters:
    """Parameters as the options dialog shows them: the scale in the plant's unit (Fahrenheit: 59 to 86)."""
    params = Parameters.from_mapping(dict(options))
    if unit is TemperatureUnit.CELSIUS:
        return params
    defaults = Parameters()
    changes: dict[str, Any] = {
        f: float(options[f]) if f in options else from_celsius(getattr(defaults, f), unit)
        for f in SCALE_FIELDS
    }
    return replace(params, **changes)


def room_data(entry: ConfigEntry) -> list[Mapping[str, Any]]:
    """Room subentries in creation order (= configured order)."""
    return [s.data for s in entry.subentries.values() if s.subentry_type == SUBENTRY_ROOM]


def build_config(entry: ConfigEntry, options: Mapping[str, Any]) -> InstallationConfig | None:
    """None while no indoor unit is configured yet. Raises ConfigError if inconsistent."""
    unit = installation_unit(entry.data)
    params = core_parameters(options, unit)
    params.validate()
    rooms = tuple(
        RoomConfig(
            id=r[ROOM_ENTITY],
            name=r[ROOM_NAME],
            setpoint_c=to_celsius(float(r[ROOM_SETPOINT]), unit),
            nominal_power_w=float(r[ROOM_POWER]),
            area_m2=float(r.get(ROOM_AREA, 1.0)),
            comfort_max_c=to_celsius(float(r.get(ROOM_COMFORT_MAX, from_celsius(24.0, unit))), unit),
            overload_max_c=to_celsius(float(r.get(ROOM_OVERLOAD_MAX, from_celsius(28.0, unit))), unit),
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
