"""FR-UNIT-01: the temperature unit of the plant (Celsius default, Fahrenheit)."""

from dataclasses import replace

import pytest

from custom_components.climate_control.core.config import Parameters, valid_setpoint
from custom_components.climate_control.core.controller import Controller
from custom_components.climate_control.core.model import Mode
from custom_components.climate_control.core.units import TemperatureUnit, from_celsius
from custom_components.climate_control.data import installation_unit

from .helpers import T0, installation, plan, room, states

C, F = TemperatureUnit.CELSIUS, TemperatureUnit.FAHRENHEIT


@pytest.mark.req("FR-UNIT-01")
def test_celsius_is_the_default() -> None:
    assert installation_unit({}) is C and installation_unit({"temperature_unit": "bogus"}) is C
    assert installation_unit({"temperature_unit": "fahrenheit"}) is F
    assert C.symbol == "°C" and F.symbol == "°F"
    assert from_celsius(21.5, C) == 21.5


@pytest.mark.req("FR-UNIT-01")
def test_absolute_defaults_and_ranges_are_converted_for_the_forms() -> None:
    assert (from_celsius(21.0, F), from_celsius(5.0, F), from_celsius(30.0, F)) == (70.0, 41.0, 86.0)
    assert from_celsius(22.0, F) == 72.0  # 71.6, whole degrees


@pytest.mark.req("FR-UNIT-01")
def test_plausibility_of_a_setpoint_follows_the_unit() -> None:
    assert valid_setpoint(71, from_celsius(5, F), from_celsius(30, F)) == 71.0
    assert valid_setpoint(100, from_celsius(5, F), from_celsius(30, F)) is None  # 37.8 degC
    assert (
        valid_setpoint(25, 5, 30) == 25.0 and valid_setpoint(71, 5, 30) is None
    )  # the same number in Celsius


@pytest.mark.req("FR-UNIT-01")
def test_the_control_uses_differences_so_the_numbers_work_in_any_unit() -> None:
    celsius = installation(room("a", setpoint=21.0))
    fahrenheit = installation(room("a", setpoint=70.0))
    for cfg, reading in ((celsius, 19.0), (fahrenheit, 68.0)):  # both 2 below the setpoint
        result = Controller(cfg).step(T0, plan(2000), states({"a": reading}))
        assert result.soc_pct == pytest.approx(26.67, abs=0.01)
        assert result.commands["a"].mode is Mode.HEAT
        assert result.commands["a"].target_c == reading + 1  # offset of 1 in the unit of the plant


@pytest.mark.req("FR-UNIT-01")
def test_distances_are_numbers_in_the_unit_of_the_plant() -> None:
    cfg = installation(replace(room("a", setpoint=70.0), band_down=4.0, limit_down=6.0))
    params = cfg.params
    assert params == Parameters()  # same start values, 1 K became 1 degree of the unit
    assert cfg.room("a").limit_down == 6.0
