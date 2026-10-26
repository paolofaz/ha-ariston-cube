"""Scheduled polling and parsing for one configured Ariston plant."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AristonAuthError, AristonClient, AristonError
from .const import CONF_PLANT_ID, DOMAIN, SCAN_INTERVAL_SECONDS
from .model import parse_main_data

_LOGGER = logging.getLogger(__name__)


class AristonCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Expose a single immutable-by-convention snapshot to all entities."""

    def __init__(self, hass, entry, client: AristonClient) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self.plant_id: str = entry.data[CONF_PLANT_ID]
        self.plant_name: str = entry.data.get("plant_name", "Ariston Cube")

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            raw = await self.client.async_read_main(self.plant_id)
            return parse_main_data(raw)
        except AristonAuthError as exc:
            raise ConfigEntryAuthFailed("Ariston authentication failed") from exc
        except (AristonError, ValueError) as exc:
            raise UpdateFailed("Unable to refresh Ariston data") from exc
