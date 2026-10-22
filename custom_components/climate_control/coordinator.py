"""Runs one control cycle per interval: read states, ask the core, apply commands."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components.climate.const import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_HVAC_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate.const import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import CONF_PLAN_ENTITY, DOMAIN, LOGGER, ROOM_ENTITY, ROOM_SETPOINT_ENTITY, ROOM_WINDOW
from .core.config import InstallationConfig, Parameters, valid_setpoint
from .core.controller import Controller, CycleResult
from .core.model import WITH_SETPOINT, Command, Mode, RoomState
from .core.plan import Plan, combine, plan_from_forecast
from .core.planner_model import PlannerInputs, planner_inputs
from .data import build_config, room_data

type ClimateControlConfigEntry = ConfigEntry[ClimateControlCoordinator]


@dataclass(frozen=True)
class CycleData:
    result: CycleResult
    planner: PlannerInputs
    plan: Plan | None


class ClimateControlCoordinator(DataUpdateCoordinator[CycleData | None]):
    """Data is None while no indoor unit is configured (nothing is controlled)."""

    config_entry: ClimateControlConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ClimateControlConfigEntry) -> None:
        self.cfg: InstallationConfig | None = build_config(entry, entry.options)
        params = self.cfg.params if self.cfg else Parameters.from_mapping(dict(entry.options))
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=params.cycle_s),
        )
        self.controller = Controller(self.cfg) if self.cfg else None
        plan_entities = entry.data[CONF_PLAN_ENTITY]
        self._plan_entities: list[str] = (
            [plan_entities] if isinstance(plan_entities, str) else list(plan_entities)
        )
        self._windows: dict[str, str | None] = {r[ROOM_ENTITY]: r.get(ROOM_WINDOW) for r in room_data(entry)}
        self._setpoint_entities: dict[str, str] = {
            r[ROOM_ENTITY]: r[ROOM_SETPOINT_ENTITY] for r in room_data(entry) if r.get(ROOM_SETPOINT_ENTITY)
        }

    async def _async_update_data(self) -> CycleData | None:
        if self.cfg is None or self.controller is None:
            return None
        now = dt_util.utcnow()
        plan = self._read_plan()
        rooms = {r.id: self._room_state(r.id) for r in self.cfg.rooms}
        setpoints = self._read_setpoints()
        result = self.controller.step(now, plan, rooms, setpoints)
        for entity_id, command in result.commands.items():
            await self._apply(entity_id, command)
        planner = planner_inputs(self.cfg.with_setpoints(setpoints), dt_util.as_local(now))
        return CycleData(result, planner, plan)

    def _read_setpoints(self) -> dict[str, float]:
        """Current setpoints from configured entities. Invalid or missing values keep the fixed setpoint."""
        setpoints: dict[str, float] = {}
        for room_id, entity_id in self._setpoint_entities.items():
            state = self.hass.states.get(entity_id)
            value = valid_setpoint(state.state) if state else None
            if value is not None:
                setpoints[room_id] = value
        return setpoints

    def _read_plan(self) -> Plan | None:
        """FR-PLAN-01: planned power now and ahead, summed over all planner outputs.

        None = planner unavailable (FR-SAFE-04).
        """
        return combine([self._read_one_plan(entity_id) for entity_id in self._plan_entities])

    def _read_one_plan(self, entity_id: str) -> Plan | None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        received = max(state.last_updated, state.last_reported)
        return plan_from_forecast(
            state.state,
            state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
            state.attributes.get("forecast"),
            received,
        )

    def _room_state(self, entity_id: str) -> RoomState:
        state = self.hass.states.get(entity_id)
        window = self._windows.get(entity_id)
        window_open = window is not None and self.hass.states.is_state(window, STATE_ON)
        if state is None:
            return RoomState(None, None, window_open)
        try:
            mode: Mode | None = Mode(state.state)
        except ValueError:
            mode = None
        temperature = state.attributes.get(ATTR_CURRENT_TEMPERATURE)
        return RoomState(mode, float(temperature) if temperature is not None else None, window_open)

    async def _apply(self, entity_id: str, command: Command) -> None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return
        try:
            switched = state.state != command.mode
            if switched:
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    SERVICE_SET_HVAC_MODE,
                    {ATTR_ENTITY_ID: entity_id, ATTR_HVAC_MODE: str(command.mode)},
                    blocking=True,
                )
            # FR-MODE-02: the unit restores its own remembered setpoint after a mode change,
            # so the setpoint is set again after every switch to heat or cool.
            if command.mode in WITH_SETPOINT and command.target_c is not None:
                current = self.hass.states.get(entity_id)
                actual = current.attributes.get(ATTR_TEMPERATURE) if current else None
                if switched or actual != command.target_c:
                    await self.hass.services.async_call(
                        CLIMATE_DOMAIN,
                        SERVICE_SET_TEMPERATURE,
                        {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: command.target_c},
                        blocking=True,
                    )
        except HomeAssistantError as err:
            LOGGER.warning("Could not apply %s to %s: %s", command, entity_id, err)
