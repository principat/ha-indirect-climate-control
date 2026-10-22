import pytest

from custom_components.climate_control.core.threshold import ThresholdConfig, decide

CFG = ThresholdConfig(p_min_w=1300)


@pytest.mark.req("FR-PLAN-02")
def test_off_below_start_threshold_stays_off() -> None:
    assert decide(1000, running=False, cfg=CFG).run is False


@pytest.mark.req("FR-PLAN-02")
def test_off_at_start_threshold_starts() -> None:
    assert decide(1100, running=False, cfg=CFG).run is True


@pytest.mark.req("FR-PLAN-02")
def test_running_stays_between_thresholds() -> None:
    assert decide(800, running=True, cfg=CFG).run is True


@pytest.mark.req("FR-PLAN-02")
def test_running_stops_below_stop_threshold() -> None:
    assert decide(600, running=True, cfg=CFG).run is False


@pytest.mark.req("FR-PLAN-03")
def test_running_requests_at_least_pmin() -> None:
    assert decide(1100, running=False, cfg=CFG).power_w == 1300
    assert decide(2000, running=True, cfg=CFG).power_w == 2000
