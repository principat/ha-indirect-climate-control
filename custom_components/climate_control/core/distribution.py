"""FR-DIST-01 / FR-DIST-02: which indoor units run for a requested power."""

from __future__ import annotations

from collections.abc import Sequence

from .config import RoomConfig

Group = tuple[RoomConfig, ...]
Tier = tuple[Group, ...]


def rank(
    deviations: Sequence[tuple[RoomConfig, float]], band_k: float, class_order: Sequence[float]
) -> tuple[Tier, ...]:
    """Order rooms by deviation (setpoint minus temperature), largest first.

    Rooms whose deviation lies within the band of the tier's largest deviation form one tier.
    Inside a tier the rooms are grouped by power class (configured class order), each group
    keeps the configured room order. `deviations` must be given in configured room order.
    """
    remaining = sorted(enumerate(deviations), key=lambda x: (-x[1][1], x[0]))
    tiers: list[Tier] = []
    while remaining:
        top = remaining[0][1][1]
        members = [x for x in remaining if top - x[1][1] < band_k]
        remaining = [x for x in remaining if top - x[1][1] >= band_k]
        members.sort(key=lambda x: x[0])
        groups = [tuple(room for _, (room, _) in members if room.power_class == cls) for cls in class_order]
        tiers.append(tuple(g for g in groups if g))
    return tuple(tiers)


def select(tiers: Sequence[Tier], requested_w: float) -> tuple[RoomConfig, ...]:
    """Add whole groups in rank order until their nominal power covers the request."""
    chosen: list[RoomConfig] = []
    total = 0.0
    for tier in tiers:
        for group in tier:
            if chosen and total >= requested_w:
                return tuple(chosen)
            chosen.extend(group)
            total += sum(r.nominal_power_w for r in group)
    return tuple(chosen)
