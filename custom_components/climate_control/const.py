"""Constants."""

import logging

DOMAIN = "climate_control"
LOGGER = logging.getLogger(__package__)

CONF_PLAN_ENTITY = "plan_entity"
CONF_P_MIN = "p_min_w"
CONF_P_MAX = "p_max_w"
CONF_CAPACITY = "capacity_kwh_per_k"
DEFAULT_CAPACITY_KWH_PER_K = 3.0  # start value until the capacity is learned from operation
SUBENTRY_ROOM = "room"

ROOM_ENTITY = "entity_id"
ROOM_NAME = "name"
ROOM_SETPOINT = "setpoint_c"
ROOM_POWER = "nominal_power_w"
ROOM_AREA = "area_m2"
ROOM_WINDOW = "window_entity"
ROOM_SETPOINT_ENTITY = "setpoint_entity"
ROOM_COMFORT_MAX = "comfort_max_c"
ROOM_OVERLOAD_MAX = "overload_max_c"

SERVICE_RUN_CYCLE = "run_cycle"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
