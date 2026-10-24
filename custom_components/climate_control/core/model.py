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


class Season(StrEnum):
    """Operating mode of the plant (FR-SEAS-01): heating is the default, cooling mirrors it."""

    HEAT = "heat"
    COOL = "cool"

    @property
    def sign(self) -> float:
        """+1 while heating, -1 while cooling: multiplies temperature differences to a common direction."""
        return 1.0 if self is Season.HEAT else -1.0

    @property
    def mode(self) -> Mode:
        return Mode.HEAT if self is Season.HEAT else Mode.COOL

    @property
    def opposite(self) -> Mode:
        return Mode.COOL if self is Season.HEAT else Mode.HEAT
