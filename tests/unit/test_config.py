from dataclasses import replace

import pytest

from custom_components.climate_control.core.config import ConfigError, InstallationConfig, Parameters
from custom_components.climate_control.core.model import Mode

from .helpers import installation, room


@pytest.mark.req("FR-GEN-01")
def test_any_number_of_rooms_and_classes() -> None:
    cfg = installation(room("x", power=400), room("y", power=900), room("z", power=400))
    assert cfg.class_order == (400.0, 900.0)  # power class = equal nominal power, configured order
    assert cfg.room("y").power_class == 900.0


@pytest.mark.req("FR-GEN-01")
def test_core_has_no_plant_defaults() -> None:
    with pytest.raises(TypeError):
        InstallationConfig(rooms=(room("a"),))  # type: ignore[call-arg]


@pytest.mark.req("FR-GEN-01")
@pytest.mark.parametrize(
    "kwargs",
    [
        {"rooms": ()},
        {"rooms": (room("a"), room("a"))},
        {"p_min_w": 4000},
        {"capacity_kwh_per_k": 0},
        {"params": Parameters(stop_ratio=0.9)},
        {"rooms": (replace(room("a"), comfort_max_c=29.0),)},
        {"rooms": (replace(room("a"), overload_max_c=31.0),)},
        {"params": Parameters(soc_min_c=30)},
        {"params": Parameters(neutral_mode=Mode.HEAT)},
    ],
)
def test_inconsistent_configuration_is_rejected(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "p_min_w": 1300,
        "p_max_w": 3300,
        "capacity_kwh_per_k": 3.5,
        "rooms": (room("a"),),
    }
    with pytest.raises(ConfigError):
        InstallationConfig(**{**base, **kwargs})  # type: ignore[arg-type]


@pytest.mark.req("FR-GEN-01")
def test_parameters_round_trip_through_mapping() -> None:
    p = Parameters(tie_band_k=0.5, neutral_mode=Mode.OFF, night_start_h=22)
    stored = {k: (str(v) if isinstance(v, Mode) else v) for k, v in p.as_mapping().items()}
    assert Parameters.from_mapping({**stored, "unknown": 1}) == p
    assert Parameters.from_mapping({"night_start_h": 20.0}).night_start_h == 20


@pytest.mark.req("FR-GEN-01")
def test_setpoint_from_variable_source_is_validated() -> None:
    from custom_components.climate_control.core.config import valid_setpoint

    assert valid_setpoint("21.5") == 21.5
    assert valid_setpoint(30) == 30.0
    for bad in ("unavailable", None, "4.9", 31, "abc"):
        assert valid_setpoint(bad) is None


@pytest.mark.req("FR-GEN-01")
def test_current_setpoints_override_configured_ones() -> None:
    cfg = installation(room("a", setpoint=21.0), room("b", setpoint=20.0))
    assert cfg.with_setpoints({}) is cfg
    current = cfg.with_setpoints({"a": 23.0, "unknown": 10.0})
    assert [r.setpoint_c for r in current.rooms] == [23.0, 20.0]
    assert cfg.room("a").setpoint_c == 21.0
