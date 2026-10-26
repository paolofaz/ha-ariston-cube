"""Original temperature sensors and the Cube S weekly programme."""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfPressure

from .entity import AristonEntity
from .model import as_temperature
from .schedule_coordinator import get_or_create_weekly_coordinator
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
    async_add_entities(entities)


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
