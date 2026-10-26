"""Independent ACS Comfort state with safe, non-retried command execution."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .web_portal import WebPortalError

_LOGGER = logging.getLogger(__name__)


class AristonDhwComfortCoordinator(DataUpdateCoordinator):
    """Real U6_9_2 parameter: 0 disabled, 1 timed, 2 always enabled."""

    def __init__(self, hass, main):
        super().__init__(
            hass, _LOGGER, name="ariston_cube_acs_comfort",
            update_interval=timedelta(minutes=15),
        )
        self.client = main.client
        self.plant_id = main.plant_id
        self.plant_name = main.plant_name

    async def _async_update_data(self) -> int:
        try:
            record = await self.client.web_portal.async_read_comfort(self.plant_id)
            return record["value"]
        except WebPortalError as exc:
            raise UpdateFailed("ACS Comfort cannot be read from web menu") from exc

    async def async_set_comfort(self, enabled: bool) -> None:
        if self.data not in (0, 2):
            raise HomeAssistantError("Comfort ACS non disponibile nel menu Ariston")
        try:
            value = await self.client.web_portal.async_set_comfort(
                self.plant_id, 2 if enabled else 0
            )
        except WebPortalError as exc:
            raise HomeAssistantError(str(exc)) from exc
        self.async_set_updated_data(value)
