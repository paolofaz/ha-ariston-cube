"""Pure status mapping for CLAS ONE/Cube S; no Home Assistant imports.

The zone can be configured even when the entire plant is in summer mode.
Do not infer effective heating from the zone mode alone.
"""

from __future__ import annotations

from typing import Any

from .model import as_boolean


def enum_code(record: dict[str, Any] | None) -> int | None:
    """Parse cloud mode codes strictly, without false zeroes."""
    if not record:
        return None
    value = record.get("value")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def heating_mode(data: dict[str, dict[str, Any]]) -> str | None:
    """Return 'heat', 'off' or unknown, considering the whole plant."""
    plant = enum_code(data.get("PlantMode"))
    zone = enum_code(data.get("ZoneMode"))
    if plant is None or zone is None:
        return None
    # Plant mode 0=summer, 5=off; holiday mode is intentionally unknown.
    # The cloud may still allow frost protection in holiday mode.
    if plant in (0, 5) or zone == 0:
        return "off"
    # 1=winter, 2=heating-only; zone 1/2/3 permits heating.
    if plant in (1, 2) and zone in (1, 2, 3):
        return "heat"
    return None


def heating_activity(data: dict[str, dict[str, Any]]) -> str | None:
    """Show burner heating only when request and flame both agree."""
    mode = heating_mode(data)
    if mode == "off":
        return "off"
    if mode != "heat":
        return None
    request = as_boolean(data.get("ZoneHeatRequest"))
    flame = as_boolean(data.get("IsFlameOn"))
    if request is False:
        return "idle"
    if request is True and flame is True:
        return "heating"
    if request is True and flame is False:
        return "idle"
    return None


def zone_program(data: dict[str, dict[str, Any]]) -> str | None:
    """Informational only. Never replace the Cube S weekly schedule."""
    return {
        0: "off",
        1: "economy",
        2: "manual",
        3: "time_program",
    }.get(enum_code(data.get("ZoneMode")))


def hot_water_operation(data: dict[str, dict[str, Any]]) -> str | None:
    """Report Ariston DHW operation; never infer it from flame."""
    return {
        0: "off",
        1: "scheduled",
        2: "always_active",
        3: "heat_cool_heat_pump",
        4: "heat_cool_heat_pump_40",
        5: "green",
    }.get(enum_code(data.get("DhwMode")))
