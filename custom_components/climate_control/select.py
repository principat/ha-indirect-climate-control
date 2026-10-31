"""Operating mode of the installation (FR-OPM-01)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ClimateControlConfigEntry, ClimateControlCoordinator
from .core.model import OperatingMode
from .entity import ClimateControlEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ClimateControlConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([OperatingModeSelect(entry.runtime_data)])


class OperatingModeSelect(ClimateControlEntity, SelectEntity):
    _attr_options = [str(mode) for mode in OperatingMode]

    def __init__(self, coordinator: ClimateControlCoordinator) -> None:
        super().__init__(coordinator, "operating_mode")

    @property
    def current_option(self) -> str:
        return str(self.coordinator.operating_mode)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_operating_mode(OperatingMode(option))
