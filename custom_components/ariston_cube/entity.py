"""Shared device description and readings for Ariston Cube entities."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class AristonEntity(CoordinatorEntity):
    """Entity backed exclusively by the shared coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.plant_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.plant_id)},
            manufacturer="Ariston",
            name=coordinator.plant_name,
        )

    @property
    def record(self):
        return self.coordinator.data.get(self._key) if self.coordinator.data else None
