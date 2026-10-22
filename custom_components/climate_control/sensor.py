"""Sensors: buffer state, plan and the planner model values (FR-PLNR-01)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateControlConfigEntry, ClimateControlCoordinator, CycleData
from .core.planner_model import Series
from .entity import ClimateControlEntity

COST = "cost"  # marker: unit is the instance currency per kWh


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
        key="charge_cost",
        value=lambda d: d.planner.charge_cost,
        unit=COST,
        attrs=lambda d: _forecast(d.planner.charge_cost_forecast),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ClimateControlConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    currency = f"{hass.config.currency}/kWh"
    async_add_entities(CCSensor(entry.runtime_data, d, currency) for d in SENSORS)


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

    @property
    def native_value(self) -> float | str | None:
        data = self.coordinator.data
        return self._desc.value(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        return self._desc.attrs(data) if data and self._desc.attrs else None
