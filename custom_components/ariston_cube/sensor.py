"""Original temperature sensors and the Cube S weekly programme."""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfTemperature

from .entity import AristonEntity
from .model import as_temperature
from .schedule_coordinator import AristonWeeklyCoordinator
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
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    schedule = AristonWeeklyCoordinator(hass, coordinator)
    entities = [AristonTemperature(coordinator, description) for description in DESCRIPTIONS]
    entities.append(AristonWeeklySchedule(schedule))
    async_add_entities(entities)
    # Only one additional request at startup; refresh failures remain local
    # to the optional schedule entity, never breaking existing sensors.
    entry.async_create_background_task(
        hass, schedule.async_refresh(), "Ariston Cube weekly programme initial read"
    )


class AristonTemperature(AristonEntity, SensorEntity):
    """Temperature read from Ariston dataItems."""

    def __init__(self, coordinator, description):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
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
