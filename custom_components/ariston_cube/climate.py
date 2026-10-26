"""Cube S climate with manual setpoint control and cloud verification.

Heating mode changes remain disabled until the program override is confirmed.
"""

from __future__ import annotations

import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .entity import AristonEntity
from .model import as_temperature
from .states import heating_activity, heating_mode, zone_program


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Add exactly one thermostat for the selected zone 1."""
    _LOGGER.info("Ariston Cube climate platform setup invoked")
    async_add_entities([AristonCubeClimate(entry.runtime_data)])


class AristonCubeClimate(AristonEntity, ClimateEntity):
    """State of the Cube S, without competing with its scheduler."""

    _attr_name = "Cube S"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 10
    _attr_max_temp = 30

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "climate")

    async def async_added_to_hass(self) -> None:
        """Confirm HA accepted the new entity, not just its platform."""
        await super().async_added_to_hass()
        _LOGGER.info("Ariston Cube climate entity added to Home Assistant")

    @property
    def current_temperature(self) -> float | None:
        return as_temperature(self.coordinator.data.get("ZoneMeasuredTemp"))

    @property
    def target_temperature(self) -> float | None:
        return as_temperature(self.coordinator.data.get("ZoneDesiredTemp"))

    @property
    def hvac_mode(self) -> HVACMode | None:
        mode = heating_mode(self.coordinator.data)
        if mode == "off":
            return HVACMode.OFF
        if mode == "heat" and zone_program(self.coordinator.data) == "time_program":
            return HVACMode.AUTO
        return HVACMode.HEAT if mode == "heat" else None

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
            "ariston_target_temperature": self.target_temperature,
            "ariston_zone_program": zone_program(data),
            "ariston_comfort_temperature": as_temperature(data.get("ZoneComfortTemp")),
            "ariston_economy_temperature": as_temperature(data.get("ZoneEconomyTemp")),
        }

    @property
    def available(self) -> bool:
        # Keep known temperatures visible if the cloud omits an optional mode.
        return super().available and (
            self.current_temperature is not None
            or self.target_temperature is not None
        )

    async def async_set_temperature(self, **kwargs) -> None:
        if ATTR_TEMPERATURE not in kwargs:
            raise HomeAssistantError("A target temperature is required")
        # The official Ariston GALEVO client changes ZoneComfortTemp, not
        # ZoneDesiredTemp. Require heating/manual mode to preserve schedules.
        await self.coordinator.async_set_setpoint(
            "ZoneComfortTemp", kwargs[ATTR_TEMPERATURE], require_manual=True
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """OFF/HEAT/AUTO affect only the Cube S zone, not the plant."""
        option = {
            HVACMode.OFF: 0,
            HVACMode.HEAT: 2,
            HVACMode.AUTO: 3,
        }.get(hvac_mode)
        if option is None:
            raise HomeAssistantError("Unsupported heating mode")
        await self.coordinator.async_set_zone_mode(option)
