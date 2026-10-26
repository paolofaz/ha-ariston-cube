"""Read-only domestic hot water state from the Ariston cloud."""

from __future__ import annotations

from homeassistant.components.water_heater import WaterHeaterEntity
from homeassistant.const import UnitOfTemperature

from .entity import AristonEntity
from .model import as_temperature
from .states import hot_water_operation


async def async_setup_entry(hass, entry, async_add_entities):
    """Add one DHW entity without any command interface."""
    async_add_entities([AristonDomesticHotWater(entry.runtime_data)])


class AristonDomesticHotWater(AristonEntity, WaterHeaterEntity):
    """Display ACS target, optional storage temperature and current mode."""

    _attr_name = "Acqua calda sanitaria"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = 0
    _attr_min_temp = 35
    _attr_max_temp = 65
    _attr_target_temperature_step = 1
    _attr_operation_list = [
        "off", "scheduled", "always_active",
        "heat_cool_heat_pump", "heat_cool_heat_pump_40", "green",
    ]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "water_heater")

    @property
    def native_target_temperature(self) -> float | None:
        return as_temperature(self.coordinator.data.get("DhwTemp"))

    @property
    def native_current_temperature(self) -> float | None:
        # CLAS ONE may not have an ACS storage tank; do not fake a sensor.
        value = as_temperature(self.coordinator.data.get("DhwStorageTemperature"))
        return value if value is not None and value > 0 else None

    @property
    def current_operation(self) -> str | None:
        return hot_water_operation(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self.coordinator.data
        return {
            "ariston_comfort_temperature": as_temperature(
                data.get("DhwTimeProgComfortTemp")
            ),
            "ariston_economy_temperature": as_temperature(
                data.get("DhwTimeProgEconomyTemp")
            ),
        }

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.native_target_temperature is not None
            and self.current_operation is not None
        )
