"""Automatic flow-temperature regulation (not the weekly Cube S programme)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import AristonEntity
from .model import as_boolean


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AristonAutomaticThermoregulation(entry.runtime_data)])


class AristonAutomaticThermoregulation(AristonEntity, SwitchEntity):
    _attr_name = "Termoregolazione automatica"

    def __init__(self, coordinator):
        super().__init__(coordinator, "automatic_thermoregulation")

    @property
    def is_on(self) -> bool | None:
        return as_boolean(self.coordinator.data.get("AutomaticThermoregulation"))

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs) -> None:
        if not self.available:
            raise HomeAssistantError("Termoregolazione non disponibile")
        await self.coordinator.async_set_plant_control("AutomaticThermoregulation", 1)

    async def async_turn_off(self, **kwargs) -> None:
        if not self.available:
            raise HomeAssistantError("Termoregolazione non disponibile")
        await self.coordinator.async_set_plant_control("AutomaticThermoregulation", 0)
