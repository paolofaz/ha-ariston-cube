"""DHW temperature control with a fixed informational on state.

The entity's state is independent of Ariston DhwMode and Comfort ACS.
It does not imply the burner or the whole boiler is operating.

Uses the already validated mobile DhwTemp setpoint API. Comfort ACS remains
a separate R2-backed switch and can be displayed alongside this entity.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.water_heater import WaterHeaterEntity, WaterHeaterEntityFeature
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .entity import AristonEntity
from .model import as_temperature

_LOGGER = logging.getLogger(__name__)
_HARD_MIN = 36.0
_HARD_MAX = 60.0


def _safe_limit(record: dict[str, Any], key: str, fallback: float) -> float:
    value = record.get(key)
    if isinstance(value, bool):
        return fallback
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return numeric if math.isfinite(numeric) else fallback


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    _LOGGER.info("Ariston Cube water_heater platform setup invoked")
    # Old ACS number is no longer exposed. Remove only this Cube registry
    # entry; never touch legacy Ariston or Recorder/long-term statistics.
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    unique_id = f"{coordinator.plant_id}_number_DhwTemp"
    old_id = registry.async_get_entity_id("number", "ariston_cube", unique_id)
    if old_id:
        old = registry.async_get(old_id)
        if old is not None and old.config_entry_id == entry.entry_id:
            registry.async_remove(old_id)
    async_add_entities([AristonDhwWaterHeater(coordinator)])


class AristonDhwWaterHeater(AristonEntity, WaterHeaterEntity):
    """Temperature-only water heater; no operation mode or on/off commands."""

    _attr_name = "Acqua calda sanitaria"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 1.0
    _attr_min_temp = _HARD_MIN
    _attr_max_temp = _HARD_MAX
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "dhw_water_heater")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        _LOGGER.info("Ariston Cube water_heater entity added to Home Assistant")

    @property
    def target_temperature(self) -> float | None:
        return as_temperature((getattr(self.coordinator, "display_data", self.coordinator.data) or {}).get("DhwTemp"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        feedback = getattr(self.coordinator, "command_feedback", lambda *keys: {})
        return feedback("DhwTemp")

    @property
    def current_temperature(self) -> float | None:
        record = (self.coordinator.data or {}).get("DhwStorageTemperature")
        measured = as_temperature(record)
        return measured if measured is not None and 0 <= measured <= 100 else None

    @property
    def current_operation(self) -> str:
        # Display-only: never follow DhwMode or the separate Comfort ACS switch.
        return "on"

    @property
    def min_temp(self) -> float:
        record = (self.coordinator.data or {}).get("DhwTemp") or {}
        return max(_HARD_MIN, _safe_limit(record, "min", _HARD_MIN))

    @property
    def max_temp(self) -> float:
        record = (self.coordinator.data or {}).get("DhwTemp") or {}
        return min(_HARD_MAX, _safe_limit(record, "max", _HARD_MAX))

    @property
    def available(self) -> bool:
        return (
            super().available and self.target_temperature is not None
            and self.min_temp < self.max_temp
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Validate once and write via the existing guarded mobile client."""
        raw = kwargs.get(ATTR_TEMPERATURE)
        if isinstance(raw, bool):
            raise HomeAssistantError("Temperatura ACS non valida")
        try:
            target = float(raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise HomeAssistantError("Temperatura ACS non valida") from exc
        if not self.available or not math.isfinite(target):
            raise HomeAssistantError("Temperatura ACS non disponibile")
        if (not self.min_temp <= target <= self.max_temp
                or abs(target - round(target)) > 1e-6):
            raise HomeAssistantError("Temperatura ACS fuori dai limiti o dal passo di 1 °C")
        await self.coordinator.async_set_setpoint("DhwTemp", target)
