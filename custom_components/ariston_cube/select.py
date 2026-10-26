"""Whole-boiler mode selector, separate from ZoneMode AUTO schedule."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import AristonEntity
from .states import enum_code

_OPTIONS = {"Modalità inverno": 1, "Modalità estate": 0, "Spenta": 5}
_BY_CODE = {code: name for name, code in _OPTIONS.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AristonPlantModeSelect(entry.runtime_data)])


class AristonPlantModeSelect(AristonEntity, SelectEntity):
    _attr_name = "Modalità caldaia"
    _attr_options = list(_OPTIONS)

    def __init__(self, coordinator):
        super().__init__(coordinator, "plant_mode")

    @property
    def current_option(self) -> str | None:
        return _BY_CODE.get(enum_code(self.coordinator.data.get("PlantMode")))

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
