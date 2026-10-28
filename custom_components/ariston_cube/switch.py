"""Automatic flow-temperature regulation (not the weekly Cube S programme)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import AristonEntity
from .model import as_boolean
from .comfort_coordinator import AristonDhwComfortCoordinator


async def async_setup_entry(hass, entry, async_add_entities):
    comfort = AristonDhwComfortCoordinator(hass, entry.runtime_data)
    async_add_entities([
        AristonAutomaticThermoregulation(entry.runtime_data),
        AristonAcsComfort(comfort),
    ])
    entry.async_create_background_task(
        hass, comfort.async_refresh(), "Ariston Cube ACS Comfort initial read"
    )


class AristonAutomaticThermoregulation(AristonEntity, SwitchEntity):
    _attr_name = "Termoregolazione automatica"

    def __init__(self, coordinator):
        super().__init__(coordinator, "automatic_thermoregulation")

    @property
    def is_on(self) -> bool | None:
        return as_boolean(getattr(self.coordinator, "display_data", self.coordinator.data).get("AutomaticThermoregulation"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        feedback = getattr(self.coordinator, "command_feedback", lambda *keys: {})
        return feedback("AutomaticThermoregulation")

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



class AristonAcsComfort(AristonEntity, SwitchEntity):
    """Control real U6_9_2, OFF=0, Always=2. Timed=1 is not binary."""

    _attr_name = "Comfort ACS"
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator):
        super().__init__(coordinator, "web_acs_comfort")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data == 2:
            return True
        if self.coordinator.data == 0:
            return False
        return None

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data in (0, 2)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_comfort(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_comfort(False)
