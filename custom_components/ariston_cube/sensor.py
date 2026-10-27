"""Original temperature sensors and the Cube S weekly programme."""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfPressure, UnitOfVolume

from .entity import AristonEntity
from .model import as_temperature
from .schedule_coordinator import get_or_create_weekly_coordinator
from .smc_coordinator import AristonSmcCoordinator
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers import entity_registry as er
from .weekly_program import daily_description

DESCRIPTIONS = (
    SensorEntityDescription(
        key="ZoneMeasuredTemp", translation_key="room_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ZoneDesiredTemp", translation_key="heating_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="DhwTemp", translation_key="dhw_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),

    SensorEntityDescription(
        key="ChFlowTemp", translation_key="flow_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ChFlowSetpointTemp", translation_key="flow_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="OutsideTemp", translation_key="outside_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="HeatingCircuitPressure", translation_key="heating_pressure",
        native_unit_of_measurement=UnitOfPressure.BAR,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    schedule = get_or_create_weekly_coordinator(hass, entry)
    entities = [AristonTemperature(coordinator, description) for description in DESCRIPTIONS]
    entities.append(AristonWeeklySchedule(schedule))
    smc = AristonSmcCoordinator(hass, coordinator, entry_id=entry.entry_id)
    entities.extend([
        AristonPhysicalGas(smc, "heating_smc_today", "heating_smc_today"),
        AristonPhysicalGas(smc, "dhw_smc_today", "dhw_smc_today"),
        AristonPhysicalGas(smc, "heating_smc_2h", "heating_smc_2h"),
        AristonPhysicalGas(smc, "dhw_smc_2h", "dhw_smc_2h"),
        AristonCumulativeGas(smc, "total_heating_smc", "heating_gas_cumulative"),
        AristonCumulativeGas(smc, "total_dhw_smc", "dhw_gas_cumulative"),
    ])
    # The diagnostic entity was intentionally temporary in 0.8.7/0.8.8.
    # Remove ONLY that exact registered Cube entity, never Recorder history,
    # legacy Ariston entities, or the verified raw Smc sensor registry entries.
    registry = er.async_get(hass)
    old_unique_id = f"{coordinator.plant_id}_smc_midnight_debug"
    old_entity_id = registry.async_get_entity_id(
        "sensor", "ariston_cube", old_unique_id
    )
    if old_entity_id:
        old_entry = registry.async_get(old_entity_id)
        if old_entry and old_entry.config_entry_id == entry.entry_id:
            registry.async_remove(old_entity_id)

    async_add_entities(entities)

    # Ariston publishes its completed two-hour gas buckets on local-clock
    # boundaries. Read at :10 and :40 after every even hour including
    # midnight, while the 22:00–00:00 bucket remains available until 02:00.
    # This avoids missing the final day bucket during the 02:00 reset.
    async def _refresh_smc(_now):
        await smc.async_refresh()

    unsubscribe = async_track_time_change(
        hass, _refresh_smc,
        hour=tuple(range(0, 24, 2)),
        minute=(10, 40),
        second=0,
    )
    entry.async_on_unload(unsubscribe)
    entry.async_create_background_task(
        hass, smc.async_refresh(), "Ariston Cube Smc initial read"
    )


class AristonTemperature(AristonEntity, SensorEntity):
    """Temperature read from Ariston dataItems."""

    def __init__(self, coordinator, description):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        if self.entity_description.key == "HeatingCircuitPressure":
            record = self.record
            if record is None or record.get("unit") not in ("bar", "Bar", "BAR"):
                return None
            result = as_temperature(record)
            return result if result is not None and 0 <= result <= 10 else None
        if self.entity_description.key == "OutsideTemp":
            # Cloud often returns a sentinel equal to its max when no physical
            # outside probe is present; do not present that as real weather.
            record = self.record
            value = as_temperature(record)
            if value is None or value < -60 or value > 70:
                return None
            max_value = record.get("max") if record else None
            if max_value is not None:
                try:
                    if value == float(max_value):
                        return None
                except (ValueError, TypeError, OverflowError):
                    return None
            return value
        if self.entity_description.key in ("ChFlowTemp", "ChFlowSetpointTemp"):
            value = as_temperature(self.record)
            return value if value is not None and 0 <= value <= 120 else None
        return as_temperature(self.record)

    @property
    def available(self):
        return super().available and self.native_value is not None



class AristonWeeklySchedule(AristonEntity, SensorEntity):
    """Read-only day-by-day view of the schedule stored on the Cube S."""

    _attr_name = "Programma settimanale Cube S"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, schedule_coordinator) -> None:
        super().__init__(schedule_coordinator, "weekly_program")

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return "Disponibile"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}
        return {
            "gruppi_programma": data["plan_count"],
            **{
                day: daily_description(slices)
                for day, slices in data["days"].items()
            },
        }

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None




class AristonPhysicalGas(AristonEntity, SensorEntity):
    """Raw physical Smc by period, not a running meter."""

    _attr_native_unit_of_measurement = "Smc"
    _attr_icon = "mdi:meter-gas"
    # Standard m³ is not interchangeable with uncorrected m³.
    # No GAS device_class or cumulative state class is advertised.

    def __init__(self, coordinator, source_key: str, translation_key: str):
        super().__init__(coordinator, "web_smc_" + source_key)
        self._source_key = source_key
        self._attr_translation_key = translation_key

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return data.get(self._source_key) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        if not data:
            return {}
        # A midnight 22:00–00:00 report belongs to YESTERDAY even
        # though the CurrentDay daily total is already for today.
        is_2h = self._source_key.endswith("_2h")
        attributes = {
            "giorno_riferimento": (
                data.get("completed_interval_date") if is_2h
                else data.get("reported_date")
            )
        }
        if is_2h:
            attributes["fascia_completata"] = data.get("completed_interval")
        return attributes

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None



class AristonCumulativeGas(AristonEntity, SensorEntity):
    """Persistent gas amount in m³ at standard conditions (Smc)."""

    _attr_device_class = SensorDeviceClass.GAS
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:meter-gas"

    def __init__(self, coordinator, source_key: str, translation_key: str):
        # NEW unique ID, not the short-lived 0.8.5/0.8.6 experimental
        # Energy statistic that may already exist in some Recorder databases.
        super().__init__(coordinator, "gas_meter_v1_" + source_key)
        self._source_key = source_key
        self._attr_translation_key = translation_key

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        return data.get(self._source_key) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "volume_reference": "standard conditions (Smc)",
            "histogram_previous_day_verified": data.get("history_complete", False),
            "histogram_periods": data.get("observed_periods", []),
        }

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None


