"""Read-only Ariston Cube integration, configured through the UI."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AristonClient
from .coordinator import AristonCoordinator

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.WATER_HEATER)


async def async_setup_entry(hass, entry) -> bool:
    """Use a token-authenticated client and fetch the initial snapshot."""
    session = async_get_clientsession(hass)
    client = AristonClient(session, entry.data["username"], entry.data["password"])
    coordinator = AristonCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Unload read-only platforms; Home Assistant cleans up the client session."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
