"""Runs one control cycle per interval: read states, ask the core, apply commands."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_OUTDOOR_POWER,
    CONF_PLAN_ENTITY,
    CONF_SEASON,
    DOMAIN,
    LOGGER,
    ROOM_ENTITY,
    ROOM_SETPOINT_ENTITY,
    ROOM_WINDOW,
    STORAGE_VERSION,
)
from .core.config import InstallationConfig, Parameters, valid_setpoint
from .core.controller import Controller, CycleResult
from .core.diagnostics import RoomDiagnostics, room_diagnostics
from .core.journal import Journal, UnitRecord
from .core.learning import CapacityLearner, Learned
from .core.model import WITH_SETPOINT, Command, Mode, RoomState, Season
from .core.plan import Plan, combine, plan_from_forecast
from .core.planner_model import PlannerInputs, planner_inputs
from .data import as_list, build_config, room_data
from .record_file import append_records

type ClimateControlConfigEntry = ConfigEntry[ClimateControlCoordinator]


@dataclass(frozen=True)
class CycleData:
    result: CycleResult
    planner: PlannerInputs
    plan: Plan | None
    rooms: dict[str, RoomDiagnostics] = field(default_factory=dict)
    season: Season = Season.HEAT
    learned: dict[Season, Learned] = field(default_factory=dict)


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
        self._plan_entities: list[str] = as_list(entry.data.get(CONF_PLAN_ENTITY))
        self._windows: dict[str, list[str]] = {
            r[ROOM_ENTITY]: as_list(r.get(ROOM_WINDOW)) for r in room_data(entry)
        }
        self._season_entity: str | None = entry.data.get(CONF_SEASON) or None
        self._power_entity: str | None = entry.data.get(CONF_OUTDOOR_POWER) or None
        self._areas: dict[str, float] = {r.id: r.area_m2 for r in self.cfg.rooms} if self.cfg else {}
        self.learner = CapacityLearner()
        self._journal = Journal()
        self._journal_path = Path(hass.config.path(DOMAIN, f"{entry.entry_id}.jsonl"))
        self._learned_dirty = False  # changed since the last write
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.learned"
        )
        self._setpoint_entities: dict[str, str] = {
            r[ROOM_ENTITY]: r[ROOM_SETPOINT_ENTITY] for r in room_data(entry) if r.get(ROOM_SETPOINT_ENTITY)
        }

    async def async_load_learned(self) -> None:
        """FR-PLNR-02: the learned values survive restarts."""
        stored = await self._store.async_load()
        if stored:
            self.learner.restore(stored)

    async def async_reset_learned(self) -> None:
        """FR-PLNR-03: back to the start values (service, not offered in the daily use)."""
        self.learner.reset()
        self._learned_dirty = False
        await self._store.async_save(self.learner.snapshot())
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        if self._learned_dirty:  # a reload must not lose what the delayed write has not stored yet
            self._learned_dirty = False
            await self._store.async_save(self.learner.snapshot())
        await super().async_shutdown()

    @property
    def commissioning(self) -> bool:
        """True until a planner output is configured (setup order: integration first, then planner)."""
        return not self._plan_entities

    async def _async_update_data(self) -> CycleData | None:
        if self.cfg is None or self.controller is None:
            return None
        now = dt_util.utcnow()
        plan = self._read_plan()
        rooms = {r.id: self._room_state(r.id) for r in self.cfg.rooms}
        setpoints = self._read_setpoints()
        season = self._read_season()
        result = self.controller.step(now, plan, rooms, setpoints, season)
        if self.commissioning:
            # No planner output configured yet: publish SOC and planner values, never touch the units.
            result = replace(result, commands={}, running=False, fallback=False, requested_w=0.0, served=())
        for entity_id, command in result.commands.items():
            await self._apply(entity_id, command)
        self._learn(now, season, result.running, rooms)
        await self._record(now, result)
        current = replace(
            self.cfg.with_setpoints(setpoints), capacity_kwh_per_k=self.learner.capacity_kwh_per_k(season)
        )
        planner = planner_inputs(current, dt_util.as_local(now), season)
        learned = {s: replace(item, bootstrap=[]) for s, item in self.learner.learned.items()}
        return CycleData(
            result, planner, plan, room_diagnostics(current, result.temperatures, season), season, learned
        )

    async def _record(self, now: datetime, result: CycleResult) -> None:
        """FR-OBS-01: start, stop and the state of every indoor unit, written only when something changed."""
        assert self.cfg is not None
        units: dict[str, UnitRecord] = {}
        for room in self.cfg.rooms:
            state = self.hass.states.get(room.id)
            if state is None:
                continue
            attrs = state.attributes
            units[room.id] = UnitRecord(
                mode=state.state,
                temperature_c=attrs.get(ATTR_CURRENT_TEMPERATURE),
                target_c=attrs.get(ATTR_TEMPERATURE),
                fan=attrs.get("fan_mode"),
            )
        context = {
            "season": str(result.season),
            "soc_pct": result.soc_pct,
            "planned_w": result.planned_w,
            "requested_w": result.requested_w,
            "fallback": result.fallback,
        }
        rows = self._journal.record(now, result.running, units, context)
        if rows:
            try:
                await self.hass.async_add_executor_job(append_records, self._journal_path, rows)
            except OSError as err:
                LOGGER.warning("Could not write the operating data to %s: %s", self._journal_path, err)

    def _read_season(self) -> Season:
        """FR-SEAS-01: heating unless the optional switch is on. Missing or unavailable switch = heating."""
        if self._season_entity and self.hass.states.is_state(self._season_entity, STATE_ON):
            return Season.COOL
        return Season.HEAT

    def _learn(self, now: datetime, season: Season, running: bool, rooms: dict[str, RoomState]) -> None:
        """FR-PLNR-02: raw device temperatures (the control rounds to whole degrees) and the power."""
        power: float | None = None
        state = self.hass.states.get(self._power_entity) if self._power_entity else None
        if state is not None and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try:
                power = float(state.state)
            except ValueError:
                power = None
            if power is not None and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == "kW":
                power *= 1000
        temps = {
            room_id: s.temperature_c
            for room_id, s in rooms.items()
            if s.temperature_c is not None and s.mode is not None and not s.window_open
        }
        # Only a complete picture counts: a missing room changes what the mean temperature means.
        if len(temps) < len(rooms):
            running = False
        if self.learner.update(now, season, running and not self.commissioning, temps, self._areas, power):
            self._learned_dirty = True
            self._store.async_delay_save(self.learner.snapshot, 60)

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
        # FR-SAFE-01: open as soon as any of the room's window contacts is open.
        window_open = any(self.hass.states.is_state(w, STATE_ON) for w in self._windows.get(entity_id, []))
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
