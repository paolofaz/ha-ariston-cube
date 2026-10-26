"""Smc report coordinator with clock-aligned reads and six-hour fallback."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .smc_report import parse_smc_report
from .gas_ledger import StoredGasLedger
from .night_smc_debug import NightSmcHistory
from .web_portal import WebPortalError

_LOGGER = logging.getLogger(__name__)

# HOLD: midnight Smc histogram timing not yet field-verified.
_SMC_TOTALS_VERIFIED = False


class AristonSmcCoordinator(DataUpdateCoordinator):
    """Web reports are independent of the mobile data-items coordinator."""

    def __init__(self, hass, main, *, entry_id: str):
        super().__init__(
            hass, _LOGGER, name="ariston_cube_physical_gas_smc",
            update_interval=timedelta(hours=6),
        )
        self.client = main.client
        self.plant_id = main.plant_id
        self.plant_name = main.plant_name
        self.gas_ledger = StoredGasLedger(hass, entry_id) if _SMC_TOTALS_VERIFIED else None
        self.night_history = NightSmcHistory(hass, entry_id)

    async def _async_update_data(self):
        try:
            report = await self.client.web_portal.async_read_metering(self.plant_id)
            now = dt_util.now()
            result = parse_smc_report(report, now)
            if all(result[key] is None for key in (
                "heating_smc_today", "dhw_smc_today",
                "heating_smc_2h", "dhw_smc_2h"
            )):
                raise UpdateFailed("No completed Smc interval in web report")
            # Diagnostic data are derived from the SAME already fetched
            # response: no further request to the boiler or cloud.
            try:
                result["night_debug"] = await self.night_history.async_record(
                    report, now
                )
            except (OSError, ValueError) as exc:
                _LOGGER.warning(
                    "Overnight Smc samples not stored: %s", type(exc).__name__
                )
                result["night_debug"] = {
                    "count": 0, "snapshots": [], "last_capture": None,
                    "error_type": type(exc).__name__,
                }

            # Never create live Energy totals until the 00:00/02:00
            # physical web histogram has been compared on the real device.
            meter = {"heating": None, "dhw": None, "history_complete": False}
            if self.gas_ledger is not None:
                try:
                    meter = await self.gas_ledger.async_apply(report, now)
                except (OSError, ValueError) as exc:
                    _LOGGER.warning(
                        "Persistent Smc totals not updated: %s", type(exc).__name__
                    )
            result["total_heating_smc"] = meter["heating"]
            result["total_dhw_smc"] = meter["dhw"]
            result["history_complete"] = meter["history_complete"]
            physical = report.get("asPhysicalUnit", {})
            histogram = physical.get("histogramData", []) if isinstance(physical, dict) else []
            result["observed_periods"] = sorted({
                row["period"] for row in histogram
                if isinstance(row, dict)
                and row.get("period") in ("CurrentDay", "PreviousDay")
            }) if isinstance(histogram, list) else []
            return result
        except WebPortalError as exc:
            raise UpdateFailed("Ariston web gas report unavailable") from exc
