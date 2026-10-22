"""FR-CFG-03: collapsible help above every non-trivial settings field.

Each such field gets a collapsible section right above it. The section's description is the
help text (translations), its only content is the helper switch `help_expanded`. The switch
decides whether all help sections are expanded when the settings are opened next time.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HELP_KEY = "help_expanded"
HELP_PREFIX = "help_"
OPTION_HELP = "help_expanded"

# Fields with help, per form. Everything except names is considered non-trivial.
USER_HELP = ("plan_entity", "p_min_w", "p_max_w")
ROOM_HELP = (
    "entity_id",
    "setpoint_c",
    "setpoint_entity",
    "power_class",
    "nominal_power_w",
    "area_m2",
    "window_entity",
)


def help_section_key(field: str) -> str:
    return f"{HELP_PREFIX}{field}"


def split_help(user_input: Mapping[str, Any], expanded: bool) -> tuple[dict[str, Any], bool]:
    """Separate field values from help sections; return the (possibly toggled) help setting.

    The setting changes when any help section's switch differs from the current setting.
    """
    values: dict[str, Any] = {}
    new = expanded
    for key, value in user_input.items():
        if key.startswith(HELP_PREFIX) and isinstance(value, Mapping):
            if HELP_KEY in value and bool(value[HELP_KEY]) != expanded:
                new = bool(value[HELP_KEY])
        else:
            values[key] = value
    return values, new
