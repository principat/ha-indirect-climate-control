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
USER_HELP = ("temperature_unit", "plan_entity", "p_min_w", "p_max_w", "outdoor_power_entity", "season_entity")
ROOM_HELP = (
    "entity_id",
    "setpoint_source",
    "band_down",
    "band_up",
    "limit_down",
    "limit_up",
    "step",
    "fan_heat",
    "fan_neutral",
    "nominal_power_w",
    "area_m2",
    "window_entity",
)

SETPOINT_CONSTANT_HELP = ("setpoint_c",)
SETPOINT_ENTITY_HELP = ("setpoint_entity",)


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


# Options are grouped into menu steps: form sections cannot be nested, help sections already are sections.
PARAMETER_GROUPS: dict[str, tuple[str, ...]] = {
    "control": (
        "start_ratio",
        "stop_ratio",
        "min_run_s",
        "tie_band_k",
        "load_deadband_ratio",
        "load_settle_max_s",
        "cutoff_k",
        "join_margin_k",
        "activation_rise_k",
        "startup_s",
        "settle_s",
        "neutral_mode",
        "standby_delay_s",
        "cycle_setback_k",
        "cycle_s",
    ),
    "soc": (
        "soc_sigma",
        "display_offset_k",
        "heat_offset_k",
        "offset_threshold_pct",
        "offset_target_pct",
        "offset_cap_factor",
        "soc_smoothing_s",
        "outlier_k",
    ),
    "safety": (
        "overheat_k",
        "overheat_s",
        "plan_max_age_s",
        "fallback_delay_s",
        "fallback_step_s",
    ),
    "planner": (
        "efficiency_pct",
        "discharge_limit_w",
        "night_start_h",
        "night_end_h",
        "night_setback_k",
        "undercharge_cost",
        "overcharge_cost",
        "late_charge_surcharge",
        "cooldown_s",
        "cooldown_surcharge",
        "planner_horizon_h",
    ),
}
