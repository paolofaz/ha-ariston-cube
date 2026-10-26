"""Infrequent independent cloud polling for the Cube S weekly programme."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AristonError
from .weekly_program import parse_weekly_program

_LOGGER = logging.getLogger(__name__)

# A weekly time plan rarely changes. Do not add requests to 60s boiler polling.
SCHEDULE_REFRESH_INTERVAL = timedelta(hours=3)


class AristonWeeklyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Optional schedule coordinator: failures do not block boiler controls."""

    def __init__(self, hass, main_coordinator) -> None:
        super().__init__(
            hass, _LOGGER, name="ariston_cube_weekly_program",
            update_interval=SCHEDULE_REFRESH_INTERVAL,
        )
        self.client = main_coordinator.client
        self.plant_id = main_coordinator.plant_id
        self.plant_name = main_coordinator.plant_name

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            result = await self.client.async_read_weekly_program(self.plant_id)
            return parse_weekly_program(result)
        except (AristonError, ValueError) as exc:
            raise UpdateFailed("Unable to read Cube S weekly programme") from exc



def get_or_create_weekly_coordinator(hass, entry) -> AristonWeeklyCoordinator:
    """Share precisely one schedule poller across sensor and calendar platforms."""
    main = entry.runtime_data
    current = getattr(main, "weekly_coordinator", None)
    if current is not None:
        return current
    current = AristonWeeklyCoordinator(hass, main)
    main.weekly_coordinator = current
    entry.async_create_background_task(
        hass, current.async_refresh(), "Ariston Cube weekly programme initial read"
    )
    return current
