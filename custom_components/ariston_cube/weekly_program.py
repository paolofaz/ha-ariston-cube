"""Validate Cube S weekly programme without Home Assistant dependencies.

The Ariston 'ChZn1' payload is a list of plans, each with day codes
(Sunday=0 through Saturday=6) and slices with start minute and preset code.
Never infer missing schedules or replace the Cube S time programme.
"""

from __future__ import annotations

from typing import Any

DAYS_IT = (
    "Domenica", "Lunedì", "Martedì", "Mercoledì",
    "Giovedì", "Venerdì", "Sabato",
)


def parse_weekly_program(payload: Any) -> dict[str, Any]:
    """Return seven day-to-slices mappings and the number of source plans.

    Fail closed on malformed or conflicting schedules. A missing weekday
    is not assumed to use any preset.
    """
    if not isinstance(payload, dict):
        raise ValueError("Invalid weekly programme response")
    zone = payload.get("ChZn1")
    if not isinstance(zone, dict):
        raise ValueError("Missing zone 1 weekly programme")
    plans = zone.get("plans")
    if not isinstance(plans, list) or not 1 <= len(plans) <= 14:
        raise ValueError("Invalid weekly programme plan count")
    by_day: dict[int, list[dict[str, Any]]] = {}
    for plan in plans:
        if not isinstance(plan, dict):
            raise ValueError("Invalid weekly plan")
        days = plan.get("days")
        slices = plan.get("slices")
        if not isinstance(days, list) or not days or not isinstance(slices, list):
            raise ValueError("Missing weekly days or slices")
        if not 1 <= len(slices) <= 48:
            raise ValueError("Unexpected number of scheduled slices")
        ordered = []
        seen_minutes = set()
        for record in slices:
            if not isinstance(record, dict):
                raise ValueError("Invalid slice")
            start = record.get("from")
            temp = record.get("temp")
            if type(start) is not int or not 0 <= start < 24 * 60:
                raise ValueError("Invalid slice time")
            if type(temp) is not int or temp not in (0, 1):
                raise ValueError("Unknown Comfort/Economy programme code")
            if start in seen_minutes:
                raise ValueError("Duplicate slice starting time")
            seen_minutes.add(start)
            ordered.append({
                "minute": start, "time": f"{start // 60:02}:{start % 60:02}",
                "preset": "Economy" if temp == 0 else "Comfort",
            })
        ordered.sort(key=lambda slice_: slice_["minute"])
        for day in days:
            if type(day) is not int or not 0 <= day <= 6:
                raise ValueError("Unknown weekday code")
            if day in by_day:
                raise ValueError("Overlapping weekly plans")
            by_day[day] = list(ordered)
    return {
        "plan_count": len(plans),
        "days": {DAYS_IT[index]: by_day.get(index) for index in range(7)},
    }


def daily_description(slices: list[dict[str, Any]] | None) -> str | None:
    """Human readable schedule; a missing plan remains unknown."""
    if slices is None:
        return None
    return " · ".join(f"{slice_['time']} {slice_['preset']}" for slice_ in slices)
