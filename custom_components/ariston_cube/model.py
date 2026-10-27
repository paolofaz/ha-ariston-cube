"""Pure Ariston response parsing; independent of Home Assistant and HTTP."""

from __future__ import annotations

from typing import Any

PLANT_IDS = frozenset((
    "PlantMode",
    "AutomaticThermoregulation",
    "ChFlowTemp",
    "ChFlowSetpointTemp",
    "OutsideTemp",
    "HeatingCircuitPressure",
    "IsFlameOn",
    "DhwTemp",
    "DhwStorageTemperature",
    "DhwMode",
    "DhwTimeProgComfortTemp",
    "DhwTimeProgEconomyTemp",
))
ZONE_IDS = frozenset((
    "ZoneMeasuredTemp",
    "ZoneDesiredTemp",
    "ZoneHeatRequest",
    "ZoneMode",
    "ZoneComfortTemp",
    "ZoneEconomyTemp",
))


def parse_plants(payload: Any) -> list[dict[str, str]]:
    """Validate plant IDs without including account details in logs."""
    if not isinstance(payload, list):
        raise ValueError("Expected a list of plants")
    plants: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("gwId"), str):
            raise ValueError("Invalid plant record")
        identifier = item["gwId"].strip()
        if not identifier:
            raise ValueError("Empty plant identifier")
        name = item.get("name")
        plants.append({
            "id": identifier,
            "name": str(name) if name else f"Ariston {identifier[-4:]}",
        })
    return plants


def make_main_request(features: dict[str, Any], zone: int = 1) -> dict[str, Any]:
    """Request supported observed values, including optional boiler telemetry."""
    if not isinstance(features, dict):
        raise ValueError("Invalid features")
    if zone < 1:
        raise ValueError("Invalid zone")
    items = [{"id": item, "zn": 0} for item in sorted(PLANT_IDS)]
    items.extend({"id": item, "zn": zone} for item in sorted(ZONE_IDS))
    return {"useCache": False, "items": items, "features": features}


def parse_main_data(payload: Any, zone: int = 1) -> dict[str, dict[str, Any]]:
    """Extract supported fields while retaining limits supplied by Ariston."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Invalid dataItems response")
    values: dict[str, dict[str, Any]] = {}
    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        item_zone = item.get("zone", item.get("zn"))
        if not isinstance(identifier, str) or "value" not in item:
            continue
        if identifier in PLANT_IDS and item_zone in (0, "0"):
            pass
        elif identifier in ZONE_IDS and item_zone in (zone, str(zone)):
            pass
        else:
            continue
        parsed: dict[str, Any] = {"value": item["value"]}
        for key in ("min", "max", "step", "unit", "options"):
            if key in item:
                parsed[key] = item[key]
        if isinstance(item.get("options"), list) and isinstance(item.get("optTexts"), list):
            try:
                option_index = [str(opt) for opt in item["options"]].index(str(item["value"]))
                parsed["label"] = item["optTexts"][option_index]
            except (ValueError, IndexError):
                pass
        values[identifier] = parsed
    return values


def as_temperature(record: dict[str, Any] | None) -> float | None:
    """Reject missing, boolean and non-numeric readings."""
    if not record:
        return None
    raw = record.get("value")
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
        if not -273.15 <= value <= 1000:
            return None
        return value
    except (TypeError, ValueError, OverflowError):
        return None


def as_boolean(record: dict[str, Any] | None) -> bool | None:
    """Interpret known on/off values without treating unknown as false."""
    if not record:
        return None
    value = record.get("value")
    if value in (True, 1, "1", "ON", "On", "on"):
        return True
    if value in (False, 0, "0", "OFF", "Off", "off"):
        return False
    return None
