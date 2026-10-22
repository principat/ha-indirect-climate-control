"""Constants."""

import logging

DOMAIN = "climate_control"
LOGGER = logging.getLogger(__package__)

CONF_PLAN_ENTITY = "plan_entity"
CONF_P_MIN = "p_min_w"
CONF_P_MAX = "p_max_w"
CONF_STAGE1 = "stage1_w"
CONF_CAPACITY = "capacity_kwh_per_k"
SUBENTRY_ROOM = "room"

ROOM_ENTITY = "entity_id"
ROOM_NAME = "name"
ROOM_SETPOINT = "setpoint_c"
ROOM_CLASS = "power_class"
ROOM_POWER = "nominal_power_w"
ROOM_AREA = "area_m2"
ROOM_WINDOW = "window_entity"
ROOM_SETPOINT_ENTITY = "setpoint_entity"

SERVICE_RUN_CYCLE = "run_cycle"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
