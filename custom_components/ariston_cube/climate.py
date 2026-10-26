"""Read-only representation of the Cube S thermostat.

No commands are implemented until the device's program/override semantics
have been validated with real, sanitized responses.
"""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, HVACAction, HVACMode
from homeassistant.const import UnitOfTemperature

from .entity import AristonEntity
from .model import as_temperature
from .states import heating_activity, heating_mode, zone_program


async def async_setup_entry(hass, entry, async_add_entities):
    """Add exactly one thermostat for the selected zone 1."""
    async_add_entities([AristonCubeClimate(entry.runtime_data)])


class AristonCubeClimate(AristonEntity, ClimateEntity):
    """State of the Cube S, without competing with its scheduler."""

    _attr_name = "Cube S"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = 0
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10
    _attr_max_temp = 30

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def native_current_temperature(self) -> float | None:
        return as_temperature(self.coordinator.data.get("ZoneMeasuredTemp"))

    @property
    def native_target_temperature(self) -> float | None:
        return as_temperature(self.coordinator.data.get("ZoneDesiredTemp"))

    @property
    def hvac_mode(self) -> HVACMode | None:
        mode = heating_mode(self.coordinator.data)
        return HVACMode.HEAT if mode == "heat" else HVACMode.OFF if mode == "off" else None

    @property
    def hvac_action(self) -> HVACAction | None:
        action = heating_activity(self.coordinator.data)
        if action == "heating":
            return HVACAction.HEATING
        if action == "idle":
            return HVACAction.IDLE
        if action == "off":
            return HVACAction.OFF
        return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "ariston_zone_program": zone_program(data),
            "ariston_comfort_temperature": as_temperature(data.get("ZoneComfortTemp")),
            "ariston_economy_temperature": as_temperature(data.get("ZoneEconomyTemp")),
        }

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.native_current_temperature is not None
            and self.native_target_temperature is not None
            and self.hvac_mode is not None
        )
