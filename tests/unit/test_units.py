"""FR-UNIT-01: the temperature unit of the plant (Celsius default, Fahrenheit)."""

import pytest

from custom_components.climate_control.core.config import Parameters
from custom_components.climate_control.core.soc import temperature_to_soc
from custom_components.climate_control.core.units import TemperatureUnit, from_celsius, to_celsius
from custom_components.climate_control.data import core_parameters, installation_unit, ui_parameters

C, F = TemperatureUnit.CELSIUS, TemperatureUnit.FAHRENHEIT


@pytest.mark.req("FR-UNIT-01")
def test_celsius_is_the_default_and_nothing_is_converted() -> None:
    assert installation_unit({}) is C and installation_unit({"temperature_unit": "bogus"}) is C
    assert installation_unit({"temperature_unit": "fahrenheit"}) is F
    assert to_celsius(21.5, C) == 21.5 and from_celsius(21.5, C) == 21.5
    assert ui_parameters({}, C) == Parameters() and core_parameters({}, C) == Parameters()


@pytest.mark.req("FR-UNIT-01")
def test_the_scale_of_15_to_30_celsius_is_59_to_86_fahrenheit() -> None:
    assert to_celsius(59, F) == pytest.approx(15.0) and to_celsius(86, F) == pytest.approx(30.0)
    assert from_celsius(15.0, F) == 59.0 and from_celsius(30.0, F) == 86.0
    defaults = ui_parameters({}, F)
    assert (defaults.soc_min_c, defaults.soc_max_c) == (59.0, 86.0)  # shown in the dialog in the plant's unit
    core = core_parameters({}, F)
    assert (core.soc_min_c, core.soc_max_c) == (15.0, 30.0)  # the core always works in degrees Celsius


@pytest.mark.req("FR-UNIT-01")
def test_a_stored_scale_is_read_in_the_plants_unit() -> None:
    options = {"soc_min_c": 50.0, "soc_max_c": 95.0}
    core = core_parameters(options, F)
    assert (core.soc_min_c, core.soc_max_c) == (pytest.approx(10.0), pytest.approx(35.0))
    shown = ui_parameters(options, F)
    assert (shown.soc_min_c, shown.soc_max_c) == (50.0, 95.0)


@pytest.mark.req("FR-UNIT-01")
def test_the_same_physical_temperature_gives_the_same_soc_in_both_units() -> None:
    celsius = temperature_to_soc(20.0, core_parameters({}, C))
    fahrenheit = temperature_to_soc(to_celsius(68.0, F), core_parameters({}, F))
    assert celsius == pytest.approx(fahrenheit) == pytest.approx(33.33, abs=0.01)


@pytest.mark.req("FR-UNIT-01")
def test_temperatures_for_fahrenheit_devices_are_whole_degrees() -> None:
    assert from_celsius(21.0, F) == 70.0  # 69.8
    assert from_celsius(22.0, F) == 72.0  # 71.6
    assert to_celsius(from_celsius(21.0, F), F) == pytest.approx(21.1, abs=0.05)
