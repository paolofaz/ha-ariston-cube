"""Low-frequency Ariston monthly gas report (no fabricated lifetime totals)."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AristonError
from .gas_report import parse_last_month_gas

_LOGGER = logging.getLogger(__name__)


class AristonGasCoordinator(DataUpdateCoordinator):
    """Gas consumption reported for the previous month by Ariston NET."""

    def __init__(self, hass, main) -> None:
        super().__init__(
            hass, _LOGGER, name="ariston_cube_gas_last_month",
            update_interval=timedelta(hours=6),
        )
        self.client = main.client
        self.plant_id = main.plant_id
        self.plant_name = main.plant_name

    async def _async_update_data(self):
        try:
            raw = await self.client.async_read_energy_account(self.plant_id)
            return parse_last_month_gas(raw)
        except AristonError as exc:
            raise UpdateFailed("Could not read monthly Ariston gas report") from exc
