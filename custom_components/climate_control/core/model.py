"""Domain types shared by the core modules."""

from __future__ import annotations

from dataclasses import dataclass, field
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
    target_c: float | None = None  # setpoint the unit holds (to see that a command has arrived)


@dataclass(frozen=True)
class Command:
    """Desired mode (and setpoint for heat/cool) for one indoor unit.

    `boost`: the unit heats under the control of this integration and gets the raised fan level (FR-FAN-01).
    """

    mode: Mode
    target_c: float | None = None
    boost: bool = field(default=False, compare=False)  # an addition to the command, not part of its identity


class OperatingMode(StrEnum):
    """FR-OPM-01: who controls the indoor units and how the plant serves the planner."""

    HEMS_OPTIMIZED = "hems_optimized"
    HEMS_BUFFER = "hems_buffer"
    MANUFACTURER = "manufacturer"
    MANUFACTURER_CYCLE = "manufacturer_cycle"

    @property
    def manufacturer(self) -> bool:
        """The manufacturer's control keeps the temperature, the plant is no buffer for the planner."""
        return self in (OperatingMode.MANUFACTURER, OperatingMode.MANUFACTURER_CYCLE)


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
