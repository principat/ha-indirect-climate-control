"""FR-MODE-01: heating and cooling only change via the neutral mode."""

from __future__ import annotations

from collections.abc import Mapping

from .model import COOL_CLASS, NEUTRAL, Mode


def next_modes(current: Mapping[str, Mode], target: Mapping[str, Mode], neutral: Mode) -> dict[str, Mode]:
    """Modes to apply now on the way from `current` to `target`.

    If a unit is to heat while any unit is in the cool class (or to cool while any unit heats),
    all units that are not neutral go to the neutral mode first. The target is applied in a
    later cycle, once the current modes no longer conflict.
    """
    now_heating = any(m == Mode.HEAT for m in current.values())
    now_cooling = any(m in COOL_CLASS for m in current.values())
    wants_heat = any(m == Mode.HEAT and current.get(r) != Mode.HEAT for r, m in target.items())
    wants_cool = any(m in COOL_CLASS and current.get(r) != m for r, m in target.items())
    if (wants_heat and now_cooling) or (wants_cool and now_heating):
        return {r: (m if m in NEUTRAL else neutral) for r, m in current.items() if r in target}
    return dict(target)
