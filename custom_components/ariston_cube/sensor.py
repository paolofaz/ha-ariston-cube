"""Only essential read-only temperature entities for the first milestone."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import UnitOfTemperature

from .entity import AristonEntity
from .model import as_temperature

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
    async_add_entities(AristonTemperature(coordinator, description) for description in DESCRIPTIONS)


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
