"""FR-UNIT-01: temperature unit of the plant.

The control only works with differences of temperatures and setpoints, so it runs in the unit of the plant.
The unit matters for absolute values only: defaults and ranges of the setpoint, and what counts as plausible.
"""

from __future__ import annotations

from enum import StrEnum


class TemperatureUnit(StrEnum):
    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"

    @property
    def symbol(self) -> str:
        return "°C" if self is TemperatureUnit.CELSIUS else "°F"


def from_celsius(value: float, unit: TemperatureUnit) -> float:
    """An absolute temperature in degrees Celsius, in the unit of the plant (whole degrees for Fahrenheit)."""
    return value if unit is TemperatureUnit.CELSIUS else float(round(value * 9.0 / 5.0 + 32.0))
