import pytest

from custom_components.climate_control.core.distribution import rank, select

from .helpers import room

A, B, C = room("a"), room("b"), room("c")


def _ids(tiers) -> list[list[list[str]]]:  # noqa: ANN001
    return [[[r.id for r in g] for g in tier] for tier in tiers]


@pytest.mark.req("FR-DIST-01")
def test_larger_deviation_higher_priority() -> None:
    tiers = rank([(A, 0.0), (B, 3.0), (C, -1.0)], 1.0, [700.0])
    assert _ids(tiers) == [[["b"]], [["a"]], [["c"]]]


@pytest.mark.req("FR-DIST-02")
def test_acceptance_scenario_tie_band() -> None:
    # A 3 K, B and C 1 K, band 1 K: A first.
    tiers = rank([(A, 3.0), (B, 1.0), (C, 1.0)], 1.0, [700.0])
    assert _ids(tiers) == [[["a"]], [["b", "c"]]]
    assert [r.id for r in select(tiers, 500)] == ["a"]
    # A down to 1 K: all equal, served in parallel in configured order.
    tiers = rank([(A, 1.0), (B, 1.0), (C, 1.0)], 1.0, [700.0])
    assert _ids(tiers) == [[["a", "b", "c"]]]
    assert [r.id for r in select(tiers, 500)] == ["a", "b", "c"]


@pytest.mark.req("FR-DIST-02")
def test_ties_grouped_by_power_class_in_configured_order() -> None:
    s1, s2 = room("s1", power=300), room("s2", power=300)
    b1, b2 = room("b1", power=900), room("b2", power=900)
    devs = [(s1, 1.0), (b1, 1.5), (s2, 1.2), (b2, 1.0)]
    tiers = rank(devs, 1.0, [300.0, 900.0])
    assert _ids(tiers) == [[["s1", "s2"], ["b1", "b2"]]]
    assert [r.id for r in select(tiers, 500)] == ["s1", "s2"]
    assert [r.id for r in select(tiers, 1300)] == ["s1", "s2", "b1", "b2"]


@pytest.mark.req("FR-DIST-02")
def test_select_takes_everything_if_request_exceeds_capacity() -> None:
    tiers = rank([(A, 1.0), (B, 0.0)], 1.0, [700.0])
    assert [r.id for r in select(tiers, 99999)] == ["a", "b"]
    assert select((), 1000) == ()
