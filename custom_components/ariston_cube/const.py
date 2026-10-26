"""Constants and read-only data-item identifiers for Ariston Cube."""

DOMAIN = "ariston_cube"
BASE_URL = "https://www.ariston-net.remotethermo.com"
CONF_PLANT_ID = "plant_id"
CONF_PLANT_NAME = "plant_name"
SCAN_INTERVAL_SECONDS = 60

# Identifiers observed in the legacy remotethermo client.
PLANT_ITEMS = (
    "PlantMode",
    "IsFlameOn",
    "DhwTemp",
    "DhwStorageTemperature",
)
ZONE_ITEMS = (
    "ZoneMeasuredTemp",
    "ZoneDesiredTemp",
    "ZoneHeatRequest",
    "ZoneMode",
)
