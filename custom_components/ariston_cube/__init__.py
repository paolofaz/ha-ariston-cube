"""Read-only Ariston Cube integration, configured through the UI."""

from __future__ import annotations

from aiohttp import CookieJar

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AristonClient
from .coordinator import AristonCoordinator

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR)


async def async_setup_entry(hass, entry) -> None:
    """Create an isolated cookie session and fetch an initial snapshot."""
    session = async_create_clientsession(hass, cookie_jar=CookieJar())
    client = AristonClient(session, entry.data["username"], entry.data["password"])
    coordinator = AristonCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass, entry) -> bool:
    """Unload read-only platforms; Home Assistant cleans up the client session."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
