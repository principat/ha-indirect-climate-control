"""Sensors: buffer state, plan, planner model values (FR-PLNR-01) and diagnostics per room (FR-OBS-02)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ROOM_ENTITY, ROOM_NAME, SUBENTRY_ROOM
from .coordinator import ClimateControlConfigEntry, ClimateControlCoordinator, CycleData
from .core.diagnostics import RoomDiagnostics
from .core.learning import STEP_K
from .core.model import Season
from .core.planner_model import Series
from .entity import ClimateControlEntity

COST = "cost"  # marker: unit is the instance currency per kWh
KWH_PER_K = "kWh/K"


def _forecast(series: Series) -> dict[str, Any]:
    return {"forecast": [{"time": t.isoformat(), "value": v} for t, v in series]}


def _plan_attrs(d: CycleData) -> dict[str, Any]:
    if d.plan is None:
        return {"forecast": []}
    hours = d.planner.min_charge_forecast
    now = hours[0][0] if hours else d.plan.received
    points = d.plan.horizon(now, len(hours) or 24)
    return {"forecast": [{"time": p.start.isoformat(), "value": p.power_w} for p in points]}


@dataclass(frozen=True, kw_only=True)
class CCSensorDescription:
    key: str
    value: Callable[[CycleData], float | str | None]
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    attrs: Callable[[CycleData], dict[str, Any]] | None = None
    diagnostic: bool = False


def _learned(season: Season) -> Callable[[CycleData], dict[str, Any]]:
    def attrs(d: CycleData) -> dict[str, Any]:
        item = d.learned.get(season)
        updated = item.updated.isoformat() if item and item.updated else None
        last = item.last_estimate_kwh if item else None
        return {
            "estimates": item.estimates if item else 0,
            "updated": updated,
            # single estimates in kWh per K: the first three (before they replace the start value), the latest
            "pending_estimates": [round(v / STEP_K, 3) for v in item.bootstrap] if item else [],
            "last_estimate": round(last / STEP_K, 3) if last is not None else None,
        }

    return attrs


SENSORS: tuple[CCSensorDescription, ...] = (
    CCSensorDescription(
        key="soc",
        value=lambda d: d.result.soc_pct,
        unit=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        attrs=lambda d: {"worst_room": d.result.worst_room},
    ),
    CCSensorDescription(
        key="planned_power",
        value=lambda d: d.result.planned_w,
        unit=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        attrs=_plan_attrs,
    ),
    CCSensorDescription(
        key="requested_power",
        value=lambda d: d.result.requested_w,
        unit=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        attrs=lambda d: {"served_rooms": list(d.result.served)},
    ),
    CCSensorDescription(
        key="capacity",
        value=lambda d: d.planner.capacity_kwh,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
    ),
    CCSensorDescription(
        key="min_charge",
        value=lambda d: d.planner.min_charge_pct,
        unit=PERCENTAGE,
        attrs=lambda d: _forecast(d.planner.min_charge_forecast),
    ),
    CCSensorDescription(
        key="undercharge",
        value=lambda d: d.planner.undercharge_pct,
        unit=PERCENTAGE,
        attrs=lambda d: _forecast(d.planner.undercharge_forecast),
    ),
    CCSensorDescription(key="max_charge", value=lambda d: d.planner.max_charge_pct, unit=PERCENTAGE),
    CCSensorDescription(key="overcharge", value=lambda d: d.planner.overcharge_pct, unit=PERCENTAGE),
    CCSensorDescription(key="undercharge_cost", value=lambda d: d.planner.undercharge_cost, unit=COST),
    CCSensorDescription(key="overcharge_cost", value=lambda d: d.planner.overcharge_cost, unit=COST),
    CCSensorDescription(key="efficiency", value=lambda d: d.planner.efficiency_pct, unit=PERCENTAGE),
    CCSensorDescription(
        key="max_discharge_power",
        value=lambda d: d.planner.max_discharge_kw,
        unit=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    CCSensorDescription(
        key="max_charge_power",
        value=lambda d: d.planner.max_charge_kw,
        unit=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    CCSensorDescription(
        key="learned_heat_capacity",
        value=lambda d: d.learned[Season.HEAT].capacity_kwh_per_k if Season.HEAT in d.learned else None,
        unit=KWH_PER_K,
        state_class=SensorStateClass.MEASUREMENT,
        attrs=_learned(Season.HEAT),
        diagnostic=True,
    ),
    CCSensorDescription(
        key="learned_cool_capacity",
        value=lambda d: d.learned[Season.COOL].capacity_kwh_per_k if Season.COOL in d.learned else None,
        unit=KWH_PER_K,
        state_class=SensorStateClass.MEASUREMENT,
        attrs=_learned(Season.COOL),
        diagnostic=True,
    ),
    CCSensorDescription(
        key="charge_cost",
        value=lambda d: d.planner.charge_cost,
        unit=COST,
        attrs=lambda d: _forecast(d.planner.charge_cost_forecast),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ClimateControlConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    currency = f"{hass.config.currency}/kWh"
    async_add_entities(CCSensor(coordinator, d, currency) for d in SENSORS)
    # FR-OBS-02: diagnostic sensors on a device per indoor unit, linked to its subentry.
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_ROOM:
            continue
        async_add_entities(
            (RoomSensor(coordinator, subentry.subentry_id, subentry.data, d) for d in ROOM_SENSORS),
            config_subentry_id=subentry.subentry_id,
        )


class CCSensor(ClimateControlEntity, SensorEntity):
    # Forecast lists are large and change at least hourly; planners read the current state only.
    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(
        self, coordinator: ClimateControlCoordinator, desc: CCSensorDescription, currency: str
    ) -> None:
        super().__init__(coordinator, desc.key)
        self._desc = desc
        self._attr_native_unit_of_measurement = currency if desc.unit == COST else desc.unit
        self._attr_device_class = desc.device_class
        self._attr_state_class = desc.state_class
        if desc.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float | str | None:
        data = self.coordinator.data
        return self._desc.value(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        return self._desc.attrs(data) if data and self._desc.attrs else None


@dataclass(frozen=True, kw_only=True)
class RoomSensorDescription:
    key: str
    value: Callable[[RoomDiagnostics], float | None]
    unit: str
    device_class: SensorDeviceClass | None = None


ROOM_SENSORS: tuple[RoomSensorDescription, ...] = (
    RoomSensorDescription(
        key="room_deviation",
        value=lambda r: r.deviation_k,
        unit=UnitOfTemperature.KELVIN,
    ),
    RoomSensorDescription(
        key="room_heat_demand",
        value=lambda r: r.heat_demand_kwh,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
    ),
    RoomSensorDescription(
        key="room_step_power",
        value=lambda r: r.step_power_w,
        unit=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    RoomSensorDescription(
        key="room_storage",
        value=lambda r: r.storage_kwh,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
    ),
)


class RoomSensor(CoordinatorEntity[ClimateControlCoordinator], SensorEntity):
    """Diagnostic value of one indoor unit, on its own device."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ClimateControlCoordinator,
        subentry_id: str,
        room: Mapping[str, Any],
        desc: RoomSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._room_id: str = room[ROOM_ENTITY]
        self._desc = desc
        self._attr_unique_id = f"{entry.entry_id}_{subentry_id}_{desc.key}"
        self._attr_translation_key = desc.key
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_class = desc.device_class
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{subentry_id}")},
            name=room[ROOM_NAME],
        )

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        diagnostics = data.rooms.get(self._room_id) if data else None
        return self._desc.value(diagnostics) if diagnostics else None
