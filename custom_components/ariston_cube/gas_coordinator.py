"""Read recent heating/DHW gas usage from cloud two-hour buckets."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AristonError
from .gas_report import parse_recent_gas

_LOGGER = logging.getLogger(__name__)


class AristonGasCoordinator(DataUpdateCoordinator):
    """Refresh both separate gas series every two hours, and once at startup."""

    def __init__(self, hass, main) -> None:
        super().__init__(
            hass, _LOGGER, name="ariston_cube_recent_gas",
            update_interval=timedelta(hours=2),
        )
        self.client = main.client
        self.plant_id = main.plant_id
        self.plant_name = main.plant_name

    async def _async_update_data(self):
        try:
            raw = await self.client.async_read_gas_sequences(self.plant_id)
            data = parse_recent_gas(raw, dt_util.now())
            if all(data[key] is None for key in (
                "heating_today", "dhw_today", "heating_2h", "dhw_2h"
            )):
                raise UpdateFailed("Cloud provided no valid recent gas series")
            return data
        except AristonError as exc:
            raise UpdateFailed("Unable to refresh recent Ariston gas usage") from exc
