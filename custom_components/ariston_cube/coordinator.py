"""Scheduled polling and parsing for one configured Ariston plant."""

from __future__ import annotations

from datetime import timedelta
from collections.abc import Awaitable, Callable
import logging
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AristonAuthError, AristonClient, AristonError
from .commands import CommandRejected
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
        # UI-only pending overlay; verified cloud snapshots remain untouched.
        # Never feed a guessed value back into Ariston's compare-and-set
        # request, the Smc ledger or HA Recorder.
        self._pending_command: tuple[str, float | int] | None = None
        self._last_command: tuple[str, str] | None = None

    @property
    def display_data(self) -> dict[str, dict[str, Any]]:
        """Optimistic view ONLY for Lovelace control entities.

        Real self.data remains the last verified cloud response. In-flight
        polling cannot remove the preview or change the validated command.
        """
        snapshot = self.data or {}
        pending = self._pending_command
        if pending is None:
            return snapshot
        item_id, value = pending
        current = snapshot.get(item_id)
        if not isinstance(current, dict):
            return snapshot
        return {**snapshot, item_id: {**current, "value": value}}

    def command_feedback(self, *item_ids: str) -> dict[str, str | bool]:
        """Compact status for the affected HA controls; no credentials."""
        if self._pending_command is not None:
            if self._pending_command[0] in item_ids:
                return {"ariston_comando_in_corso": True,
                        "ariston_comando_esito": "in_attesa"}
            return {}
        if self._last_command is not None and self._last_command[0] in item_ids:
            return {"ariston_comando_in_corso": False,
                    "ariston_comando_esito": self._last_command[1]}
        return {}

    async def _async_command_with_preview(
        self, item_id: str, value: float | int,
        operation: Callable[[], Awaitable[dict[str, dict[str, Any]]]],
    ) -> None:
        """Publish a temporary desired value, then commit OR roll back.

        At most one control command in flight; no background POST, no retry.
        The underlying API retains its fresh GET/POST/GET validation, and
        a failed or ambiguous response NEVER becomes a confirmed state.
        """
        if self._pending_command is not None:
            raise HomeAssistantError(
                "Un altro comando Ariston è in corso: attendi la conferma"
            )
        snapshot = self.data or {}
        if not isinstance(snapshot.get(item_id), dict):
            raise HomeAssistantError("Valore Ariston non disponibile")
        self._pending_command = (item_id, value)
        self._last_command = (item_id, "in_attesa")
        self.async_update_listeners()
        try:
            confirmed = await operation()
        except Exception as exc:
            self._pending_command = None
            # Connection timeouts and delayed readback are indeterminate:
            # inform the UI and wait for the normal read-only cloud poll.
            if isinstance(exc, AristonError):
                status = "non_confermato"
            else:
                status = "rifiutato"
            self._last_command = (item_id, status)
            self.async_update_listeners()  # roll back to verified snapshot
            raise
        else:
            self._pending_command = None
            self._last_command = (item_id, "confermato")
            self.async_set_updated_data(confirmed)


    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            raw = await self.client.async_read_main(self.plant_id)
            return parse_main_data(raw)
        except AristonAuthError as exc:
            raise ConfigEntryAuthFailed("Ariston authentication failed") from exc
        except (AristonError, ValueError) as exc:
            raise UpdateFailed("Unable to refresh Ariston data") from exc

    async def async_set_setpoint(
        self, item_id: str, value: float, *, require_manual: bool = False
    ) -> None:
        """Immediate UI preview, then existing strict cloud verification."""
        async def write():
            try:
                return await self.client.async_set_setpoint(
                    self.plant_id, item_id, value, require_manual=require_manual
                )
            except CommandRejected as exc:
                raise HomeAssistantError(str(exc)) from exc
            except AristonError as exc:
                _LOGGER.warning("Ariston setpoint not confirmed: %s", type(exc).__name__)
                raise

        await self._async_command_with_preview(item_id, value, write)

    async def async_set_zone_mode(self, mode: int) -> None:
        """Publish AUTO/MANUAL immediately; verify once in cloud."""
        async def write():
            try:
                return await self.client.async_set_zone_mode(self.plant_id, mode)
            except CommandRejected as exc:
                raise HomeAssistantError(str(exc)) from exc
            except AristonError as exc:
                _LOGGER.warning("Ariston zone mode not confirmed: %s", type(exc).__name__)
                raise

        await self._async_command_with_preview("ZoneMode", mode, write)

    async def async_set_plant_control(self, item_id: str, value: int) -> None:
        """Keep the same explicit plant control, with pending UI feedback."""
        async def write():
            try:
                return await self.client.async_set_plant_control(
                    self.plant_id, item_id, value
                )
            except CommandRejected as exc:
                raise HomeAssistantError(str(exc)) from exc
            except AristonError as exc:
                _LOGGER.warning("Ariston plant control not confirmed: %s", type(exc).__name__)
                raise

        await self._async_command_with_preview(item_id, value, write)
