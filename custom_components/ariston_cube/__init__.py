"""Ariston Cube integration, configured through the UI."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AristonClient
from .coordinator import AristonCoordinator
from .frontend import async_register_weekly_card

_LOGGER = logging.getLogger(__name__)

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.CALENDAR)


async def async_setup_entry(hass, entry) -> bool:
    """Use a token-authenticated client and fetch the initial snapshot."""
    _LOGGER.info("Ariston Cube 0.8.0 starting; platforms=%s", ", ".join(str(getattr(p, "value", p)) for p in PLATFORMS))
    session = async_get_clientsession(hass)
    client = AristonClient(session, entry.data["username"], entry.data["password"])
    coordinator = AristonCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    try:
        await async_register_weekly_card(hass)
    except Exception as exc:  # noqa: BLE001
        # Optional UI must never prevent boiler entity setup.
        _LOGGER.warning("Cube S weekly card could not be registered: %s", type(exc).__name__)
    _LOGGER.info("Ariston Cube 0.8.0 platform setup dispatched")
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Unload entity platforms; Home Assistant cleans up the client session."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
