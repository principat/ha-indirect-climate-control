"""Binary sensors: outdoor unit running on plan, fallback active."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateControlConfigEntry, ClimateControlCoordinator
from .entity import ClimateControlEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ClimateControlConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([RunningSensor(coordinator), FallbackSensor(coordinator)])


class RunningSensor(ClimateControlEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: ClimateControlCoordinator) -> None:
        super().__init__(coordinator, "running")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.result.running)


class FallbackSensor(ClimateControlEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: ClimateControlCoordinator) -> None:
        super().__init__(coordinator, "fallback")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.result.fallback)
