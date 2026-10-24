"""Config flow (FR-GEN-01, FR-CFG-01..03).

Installation in the main flow, each indoor unit as its own subentry (add, change, remove one at
a time), all parameters as options. Several installations can be configured side by side.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any

import probatio as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CONF_OUTDOOR_POWER,
    CONF_P_MAX,
    CONF_P_MIN,
    CONF_PLAN_ENTITY,
    CONF_SEASON,
    CONF_UNIT,
    DOMAIN,
    ROOM_AREA,
    ROOM_BAND_DOWN,
    ROOM_BAND_UP,
    ROOM_ENTITY,
    ROOM_LIMIT_DOWN,
    ROOM_LIMIT_UP,
    ROOM_NAME,
    ROOM_POWER,
    ROOM_SETPOINT,
    ROOM_SETPOINT_ENTITY,
    ROOM_SETPOINT_SOURCE,
    ROOM_START_OFFSET,
    ROOM_STEP,
    ROOM_WINDOW,
    SOURCE_CONSTANT,
    SOURCE_ENTITY,
    SUBENTRY_ROOM,
)
from .core.config import ConfigError, Parameters, RoomConfig
from .core.model import Mode
from .core.units import TemperatureUnit, from_celsius
from .data import as_list, build_config, installation_unit, setpoint_source
from .help import (
    HELP_KEY,
    OPTION_HELP,
    PARAMETER_GROUPS,
    ROOM_HELP,
    SETPOINT_CONSTANT_HELP,
    SETPOINT_ENTITY_HELP,
    USER_HELP,
    help_section_key,
    split_help,
)


def _number(
    unit: str, step: float = 1, minimum: float = 0, maximum: float = 100000
) -> selector.Selector[Any]:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _with_help(items: dict[Any, Any], help_fields: tuple[str, ...], expanded: bool) -> vol.Schema:
    """Insert a collapsible help section (holding the helper switch) above each listed field."""
    schema: dict[Any, Any] = {}
    for marker, validator in items.items():
        if str(marker) in help_fields:
            schema[vol.Optional(help_section_key(str(marker)))] = section(
                vol.Schema({vol.Optional(HELP_KEY, default=expanded): selector.BooleanSelector()}),
                {"collapsed": not expanded},
            )
        schema[marker] = validator
    return vol.Schema(schema)


def _outdoor_power_selector() -> selector.Selector[Any]:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", device_class="power"))


def _season_selector() -> selector.Selector[Any]:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["switch", "binary_sensor", "input_boolean"])
    )


def _user_fields(defaults: dict[str, Any]) -> dict[Any, Any]:
    return {
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Climate Control")): str,
        vol.Required(CONF_UNIT, default=TemperatureUnit.CELSIUS.value): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[u.value for u in TemperatureUnit], translation_key=CONF_UNIT
            )
        ),
        vol.Required(CONF_P_MIN): _number("W"),
        vol.Required(CONF_P_MAX): _number("W"),
        vol.Required(CONF_OUTDOOR_POWER): _outdoor_power_selector(),
        vol.Optional(CONF_SEASON): _season_selector(),
        # Optional: the planner output only exists once the planner uses this integration's sensors.
        vol.Optional(CONF_PLAN_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", multiple=True)
        ),
    }


def _room_fields(with_entity: bool, unit: TemperatureUnit) -> dict[Any, Any]:
    """Temperatures are entered in the plant's unit (FR-UNIT-01); the ranges follow it."""
    symbol = unit.symbol
    items: dict[Any, Any] = {}
    if with_entity:
        items[vol.Required(ROOM_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        )
    items.update(
        {
            vol.Required(ROOM_NAME): str,
            # FR-CFG-04: a fixed value or an entity: the choice here, the value in the next step
            vol.Required(ROOM_SETPOINT_SOURCE, default=SOURCE_CONSTANT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SOURCE_CONSTANT, SOURCE_ENTITY],
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key=ROOM_SETPOINT_SOURCE,
                )
            ),
            # FR-BAND-01: optional distances to the current setpoint, in the plant's unit
            vol.Optional(ROOM_BAND_DOWN, default=RoomConfig.band_down): _number(
                symbol, step=0.5, minimum=0.5, maximum=15
            ),
            vol.Optional(ROOM_BAND_UP, default=RoomConfig.band_up): _number(
                symbol, step=0.5, minimum=0.5, maximum=15
            ),
            vol.Optional(ROOM_LIMIT_DOWN, default=RoomConfig.limit_down): _number(
                symbol, step=0.5, minimum=0.5, maximum=15
            ),
            vol.Optional(ROOM_LIMIT_UP, default=RoomConfig.limit_up): _number(
                symbol, step=0.5, minimum=0.5, maximum=15
            ),
            vol.Optional(ROOM_START_OFFSET, default=RoomConfig.start_offset): _number(
                symbol, step=0.5, minimum=0, maximum=10
            ),
            vol.Optional(ROOM_STEP, default=RoomConfig.step): _number(
                symbol, step=0.1, minimum=0.1, maximum=5
            ),
            vol.Required(ROOM_POWER): _number("W"),
            vol.Required(ROOM_AREA, default=10): _number("m²", step=0.5),
            vol.Optional(ROOM_WINDOW): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
        }
    )
    return items


def _room_errors(values: dict[str, Any]) -> dict[str, str]:
    """The control range must lie inside the absolute limit, in both directions."""
    down = values.get(ROOM_BAND_DOWN, RoomConfig.band_down) <= values.get(
        ROOM_LIMIT_DOWN, RoomConfig.limit_down
    )
    up = values.get(ROOM_BAND_UP, RoomConfig.band_up) <= values.get(ROOM_LIMIT_UP, RoomConfig.limit_up)
    return {} if down and up else {"base": "room_limits"}


def _installation_errors(values: dict[str, Any]) -> dict[str, str]:
    if not 0 < values[CONF_P_MIN] <= values[CONF_P_MAX]:
        return {"base": "pmin_pmax"}
    return {}


class ClimateControlConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 4

    def __init__(self) -> None:
        self._help = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ClimateControlOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_ROOM: RoomSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        values: dict[str, Any] = {}
        if user_input is not None:
            values, self._help = split_help(user_input, self._help)
            errors = _installation_errors(values)
            if not errors:
                title = values.pop(CONF_NAME)
                return self.async_create_entry(title=title, data=values, options={OPTION_HELP: self._help})
        schema = _with_help(_user_fields(values), USER_HELP, self._help)
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, values), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        expanded = bool(entry.options.get(OPTION_HELP, False))
        errors: dict[str, str] = {}
        if user_input is not None:
            values, expanded = split_help(user_input, expanded)
            errors = _installation_errors(values)
            if not errors:
                title = values.pop(CONF_NAME)
                # The update listener reloads the entry; the reload helper as well would reload twice.
                self.hass.config_entries.async_update_entry(
                    entry, title=title, data=values, options={**entry.options, OPTION_HELP: expanded}
                )
                return self.async_abort(reason="reconfigure_successful")
        current = {CONF_NAME: entry.title, **entry.data}
        schema = _with_help(_user_fields(current), USER_HELP, expanded)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, current),
            errors=errors,
        )


class RoomSubentryFlow(ConfigSubentryFlow):
    """FR-CFG-01: one indoor unit per subentry. FR-CFG-04: the setpoint source first, its value next."""

    def __init__(self) -> None:
        super().__init__()
        self._room: dict[str, Any] = {}
        self._old: Mapping[str, Any] = {}
        self._reconfiguring = False

    def _expanded(self) -> bool:
        return bool(self._get_entry().options.get(OPTION_HELP, False))

    def _unit(self) -> TemperatureUnit:
        return installation_unit(self._get_entry().data)

    def _store_help(self, expanded: bool) -> None:
        entry = self._get_entry()
        if expanded != self._expanded():
            self.hass.config_entries.async_update_entry(
                entry, options={**entry.options, OPTION_HELP: expanded}
            )

    @staticmethod
    def _suggested(values: dict[str, Any]) -> dict[str, Any]:
        """Multi-selects need a list as suggested value, older entries stored a single id."""
        if values.get(ROOM_WINDOW):
            values[ROOM_WINDOW] = as_list(values[ROOM_WINDOW])
        return values

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        values: dict[str, Any] = {}
        if user_input is not None:
            values, expanded = split_help(user_input, self._expanded())
            self._store_help(expanded)
            entity_id = values[ROOM_ENTITY]
            errors = _room_errors(values)
            if any(s.unique_id == entity_id for s in self._get_entry().subentries.values()):
                errors[ROOM_ENTITY] = "already_configured"
            elif not errors:
                self._room = values
                return await self._next_step()
        schema = _with_help(_room_fields(True, self._unit()), ROOM_HELP, self._expanded())
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, values), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        self._reconfiguring = True
        self._old = subentry.data
        errors: dict[str, str] = {}
        current = self._suggested({**subentry.data, ROOM_SETPOINT_SOURCE: setpoint_source(subentry.data)})
        if user_input is not None:
            values, expanded = split_help(user_input, self._expanded())
            self._store_help(expanded)
            errors = _room_errors(values)
            if not errors:
                self._room = {ROOM_ENTITY: subentry.data[ROOM_ENTITY], **values}
                return await self._next_step()
            current = self._suggested({ROOM_ENTITY: subentry.data[ROOM_ENTITY], **values})
        schema = _with_help(_room_fields(False, self._unit()), ROOM_HELP, self._expanded())
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, current),
            description_placeholders={"entity_id": subentry.data[ROOM_ENTITY]},
            errors=errors,
        )

    async def _next_step(self) -> SubentryFlowResult:
        if self._room[ROOM_SETPOINT_SOURCE] == SOURCE_ENTITY:
            return await self.async_step_setpoint_entity()
        return await self.async_step_setpoint_constant()

    async def async_step_setpoint_constant(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The setpoint is a fixed value (entered here)."""
        unit = self._unit()
        expanded = self._expanded()
        if user_input is not None:
            values, expanded = split_help(user_input, expanded)
            self._store_help(expanded)
            data = {k: v for k, v in self._room.items() if k != ROOM_SETPOINT_ENTITY}
            return self._finish({**data, ROOM_SETPOINT: values[ROOM_SETPOINT]})
        symbol = unit.symbol
        step = 0.5 if unit is TemperatureUnit.CELSIUS else 1
        fields = {
            vol.Required(ROOM_SETPOINT, default=from_celsius(21.0, unit)): _number(
                symbol, step=step, minimum=from_celsius(5, unit), maximum=from_celsius(30, unit)
            )
        }
        schema = _with_help(fields, SETPOINT_CONSTANT_HELP, expanded)
        current = {ROOM_SETPOINT: self._old[ROOM_SETPOINT]} if ROOM_SETPOINT in self._old else {}
        return self.async_show_form(
            step_id="setpoint_constant", data_schema=self.add_suggested_values_to_schema(schema, current)
        )

    async def async_step_setpoint_entity(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """The setpoint comes from an entity (chosen here)."""
        expanded = self._expanded()
        if user_input is not None:
            values, expanded = split_help(user_input, expanded)
            self._store_help(expanded)
            data = dict(self._room)
            data[ROOM_SETPOINT_ENTITY] = values[ROOM_SETPOINT_ENTITY]
            data.pop(ROOM_SETPOINT, None)  # one value only: the fixed one is gone
            return self._finish(data)
        fields = {
            vol.Required(ROOM_SETPOINT_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["input_number", "number", "sensor"])
            )
        }
        schema = _with_help(fields, SETPOINT_ENTITY_HELP, expanded)
        current = (
            {ROOM_SETPOINT_ENTITY: self._old[ROOM_SETPOINT_ENTITY]}
            if ROOM_SETPOINT_ENTITY in self._old
            else {}
        )
        return self.async_show_form(
            step_id="setpoint_entity", data_schema=self.add_suggested_values_to_schema(schema, current)
        )

    def _finish(self, data: dict[str, Any]) -> SubentryFlowResult:
        if self._reconfiguring:
            return self.async_update_and_abort(
                self._get_entry(), self._get_reconfigure_subentry(), title=data[ROOM_NAME], data=data
            )
        return self.async_create_entry(title=data[ROOM_NAME], data=data, unique_id=data[ROOM_ENTITY])


def _options_fields(current: Parameters, names: tuple[str, ...], unit: TemperatureUnit) -> dict[Any, Any]:
    items: dict[Any, Any] = {}
    for name in names:
        value = getattr(current, name)
        f = next(f for f in fields(Parameters) if f.name == name)
        if isinstance(value, Mode):
            items[vol.Required(f.name, default=str(value))] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[str(Mode.FAN), str(Mode.OFF)], translation_key="neutral_mode"
                )
            )
        elif isinstance(value, int):
            items[vol.Required(f.name, default=value)] = vol.Coerce(int)
        elif f.name.endswith("_k"):  # FR-UNIT-01: temperature differences are given in the plant's unit
            items[vol.Required(f.name, default=value)] = _number(unit.symbol, step=0.1, minimum=0, maximum=30)
        else:
            items[vol.Required(f.name, default=value)] = vol.Coerce(float)
    return items


class ClimateControlOptionsFlow(OptionsFlow):
    """All tunable parameters (functional spec, section 4), grouped into menu steps."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["plan", "sensors", *PARAMETER_GROUPS])

    async def async_step_plan(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Planner output: connected here as well, because it is set after the planner exists."""
        entry = self.config_entry
        expanded = bool(entry.options.get(OPTION_HELP, False))
        if user_input is not None:
            values, expanded = split_help(user_input, expanded)
            data = {k: v for k, v in entry.data.items() if k != CONF_PLAN_ENTITY}
            if values.get(CONF_PLAN_ENTITY):
                data[CONF_PLAN_ENTITY] = values[CONF_PLAN_ENTITY]
            self.hass.config_entries.async_update_entry(entry, data=data)
            return self.async_create_entry(data={**entry.options, OPTION_HELP: expanded})
        field = {
            vol.Optional(CONF_PLAN_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", multiple=True)
            )
        }
        schema = _with_help(field, (CONF_PLAN_ENTITY,), expanded)
        current = {CONF_PLAN_ENTITY: entry.data[CONF_PLAN_ENTITY]} if entry.data.get(CONF_PLAN_ENTITY) else {}
        return self.async_show_form(
            step_id="plan", data_schema=self.add_suggested_values_to_schema(schema, current)
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Outdoor unit power and cooling switch: also here, so they can be changed without reconfiguring."""
        entry = self.config_entry
        expanded = bool(entry.options.get(OPTION_HELP, False))
        if user_input is not None:
            values, expanded = split_help(user_input, expanded)
            data = {k: v for k, v in entry.data.items() if k not in (CONF_OUTDOOR_POWER, CONF_SEASON)}
            data[CONF_OUTDOOR_POWER] = values[CONF_OUTDOOR_POWER]
            if values.get(CONF_SEASON):  # empty = no switch = heating
                data[CONF_SEASON] = values[CONF_SEASON]
            self.hass.config_entries.async_update_entry(entry, data=data)
            return self.async_create_entry(data={**entry.options, OPTION_HELP: expanded})
        fields = {
            vol.Required(CONF_OUTDOOR_POWER): _outdoor_power_selector(),
            vol.Optional(CONF_SEASON): _season_selector(),
        }
        schema = _with_help(fields, (CONF_OUTDOOR_POWER, CONF_SEASON), expanded)
        current = {k: entry.data[k] for k in (CONF_OUTDOOR_POWER, CONF_SEASON) if entry.data.get(k)}
        return self.async_show_form(
            step_id="sensors", data_schema=self.add_suggested_values_to_schema(schema, current)
        )

    async def async_step_control(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._group("control", user_input)

    async def async_step_soc(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._group("soc", user_input)

    async def async_step_safety(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._group("safety", user_input)

    async def async_step_planner(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._group("planner", user_input)

    async def _group(self, group: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        names = PARAMETER_GROUPS[group]
        expanded = bool(self.config_entry.options.get(OPTION_HELP, False))
        current = Parameters.from_mapping(dict(self.config_entry.options))
        errors: dict[str, str] = {}
        if user_input is not None:
            values, expanded = split_help(user_input, expanded)
            stored = {k: (str(v) if isinstance(v, Mode) else v) for k, v in current.as_mapping().items()}
            merged = {**stored, **values}
            try:
                build_config(self.config_entry, merged)
            except ConfigError, ValueError:
                errors["base"] = "invalid_parameters"
            else:
                return self.async_create_entry(data={**merged, OPTION_HELP: expanded})
        unit = installation_unit(self.config_entry.data)
        schema = _with_help(_options_fields(current, names, unit), names, expanded)
        return self.async_show_form(step_id=group, data_schema=schema, errors=errors)
