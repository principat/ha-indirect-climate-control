import pytest

from custom_components.climate_control.core.model import Mode
from custom_components.climate_control.core.modes import next_modes

H, C, D, F, X = Mode.HEAT, Mode.COOL, Mode.DRY, Mode.FAN, Mode.OFF


@pytest.mark.req("FR-MODE-01")
def test_heat_while_cooling_goes_neutral_first() -> None:
    assert next_modes({"a": C, "b": F}, {"a": F, "b": H}, F) == {"a": F, "b": F}
    assert next_modes({"a": F, "b": F}, {"a": F, "b": H}, F) == {"a": F, "b": H}


@pytest.mark.req("FR-MODE-01")
def test_dry_counts_as_cool_class() -> None:
    assert next_modes({"a": D, "b": F}, {"a": D, "b": H}, F) == {"a": F, "b": F}


@pytest.mark.req("FR-MODE-01")
def test_cool_while_heating_goes_neutral_first() -> None:
    assert next_modes({"a": H, "b": X}, {"a": F, "b": C}, F) == {"a": F, "b": X}


@pytest.mark.req("FR-MODE-01")
def test_neutral_to_off_or_heat_allowed_when_nobody_cools() -> None:
    assert next_modes({"a": F, "b": H}, {"a": X, "b": H}, F) == {"a": X, "b": H}
    assert next_modes({"a": X, "b": F}, {"a": H, "b": H}, F) == {"a": H, "b": H}


@pytest.mark.req("FR-MODE-01")
def test_direct_heat_to_cool_on_one_unit_is_not_allowed() -> None:
    assert next_modes({"a": H}, {"a": C}, F) == {"a": F}
    assert next_modes({"a": C}, {"a": H}, X) == {"a": X}
