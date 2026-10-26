"""Constants."""

import logging

DOMAIN = "climate_control"
LOGGER = logging.getLogger(__package__)

CONF_PLAN_ENTITY = "plan_entity"
CONF_OUTDOOR_POWER = "outdoor_power_entity"
CONF_UNIT = "temperature_unit"  # celsius (default) or fahrenheit, FR-UNIT-01
CONF_SEASON = "season_entity"  # optional: off = heating (default), on = cooling
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
ROOM_SETPOINT_SOURCE = "setpoint_source"  # FR-CFG-04: a fixed value or an entity, never both
SOURCE_CONSTANT = "constant"
SOURCE_ENTITY = "entity"
ROOM_BAND_DOWN = "band_down"  # FR-BAND-01: control range and absolute limit, distances to the setpoint
ROOM_BAND_UP = "band_up"
ROOM_LIMIT_DOWN = "limit_down"
ROOM_LIMIT_UP = "limit_up"
ROOM_STEP = "step"  # smallest change of the device temperature the unit reports (informational)

SERVICE_RUN_CYCLE = "run_cycle"
SERVICE_RESET_LEARNED = "reset_learned_capacity"
STORAGE_VERSION = 1
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
