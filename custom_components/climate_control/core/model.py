"""Domain types shared by the core modules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    """Operating mode of an indoor unit. Values match the platform's mode names."""

    HEAT = "heat"
    COOL = "cool"
    DRY = "dry"
    FAN = "fan_only"
    OFF = "off"


COOL_CLASS = frozenset({Mode.COOL, Mode.DRY})
NEUTRAL = frozenset({Mode.FAN, Mode.OFF})
WITH_SETPOINT = frozenset({Mode.HEAT, Mode.COOL})


@dataclass(frozen=True)
class RoomState:
    """What the controller sees of one room in one cycle."""

    mode: Mode | None
    temperature_c: float | None
    window_open: bool = False


@dataclass(frozen=True)
class Command:
    """Desired mode (and setpoint for heat/cool) for one indoor unit."""

    mode: Mode
    target_c: float | None = None
