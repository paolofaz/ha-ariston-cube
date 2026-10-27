"""Ariston Cube integration, configured through the UI."""

from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntryState

from .const import DOMAIN
from .weekly_preview import preview_one_boundary_move
from .api import AristonError

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession, async_create_clientsession

from .api import AristonClient
from .coordinator import AristonCoordinator
from .frontend import async_register_weekly_card

_LOGGER = logging.getLogger(__name__)


_PREVIEW_SERVICE = "preview_weekly_slice"
_PREVIEW_SCHEMA = vol.Schema({
    vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
    vol.Required("from_time"): str,
    vol.Required("to_time"): str,
})


async def async_setup(hass, config) -> bool:
    """Register an offline-change preview using one fresh cloud GET."""

    async def preview(call):
        entries = [
            entry for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise HomeAssistantError("Exactly one loaded Ariston Cube entry is required")
        coordinator = entries[0].runtime_data
        try:
            source = await coordinator.client.async_read_weekly_program(
                coordinator.plant_id
            )
            proposal = preview_one_boundary_move(
                source, call.data["day"],
                call.data["from_time"], call.data["to_time"],
            )
        except (AristonError, ValueError) as exc:
            raise HomeAssistantError("Unable to preview the Cube S time change") from exc

        # Return only the requested weekday: never expose the complete raw
        # authenticated cloud response, plant identifiers or credentials.
        return {
            "status": "preview_only_no_cloud_write",
            "weekday": proposal["weekday"],
            "before": proposal["before"],
            "after": proposal["after"],
            "changed": proposal["changed"],
            "source_fingerprint": proposal["source_fingerprint"],
            "can_submit": False,
        }

    hass.services.async_register(
        DOMAIN, _PREVIEW_SERVICE, preview,
        schema=_PREVIEW_SCHEMA, supports_response=SupportsResponse.ONLY,
    )
    return True


PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.WATER_HEATER, Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.CALENDAR)


async def async_setup_entry(hass, entry) -> bool:
    """Use a token-authenticated client and fetch the initial snapshot."""
    _LOGGER.info("Ariston Cube 1.0.0 starting; platforms=%s", ", ".join(str(getattr(p, "value", p)) for p in PLATFORMS))
    session = async_get_clientsession(hass)
    # Cookie-based R2 login must never share the mobile bearer-token session.
    web_session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    client = AristonClient(
        session, entry.data["username"], entry.data["password"],
        web_session=web_session,
    )
    coordinator = AristonCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    try:
        await async_register_weekly_card(hass)
    except Exception as exc:  # noqa: BLE001
        # Optional UI must never prevent boiler entity setup.
        _LOGGER.warning("Cube S weekly card could not be registered: %s", type(exc).__name__)
    _LOGGER.info("Ariston Cube 1.0.0 platform setup dispatched")
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Unload entity platforms; Home Assistant cleans up the client session."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
