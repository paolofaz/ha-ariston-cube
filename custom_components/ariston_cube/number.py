"""Cube S Comfort and Economy numeric controls (ACS uses water_heater)."""

from __future__ import annotations

import logging
import math

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError

from .entity import AristonEntity
from .model import as_temperature

_LOGGER = logging.getLogger(__name__)

# Domain-specific caps: the cloud min/max are also enforced by commands.py.
_NUMBERS: tuple[tuple[str, str, float, float, float], ...] = (
    ("ZoneEconomyTemp", "heating_economy", 10.0, 30.0, 0.5),
    ("ZoneComfortTemp", "heating_comfort", 10.0, 30.0, 0.5),
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Register numeric controls for heating Comfort and Economy."""
    _LOGGER.info("Ariston Cube number platform setup invoked")
    async_add_entities(
        AristonCubeNumber(entry.runtime_data, field, key, lower, upper, step)
        for field, key, lower, upper, step in _NUMBERS
    )


class AristonCubeNumber(AristonEntity, NumberEntity):
    """Show cloud current value; change using a fresh validated read."""

    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator, field: str, translation_key: str,
        lower: float, upper: float, step: float,
    ) -> None:
        super().__init__(coordinator, f"number_{field}")
        self._field = field
        self._attr_translation_key = translation_key
        self._attr_native_min_value = lower
        self._attr_native_max_value = upper
        self._attr_native_step = step

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        _LOGGER.info("Ariston Cube number entity added to Home Assistant")

    @property
    def native_value(self) -> float | None:
        return as_temperature(self.coordinator.data.get(self._field))

    @property
    def native_min_value(self) -> float:
        """Use intersection of safe caps and confirmed cloud metadata."""
        item = self.coordinator.data.get(self._field) or {}
        try:
            limit = float(item.get("min"))
        except (TypeError, ValueError, OverflowError):
            return self._attr_native_min_value
        if not math.isfinite(limit):
            return self._attr_native_min_value
        return max(self._attr_native_min_value, limit)

    @property
    def native_max_value(self) -> float:
        item = self.coordinator.data.get(self._field) or {}
        try:
            limit = float(item.get("max"))
        except (TypeError, ValueError, OverflowError):
            return self._attr_native_max_value
        if not math.isfinite(limit):
            return self._attr_native_max_value
        return min(self._attr_native_max_value, limit)

    @property
    def native_step(self) -> float:
        # ACS must always be whole-degree steps even if cloud is more granular.
        # Comfort/Economy use the device's step when it is a safe multiple of 0.5.
        if self._field == "DhwTemp":
            return 1.0
        item = self.coordinator.data.get(self._field) or {}
        value = item.get("step")
        try:
            step = float(value)
        except (TypeError, ValueError, OverflowError):
            return self._attr_native_step
        if math.isfinite(step) and 0 < step <= 1 and (step / 0.5).is_integer():
            return step
        return self._attr_native_step

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.native_value is not None
            and self.native_min_value < self.native_max_value
        )

    async def async_set_native_value(self, value: float) -> None:
        if self.native_value is None:
            raise HomeAssistantError("Ariston has not supplied the current value")
        if not self.native_min_value <= value <= self.native_max_value:
            raise HomeAssistantError("Target temperature outside valid limits")
        # Prevent calls with an unsupported increment even if made outside the UI.
        if not math.isfinite(value) or abs(value / self.native_step - round(value / self.native_step)) > 1e-6:
            raise HomeAssistantError("Target temperature is not on a valid step")
        await self.coordinator.async_set_setpoint(self._field, value)
