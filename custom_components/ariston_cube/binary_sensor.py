"""Heating request and flame state from the cloud; read-only."""

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription

from .entity import AristonEntity
from .model import as_boolean

DESCRIPTIONS = (
    BinarySensorEntityDescription(key="ZoneHeatRequest", translation_key="heat_request"),
    BinarySensorEntityDescription(key="IsFlameOn", translation_key="flame"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(AristonBinarySensor(coordinator, description) for description in DESCRIPTIONS)


class AristonBinarySensor(AristonEntity, BinarySensorEntity):
    """Read a single boolean item."""

    def __init__(self, coordinator, description):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self):
        return as_boolean(self.record)

    @property
    def available(self):
        return super().available and self.is_on is not None
