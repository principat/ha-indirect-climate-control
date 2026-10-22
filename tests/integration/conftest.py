"""Integration fixtures: HA test harness with fake indoor units and a fake planner output."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_control.const import DOMAIN

from .fakes import INSTALLATION, ROOMS, FakeUnits, room_subentries


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):  # noqa: ANN001
    """Let the Home Assistant test harness load custom_components/."""
    yield


@pytest.fixture
def units(hass: HomeAssistant) -> FakeUnits:
    fake = FakeUnits(hass)
    for entity_id in ROOMS:
        fake.set(entity_id, "fan_only", 20)
    return fake


@pytest.fixture
def setup_entry(hass: HomeAssistant) -> Callable[..., Any]:
    async def _setup(
        options: dict[str, Any] | None = None,
        title: str = "Climate Control",
        **room_overrides: dict[str, Any],
    ) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=title,
            data=dict(INSTALLATION),
            options=options or {},
            subentries_data=room_subentries(**room_overrides),
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup
