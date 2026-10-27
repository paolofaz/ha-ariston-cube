"""Physical-unit Smc report parser, with daily rollover at 00:00.

Field-observed 2026-10-27 on Cube S:
  * At 22:40 CurrentDay indexes 0..10 were complete.
  * At 00:10 PreviousDay held all 12 previous calendar-day buckets,
    including the last 22:00-00:00 usage; CurrentDay was reset to zero.
  * At 02:10 PreviousDay was unchanged; CurrentDay was still zero.
This is DIFFERENT from the legacy mobile kWh "today" calculation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any


def _series(histogram: Any, period: str, cloud_name: str) -> list[float] | None:
    if not isinstance(histogram, list):
        return None
    matches = [
        row for row in histogram
        if isinstance(row, dict)
        and row.get("period") == period
        and row.get("series") == cloud_name
    ]
    if len(matches) != 1:
        return None
    points = matches[0].get("items")
    if not isinstance(points, list) or len(points) != 12:
        return None
    values = []
    for point in points:
        value = point.get("y") if isinstance(point, dict) else None
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not 0 <= value < 100000):
            return None
        values.append(float(value))
    return values


def parse_smc_report(payload: Any, now: datetime) -> dict[str, Any]:
    """Today from CurrentDay; midnight's final interval from PreviousDay."""
    result = {
        "heating_smc_today": None, "dhw_smc_today": None,
        "heating_smc_2h": None, "dhw_smc_2h": None,
        "completed_interval": None,
        "completed_interval_date": None,
        "reported_date": None,
    }
    if not isinstance(payload, dict) or now.tzinfo is None or now.utcoffset() is None:
        return result
    physical = payload.get("asPhysicalUnit")
    histogram = physical.get("histogramData") if isinstance(physical, dict) else None
    if not isinstance(histogram, list):
        return result

    result["reported_date"] = now.date().isoformat()
    at_midnight = now.hour < 2
    finished = 11 if at_midnight else now.hour // 2 - 1
    completed_date = now.date() - timedelta(days=1) if at_midnight else now.date()
    result["completed_interval_date"] = completed_date.isoformat()
    result["completed_interval"] = (
        f"{2 * finished:02}:00–{(2 * finished + 2) % 24:02}:00"
    )
    for cloud_name, key in (("Heating", "heating"), ("Dhw", "dhw")):
        current = _series(histogram, "CurrentDay", cloud_name)
        # Only completed windows are summed. Future slots may be zero or
        # contain a transient server value, and are never recognized as usage.
        if current is not None:
            result[key + "_smc_today"] = round(sum(current[:now.hour // 2]), 6)

        last = (_series(histogram, "PreviousDay", cloud_name)
                if at_midnight else current)
        if last is not None:
            result[key + "_smc_2h"] = round(last[finished], 6)
    return result
