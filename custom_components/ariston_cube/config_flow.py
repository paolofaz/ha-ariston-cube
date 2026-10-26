"""UI-only onboarding for Ariston Cube."""

from __future__ import annotations

import logging

from aiohttp import CookieJar
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AristonAuthError, AristonClient, AristonConnectionError, AristonResponseError
from .const import CONF_PLANT_ID, CONF_PLANT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
})


class AristonCubeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one config entry per plant, without YAML."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, str] = {}
        self._plants: list[dict[str, str]] = []

    async def async_step_user(self, user_input=None):
        """Authenticate and discover plants."""
        errors = {}
        if user_input is not None:
            session = async_create_clientsession(self.hass, cookie_jar=CookieJar())
            client = AristonClient(
                session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                self._plants = await client.async_list_plants()
                if not self._plants:
                    errors["base"] = "no_plants"
                else:
                    self._credentials = dict(user_input)
                    if len(self._plants) == 1:
                        return await self._create_for_plant(self._plants[0])
                    return await self.async_step_plant()
            except AristonAuthError:
                errors["base"] = "invalid_auth"
            except AristonConnectionError:
                errors["base"] = "cannot_connect"
            except AristonResponseError:
                errors["base"] = "invalid_response"
            finally:
                session.detach()
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA, errors=errors)

    async def async_step_plant(self, user_input=None):
        """Select the exact plant if an account has multiple installations."""
        if not self._plants:
            return await self.async_step_user()
        choices = {plant["id"]: plant["name"] for plant in self._plants}
        if user_input is not None:
            identifier = user_input[CONF_PLANT_ID]
            if identifier in choices:
                plant = next(item for item in self._plants if item["id"] == identifier)
                return await self._create_for_plant(plant)
            return self.async_show_form(
                step_id="plant",
                data_schema=vol.Schema({vol.Required(CONF_PLANT_ID): vol.In(choices)}),
                errors={"base": "unknown"},
            )
        return self.async_show_form(
            step_id="plant",
            data_schema=vol.Schema({vol.Required(CONF_PLANT_ID): vol.In(choices)}),
        )

    async def _create_for_plant(self, plant: dict[str, str]):
        await self.async_set_unique_id(plant["id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=plant["name"],
            data={
                **self._credentials,
                CONF_PLANT_ID: plant["id"],
                CONF_PLANT_NAME: plant["name"],
            },
        )
