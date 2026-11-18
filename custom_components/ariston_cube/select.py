"""Whole-boiler selector and Cube S AUTO/Manuale schedule selector."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import AristonEntity
from .states import enum_code

_OPTIONS = {"Modalità inverno": 1, "Modalità estate": 0, "Spenta": 5}
_BY_CODE = {code: name for name, code in _OPTIONS.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    # One local timer per plant; the existing cloud modes are unchanged.
    if getattr(entry, "entry_id", None) is not None:
        from .schedule_coordinator import get_or_create_weekly_coordinator
        from .temporary_manual import TemporaryManualController

        weekly = get_or_create_weekly_coordinator(hass, entry)
        temporary = TemporaryManualController(hass, entry, coordinator, weekly)
        coordinator.temporary_manual = temporary
        try:
            await temporary.async_initialize()
        except Exception:
            temporary.stop()
            coordinator.temporary_manual = None
            raise
        entry.async_on_unload(temporary.stop)
    async_add_entities([
        AristonPlantModeSelect(entry.runtime_data),
        AristonZoneProgrammeSelect(entry.runtime_data),
    ])


class AristonPlantModeSelect(AristonEntity, SelectEntity):
    _attr_name = "Modalità caldaia"
    _attr_options = list(_OPTIONS)

    def __init__(self, coordinator):
        super().__init__(coordinator, "plant_mode")

    @property
    def current_option(self) -> str | None:
        return _BY_CODE.get(enum_code(getattr(self.coordinator, "display_data", self.coordinator.data).get("PlantMode")))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        feedback = getattr(self.coordinator, "command_feedback", lambda *keys: {})
        return feedback("PlantMode")

    @property
    def available(self) -> bool:
        row = self.coordinator.data.get("PlantMode") or {}
        return (
            super().available and self.current_option is not None
            and isinstance(row.get("options"), list)
            and bool(row["options"])
        )

    async def async_select_option(self, option: str) -> None:
        if option not in _OPTIONS:
            raise HomeAssistantError("Modalità caldaia non supportata")
        if not self.available:
            raise HomeAssistantError("Modalità caldaia non disponibile")
        await self.coordinator.async_set_plant_control("PlantMode", _OPTIONS[option])


# These choices map to the exact ZoneMode values used by the climate entity.
# ZoneMode=0 (off) and ZoneMode=1 (economy) are not relabelled "Manuale".
_ZONE_PROGRAM_OPTIONS = {"AUTO": 3, "Manuale": 2}
_ZONE_PROGRAM_BY_CODE = {code: option for option, code in _ZONE_PROGRAM_OPTIONS.items()}


class AristonZoneProgrammeSelect(AristonEntity, SelectEntity):
    """Select Cube S time programme or manual mode, never plant operation."""

    _attr_name = "Modalità riscaldamento"
    _attr_options = [*_ZONE_PROGRAM_OPTIONS, "Manuale temporaneo"]
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator):
        super().__init__(coordinator, "zone_program_mode")

    @property
    def current_option(self) -> str | None:
        data = getattr(self.coordinator, "display_data", self.coordinator.data) or {}
        code = enum_code(data.get("ZoneMode"))
        temporary = getattr(self.coordinator, "temporary_manual", None)
        if code == 2 and temporary is not None and temporary.active:
            return "Manuale temporaneo"
        return _ZONE_PROGRAM_BY_CODE.get(code)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        feedback = getattr(self.coordinator, "command_feedback", lambda *keys: {})
        temporary = getattr(self.coordinator, "temporary_manual", None)
        return {
            **feedback("ZoneMode"),
            **(temporary.attributes() if temporary is not None else {}),
        }

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        data = self.coordinator.data or {}
        # The plant's season is separate from the saved Cube S programme:
        # in summer/off mode, expose no write control.
        if enum_code(data.get("PlantMode")) not in (1, 2):
            return False
        if self.current_option is None:
            return False
        zone = data.get("ZoneMode")
        if not isinstance(zone, dict):
            return False
        declared = zone.get("options")
        if not isinstance(declared, list):
            return False
        allowed = {
            code for option in declared
            if (code := enum_code({"value": option})) is not None
        }
        return set(_ZONE_PROGRAM_OPTIONS.values()).issubset(allowed)

    async def async_select_option(self, option: str) -> None:
        if option not in (*_ZONE_PROGRAM_OPTIONS, "Manuale temporaneo"):
            raise HomeAssistantError("Modalità riscaldamento non supportata")
        if not self.available:
            raise HomeAssistantError("Modalità riscaldamento non disponibile")
        temporary = getattr(self.coordinator, "temporary_manual", None)
        if option == "Manuale temporaneo":
            if temporary is None:
                raise HomeAssistantError("Gestione Manuale temporaneo non disponibile")
            await temporary.async_activate()
        elif temporary is not None:
            await temporary.async_select_permanent(_ZONE_PROGRAM_OPTIONS[option])
        else:
            await self.coordinator.async_set_zone_mode(_ZONE_PROGRAM_OPTIONS[option])
