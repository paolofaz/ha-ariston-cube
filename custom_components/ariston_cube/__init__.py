"""Ariston Cube integration, configured through the UI."""

from __future__ import annotations

import logging

import aiohttp

from .const import DOMAIN
from .weekly_changes import preview_weekly_change
from .weekly_clone import preview_clone_weekly_days

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession, async_create_clientsession

from .api import AristonClient
from .coordinator import AristonCoordinator
from .frontend import async_register_weekly_card

_LOGGER = logging.getLogger(__name__)


_PREVIEW_SERVICE = "preview_weekly_change"


async def async_setup(hass, config) -> bool:
    """Register only six supported services: four Cube S, two gas reads.

    Obsolete experiment/probe endpoints and manual gas-statistics writes are
    intentionally NOT registered in 1.3. The weekly card uses only these
    production services. The independent automatic gas aligner is unchanged.
    """
    import voluptuous as vol
    from homeassistant.core import SupportsResponse
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.config_entries import ConfigEntryState
    from .api import AristonError
    from .commands import CommandRejected
    from .energy_alignment import AlignmentRejected, EnergyHourAligner

    def get_coordinator():
        entries = [
            entry for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise HomeAssistantError("Exactly one loaded Ariston Cube entry required")
        return entries[0].runtime_data

    async def refresh_weekly(coordinator, operation: str) -> None:
        """One best-effort read-only calendar refresh after confirmed writes."""
        weekly = getattr(coordinator, "weekly_coordinator", None)
        if weekly is not None:
            try:
                await weekly.async_refresh()
            except Exception as exc:
                _LOGGER.warning(
                    "Cube S %s confirmed but calendar refresh failed (%s)",
                    operation, type(exc).__name__,
                )

    def change_values(data):
        return {
            "from_time": data.get("from_time", ""),
            "to_time": data.get("to_time", ""),
            "end_time": data.get("end_time", ""),
            "preset": data.get("preset", ""),
        }

    async def preview_change(call):
        """Read-only GET and guarded preview of move/add/remove."""
        coordinator = get_coordinator()
        try:
            source = await coordinator.client.async_read_weekly_program(
                coordinator.plant_id
            )
            proposal = preview_weekly_change(
                source, call.data["day"], call.data["operation"],
                **change_values(call.data),
            )
        except (AristonError, ValueError) as exc:
            raise HomeAssistantError(str(exc)) from exc
        return {
            "status": "preview_only_no_cloud_write",
            "weekday": proposal["weekday"],
            "operation": proposal["operation"],
            "before": proposal["before"],
            "after": proposal["after"],
            "changed": proposal["changed"],
            "source_fingerprint": proposal["source_fingerprint"],
            "can_submit": False,
        }

    async def write_change(call):
        """One user-approved cloud POST, never retried after ambiguity."""
        coordinator = get_coordinator()
        try:
            result = await coordinator.client.async_write_weekly_change(
                coordinator.plant_id,
                call.data["day"],
                call.data["operation"],
                expected_fingerprint=call.data["expected_fingerprint"],
                **change_values(call.data),
            )
        except CommandRejected as exc:
            # The refusal happened before a cloud write. The frontend
            # distinguishes this from an ambiguous post-write failure.
            raise HomeAssistantError("Nessuna modifica inviata: " + str(exc)) from exc
        except AristonError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await refresh_weekly(coordinator, "edit")
        return result

    change_schema = {
        vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
        vol.Required("operation"): vol.In(("move", "add", "remove")),
        vol.Optional("from_time", default=""): str,
        vol.Optional("to_time", default=""): str,
        vol.Optional("end_time", default=""): str,
        vol.Optional("preset", default=""): vol.In(("", "Comfort", "Economy")),
    }
    hass.services.async_register(
        DOMAIN, "preview_weekly_change", preview_change,
        schema=vol.Schema(change_schema),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "write_weekly_change", write_change,
        schema=vol.Schema({
            **change_schema,
            vol.Required("expected_fingerprint"): vol.Match(r"^[a-f0-9]{64}$"),
            vol.Required("confirm"): vol.Equal(True),
        }),
        supports_response=SupportsResponse.ONLY,
    )

    clone_fields = {
        vol.Required("source_day"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=6)
        ),
        vol.Required("destinations"): [
            vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
        ],
    }

    async def preview_clone(call):
        """One current seven-day cloud read, no write."""
        coordinator = get_coordinator()
        try:
            source = await coordinator.client.async_read_weekly_program(
                coordinator.plant_id
            )
            return preview_clone_weekly_days(
                source, call.data["source_day"], call.data["destinations"]
            )
        except (AristonError, ValueError) as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def write_clone(call):
        """Fingerprint-guarded write of selected weekdays, one POST only."""
        coordinator = get_coordinator()
        try:
            result = await coordinator.client.async_clone_weekly_days(
                coordinator.plant_id, call.data["source_day"],
                call.data["destinations"], call.data["expected_fingerprint"],
            )
        except CommandRejected as exc:
            raise HomeAssistantError("Nessuna modifica inviata: " + str(exc)) from exc
        except AristonError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await refresh_weekly(coordinator, "clone")
        return result

    hass.services.async_register(
        DOMAIN, "preview_weekly_clone", preview_clone,
        schema=vol.Schema(clone_fields),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "clone_weekly_days", write_clone,
        schema=vol.Schema({
            **clone_fields,
            vol.Required("expected_fingerprint"): vol.Match(r"^[a-f0-9]{64}$"),
            vol.Required("confirm"): vol.Equal(True),
        }),
        supports_response=SupportsResponse.ONLY,
    )

    def get_energy_aligner():
        coordinator = get_coordinator()
        if getattr(coordinator, "smc_coordinator", None) is None:
            raise HomeAssistantError("Gas coordinator is not ready")
        aligner = getattr(coordinator, "energy_hour_aligner", None)
        if aligner is None:
            aligner = EnergyHourAligner(hass, coordinator)
            coordinator.energy_hour_aligner = aligner
        return aligner

    async def inspect_energy_hour(call):
        """Read only the real existing Recorder hourly statistics."""
        try:
            return await get_energy_aligner().inspect_hour(call.data["target_start"])
        except AlignmentRejected as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def inspect_auto_energy_hour(call):
        """Read only the latest in-memory automatic-run reports."""
        runner = getattr(get_coordinator(), "energy_hour_runner", None)
        if runner is None:
            return {
                "status": "read_only_auto_energy_hour_status",
                "enabled": False, "last_attempt": None, "recent_attempts": [],
            }
        return runner.status()

    hass.services.async_register(
        DOMAIN, "inspect_energy_hour_alignment", inspect_energy_hour,
        schema=vol.Schema({vol.Required("target_start"): str}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "inspect_automatic_energy_hour_alignment",
        inspect_auto_energy_hour,
        supports_response=SupportsResponse.ONLY,
    )
    return True


PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.WATER_HEATER, Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.CALENDAR)


async def async_setup_entry(hass, entry) -> bool:
    """Use a token-authenticated client and fetch the initial snapshot."""
    _LOGGER.info("Ariston Cube 1.2.0 starting; platforms=%s", ", ".join(str(getattr(p, "value", p)) for p in PLATFORMS))
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
    # HA normally invokes async_setup() first. Guarded fallback for the
    # supported action set, including on integrations upgraded in place.
    services = getattr(hass, "services", None)
    if services is not None and not services.has_service(DOMAIN, _PREVIEW_SERVICE):
        await async_setup(hass, {})
    try:
        await async_register_weekly_card(hass)
    except Exception as exc:  # noqa: BLE001
        # Optional UI must never prevent boiler entity setup.
        _LOGGER.warning("Cube S weekly card could not be registered: %s", type(exc).__name__)
    # Single local-time scheduler, only after all entity platforms finished
    # initial setup. Manual actions stay available independently.
    from homeassistant.helpers.event import async_track_time_change
    from .energy_automation import AutomaticEnergyHourRunner

    runner = AutomaticEnergyHourRunner(hass, coordinator)
    # HA invokes async callbacks for local HH:15:00. The runner filters
    # even hours, validates the exact eligible bucket, and does NOT retry.
    unsubscribe = async_track_time_change(
        hass, runner.async_tick, minute=15, second=0
    )
    coordinator.energy_hour_runner = runner
    coordinator.energy_hour_unsubscribe = unsubscribe
    _LOGGER.info(
        "Ariston Cube Energy-hour automatic alignment enabled at odd local hours :15"
    )
    _LOGGER.info("Ariston Cube 1.2.0 platform setup dispatched")
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Unload entity platforms; Home Assistant cleans up the client session."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            runner = getattr(coordinator, "energy_hour_runner", None)
            if runner is not None:
                runner.stop()
            unsubscribe = getattr(
                coordinator, "energy_hour_unsubscribe", None
            )
            if unsubscribe is not None:
                unsubscribe()
                coordinator.energy_hour_unsubscribe = None
    return unloaded
