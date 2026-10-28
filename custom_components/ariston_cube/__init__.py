"""Ariston Cube integration, configured through the UI."""

from __future__ import annotations

import logging

import aiohttp

from .const import DOMAIN
from .weekly_preview import preview_one_boundary_move
from .weekly_changes import preview_weekly_change
from .weekly_clone import preview_clone_weekly_days

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession, async_create_clientsession

from .api import AristonClient
from .coordinator import AristonCoordinator
from .frontend import async_register_weekly_card

_LOGGER = logging.getLogger(__name__)


_PREVIEW_SERVICE = "preview_weekly_slice"


async def async_setup(hass, config) -> bool:
    """Register an offline-change preview using one fresh cloud GET."""
    import voluptuous as vol

    from homeassistant.core import SupportsResponse
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.config_entries import ConfigEntryState

    from .api import AristonError
    from .energy_alignment import AlignmentRejected, EnergyHourAligner

    schema = vol.Schema({
        vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
        vol.Required("from_time"): str,
        vol.Required("to_time"): str,
    })

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

    async def probe_weekly(call):
        """Request only OPTIONS metadata for the known schedule-read path."""
        entries = [
            entry for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise HomeAssistantError("Exactly one loaded Ariston Cube entry is required")
        coordinator = entries[0].runtime_data
        try:
            return await coordinator.client.async_probe_weekly_methods(
                coordinator.plant_id
            )
        except AristonError as exc:
            raise HomeAssistantError("Cube S OPTIONS probe failed") from exc

    hass.services.async_register(
        DOMAIN, _PREVIEW_SERVICE, preview,
        schema=schema, supports_response=SupportsResponse.ONLY,
    )
    async def test_write_weekly(call):
        """ONLY a user action with a matching preview fingerprint may POST."""
        from .commands import CommandRejected

        entries = [
            entry for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise HomeAssistantError("Exactly one loaded Ariston Cube entry is required")
        coordinator = entries[0].runtime_data
        try:
            result = await coordinator.client.async_test_write_weekly_slice(
                coordinator.plant_id,
                call.data["day"], call.data["from_time"],
                call.data["to_time"], call.data["expected_fingerprint"],
            )
        except (AristonError, CommandRejected) as exc:
            raise HomeAssistantError(str(exc)) from exc
        weekly = getattr(coordinator, "weekly_coordinator", None)
        if weekly is not None:
            try:
                await weekly.async_refresh()
            except Exception as exc:  # optional refresh is not a second write
                _LOGGER.warning(
                    "Cube S schedule changed, but calendar refresh failed (%s)",
                    type(exc).__name__,
                )
        return result

    write_schema = vol.Schema({
        vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
        vol.Required("from_time"): str,
        vol.Required("to_time"): str,
        vol.Required("expected_fingerprint"): vol.Match(r"^[a-f0-9]{64}$"),
        vol.Required("confirm"): vol.Equal(True),
    })

    async def preview_change(call):
        """Fresh cloud GET and read-only before/after for one weekly edit."""
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
            proposal = preview_weekly_change(
                source, call.data["day"], call.data["operation"],
                from_time=call.data.get("from_time", ""),
                to_time=call.data.get("to_time", ""),
                end_time=call.data.get("end_time", ""),
                preset=call.data.get("preset", ""),
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
        """One user-triggered POST after fresh fingerprint validation."""
        from .commands import CommandRejected

        entries = [
            entry for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise HomeAssistantError("Exactly one loaded Ariston Cube entry is required")
        coordinator = entries[0].runtime_data
        try:
            result = await coordinator.client.async_write_weekly_change(
                coordinator.plant_id, call.data["day"], call.data["operation"],
                from_time=call.data.get("from_time", ""),
                to_time=call.data.get("to_time", ""),
                end_time=call.data.get("end_time", ""),
                preset=call.data.get("preset", ""),
                expected_fingerprint=call.data["expected_fingerprint"],
            )
        except CommandRejected as exc:
            # This error is raised by the fresh-read preflight BEFORE the POST.
            # Distinguish a harmless refusal from an ambiguous cloud write.
            raise HomeAssistantError("Nessuna modifica inviata: " + str(exc)) from exc
        except AristonError as exc:
            raise HomeAssistantError(str(exc)) from exc
        weekly = getattr(coordinator, "weekly_coordinator", None)
        if weekly is not None:
            try:
                await weekly.async_refresh()
            except Exception as exc:
                _LOGGER.warning(
                    "Cube S schedule written; calendar refresh failed (%s)",
                    type(exc).__name__,
                )
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

    async def clone_preview(call):
        """Read-only preview for copying one source to several weekdays."""
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
            return preview_clone_weekly_days(
                source, call.data["source_day"], call.data["destinations"]
            )
        except (AristonError, ValueError) as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def clone_write(call):
        """Explicitly approved ONE POST to update all selected weekdays."""
        from .commands import CommandRejected

        entries = [
            entry for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise HomeAssistantError("Exactly one loaded Ariston Cube entry is required")
        coordinator = entries[0].runtime_data
        try:
            result = await coordinator.client.async_clone_weekly_days(
                coordinator.plant_id, call.data["source_day"],
                call.data["destinations"], call.data["expected_fingerprint"],
            )
        except CommandRejected as exc:
            raise HomeAssistantError("Nessuna modifica inviata: " + str(exc)) from exc
        except AristonError as exc:
            raise HomeAssistantError(str(exc)) from exc
        weekly = getattr(coordinator, "weekly_coordinator", None)
        if weekly is not None:
            try:
                await weekly.async_refresh()
            except Exception as exc:
                _LOGGER.warning(
                    "Cube S cloned week but calendar refresh failed (%s)",
                    type(exc).__name__,
                )
        return result

    clone_fields = {
        vol.Required("source_day"): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=6)
        ),
        vol.Required("destinations"): [
            vol.All(vol.Coerce(int), vol.Range(min=0, max=6))
        ],
    }
    hass.services.async_register(
        DOMAIN, "preview_weekly_clone", clone_preview,
        schema=vol.Schema(clone_fields),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "clone_weekly_days", clone_write,
        schema=vol.Schema({
            **clone_fields,
            vol.Required("expected_fingerprint"): vol.Match(r"^[a-f0-9]{64}$"),
            vol.Required("confirm"): vol.Equal(True),
        }),
        supports_response=SupportsResponse.ONLY,
    )

    def get_energy_aligner():
        """Use only the existing Smc coordinator and existing sensor identities."""
        entries = [
            entry for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]
        if len(entries) != 1:
            raise HomeAssistantError("Exactly one loaded Ariston Cube entry required")
        coordinator = entries[0].runtime_data
        if getattr(coordinator, "smc_coordinator", None) is None:
            raise HomeAssistantError("Gas coordinator is not ready")
        aligner = getattr(coordinator, "energy_hour_aligner", None)
        if aligner is None:
            aligner = EnergyHourAligner(hass, coordinator)
            coordinator.energy_hour_aligner = aligner
        return aligner

    async def preview_energy_hour(call):
        try:
            return await get_energy_aligner().preview()
        except AlignmentRejected as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def inspect_energy_hour(call):
        """READ ONLY: inspect existing hourly sums without any Recorder writes."""
        try:
            return await get_energy_aligner().inspect_hour(call.data["target_start"])
        except AlignmentRejected as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def apply_energy_hour(call):
        """Exactly one fingerprint-guarded manual correction per eligible sensor."""
        try:
            return await get_energy_aligner().apply(call.data["fingerprint"])
        except AlignmentRejected as exc:
            raise HomeAssistantError(str(exc)) from exc

    hass.services.async_register(
        DOMAIN, "preview_energy_hour_alignment", preview_energy_hour,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "inspect_energy_hour_alignment", inspect_energy_hour,
        schema=vol.Schema({vol.Required("target_start"): str}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "apply_energy_hour_alignment", apply_energy_hour,
        schema=vol.Schema({
            vol.Required("fingerprint"): vol.Match(r"^[a-f0-9]{64}$"),
            vol.Required("confirm"): vol.Equal(True),
        }),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN, "probe_weekly_methods", probe_weekly,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "test_write_weekly_slice", test_write_weekly,
        schema=write_schema, supports_response=SupportsResponse.ONLY,
    )
    return True


PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.WATER_HEATER, Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.CALENDAR)


async def async_setup_entry(hass, entry) -> bool:
    """Use a token-authenticated client and fetch the initial snapshot."""
    _LOGGER.info("Ariston Cube 1.1.1-rc.1 starting; platforms=%s", ", ".join(str(getattr(p, "value", p)) for p in PLATFORMS))
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
    # HA usually invokes async_setup() before config-entry setup. Keep a
    # guarded fallback so the experimental actions also appear on upgrades.
    services = getattr(hass, "services", None)
    if services is not None and not services.has_service(DOMAIN, _PREVIEW_SERVICE):
        await async_setup(hass, {})
    try:
        await async_register_weekly_card(hass)
    except Exception as exc:  # noqa: BLE001
        # Optional UI must never prevent boiler entity setup.
        _LOGGER.warning("Cube S weekly card could not be registered: %s", type(exc).__name__)
    _LOGGER.info("Ariston Cube 1.1.1-rc.1 platform setup dispatched")
    return True


async def async_unload_entry(hass, entry) -> bool:
    """Unload entity platforms; Home Assistant cleans up the client session."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
