"""Common base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ClimateControlCoordinator


class ClimateControlEntity(CoordinatorEntity[ClimateControlCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ClimateControlCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    @property
    def available(self) -> bool:
        """Unavailable while no indoor unit is configured."""
        return super().available and self.coordinator.data is not None
