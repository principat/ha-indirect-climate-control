"""FR-UNIT-01: temperature unit of the plant. The control itself always works in degrees Celsius."""

from __future__ import annotations

from enum import StrEnum


class TemperatureUnit(StrEnum):
    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"

    @property
    def symbol(self) -> str:
        return "°C" if self is TemperatureUnit.CELSIUS else "°F"


def to_celsius(value: float, unit: TemperatureUnit) -> float:
    """A device or entered temperature in the plant's unit, as degrees Celsius."""
    return value if unit is TemperatureUnit.CELSIUS else (value - 32.0) * 5.0 / 9.0


def from_celsius(value: float, unit: TemperatureUnit) -> float:
    """A temperature for a device, in the plant's unit. Fahrenheit is sent in whole degrees."""
    return value if unit is TemperatureUnit.CELSIUS else float(round(value * 9.0 / 5.0 + 32.0))
