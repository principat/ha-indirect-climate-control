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
    CONF_P_MAX,
    CONF_P_MIN,
    CONF_PLAN_ENTITY,
    DOMAIN,
    ROOM_AREA,
    ROOM_COMFORT_MAX,
    ROOM_ENTITY,
    ROOM_NAME,
    ROOM_OVERLOAD_MAX,
    ROOM_POWER,
    ROOM_SETPOINT,
    ROOM_SETPOINT_ENTITY,
    ROOM_WINDOW,
    SUBENTRY_ROOM,
)
from .core.config import ConfigError, Parameters
from .core.model import Mode
from .data import build_config
from .help import (
    HELP_KEY,
    OPTION_HELP,
    PARAMETER_GROUPS,
    ROOM_HELP,
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


def _user_fields(defaults: dict[str, Any]) -> dict[Any, Any]:
    return {
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "Climate Control")): str,
        vol.Required(CONF_P_MIN): _number("W"),
        vol.Required(CONF_P_MAX): _number("W"),
        # Optional: the planner output only exists once the planner uses this integration's sensors.
        vol.Optional(CONF_PLAN_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", multiple=True)
        ),
    }


def _room_fields(with_entity: bool) -> dict[Any, Any]:
    items: dict[Any, Any] = {}
    if with_entity:
        items[vol.Required(ROOM_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="climate")
        )
    items.update(
        {
            vol.Required(ROOM_NAME): str,
            vol.Required(ROOM_SETPOINT, default=21.0): _number("°C", step=0.5, minimum=5, maximum=30),
            vol.Optional(ROOM_SETPOINT_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["input_number", "number", "sensor"])
            ),
            vol.Required(ROOM_COMFORT_MAX, default=24.0): _number("°C", step=0.5, minimum=5, maximum=35),
            vol.Required(ROOM_OVERLOAD_MAX, default=28.0): _number("°C", step=0.5, minimum=5, maximum=35),
            vol.Required(ROOM_POWER): _number("W"),
            vol.Required(ROOM_AREA, default=10): _number("m²", step=0.5),
            vol.Optional(ROOM_WINDOW): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
        }
    )
    return items


def _room_errors(values: dict[str, Any], options: Mapping[str, Any]) -> dict[str, str]:
    """Room limits must lie on the SOC scale: scale min < comfort max < overload max <= scale max."""
    p = Parameters.from_mapping(dict(options))
    if not p.soc_min_c < values[ROOM_COMFORT_MAX] < values[ROOM_OVERLOAD_MAX] <= p.soc_max_c:
        return {"base": "room_limits"}
    return {}


def _installation_errors(values: dict[str, Any]) -> dict[str, str]:
    if not 0 < values[CONF_P_MIN] <= values[CONF_P_MAX]:
        return {"base": "pmin_pmax"}
    return {}


class ClimateControlConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 2

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
                return self.async_update_reload_and_abort(
                    entry, title=title, data=values, options={**entry.options, OPTION_HELP: expanded}
                )
        current = {CONF_NAME: entry.title, **entry.data}
        schema = _with_help(_user_fields(current), USER_HELP, expanded)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, current),
            errors=errors,
        )


class RoomSubentryFlow(ConfigSubentryFlow):
    """FR-CFG-01: one indoor unit per subentry."""

    def _expanded(self) -> bool:
        return bool(self._get_entry().options.get(OPTION_HELP, False))

    def _store_help(self, expanded: bool) -> None:
        entry = self._get_entry()
        if expanded != self._expanded():
            self.hass.config_entries.async_update_entry(
                entry, options={**entry.options, OPTION_HELP: expanded}
            )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        values: dict[str, Any] = {}
        if user_input is not None:
            values, expanded = split_help(user_input, self._expanded())
            self._store_help(expanded)
            entity_id = values[ROOM_ENTITY]
            errors = _room_errors(values, self._get_entry().options)
            if any(s.unique_id == entity_id for s in self._get_entry().subentries.values()):
                errors[ROOM_ENTITY] = "already_configured"
            elif not errors:
                return self.async_create_entry(title=values[ROOM_NAME], data=values, unique_id=entity_id)
        schema = _with_help(_room_fields(with_entity=True), ROOM_HELP, self._expanded())
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, values), errors=errors
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        current = dict(subentry.data)
        if user_input is not None:
            values, expanded = split_help(user_input, self._expanded())
            self._store_help(expanded)
            errors = _room_errors(values, self._get_entry().options)
            if not errors:
                data = {ROOM_ENTITY: subentry.data[ROOM_ENTITY], **values}
                return self.async_update_and_abort(
                    self._get_entry(), subentry, title=values[ROOM_NAME], data=data
                )
            current = {ROOM_ENTITY: subentry.data[ROOM_ENTITY], **values}
        schema = _with_help(_room_fields(with_entity=False), ROOM_HELP, self._expanded())
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, current),
            description_placeholders={"entity_id": subentry.data[ROOM_ENTITY]},
            errors=errors,
        )


def _options_fields(current: Parameters, names: tuple[str, ...]) -> dict[Any, Any]:
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
        else:
            items[vol.Required(f.name, default=value)] = vol.Coerce(float)
    return items


class ClimateControlOptionsFlow(OptionsFlow):
    """All tunable parameters (functional spec, section 4), grouped into menu steps."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=list(PARAMETER_GROUPS))

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
        schema = _with_help(_options_fields(current, names), names, expanded)
        return self.async_show_form(step_id=group, data_schema=schema, errors=errors)
