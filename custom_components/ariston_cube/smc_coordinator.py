"""Smc report coordinator with clock-aligned reads and six-hour fallback."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .smc_report import parse_smc_report
from .web_portal import WebPortalError

_LOGGER = logging.getLogger(__name__)


class AristonSmcCoordinator(DataUpdateCoordinator):
    """Web reports are independent of the mobile data-items coordinator."""

    def __init__(self, hass, main):
        super().__init__(
            hass, _LOGGER, name="ariston_cube_physical_gas_smc",
            update_interval=timedelta(hours=6),
        )
        self.client = main.client
        self.plant_id = main.plant_id
        self.plant_name = main.plant_name

    async def _async_update_data(self):
        try:
            report = await self.client.web_portal.async_read_metering(self.plant_id)
            result = parse_smc_report(report, dt_util.now())
            if all(result[key] is None for key in (
                "heating_smc_today", "dhw_smc_today",
                "heating_smc_2h", "dhw_smc_2h"
            )):
                raise UpdateFailed("No completed Smc interval in web report")
            return result
        except WebPortalError as exc:
            raise UpdateFailed("Ariston web gas report unavailable") from exc
