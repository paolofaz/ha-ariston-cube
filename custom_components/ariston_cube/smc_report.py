"""Direct standard cubic metres from Ariston's physical-unit web report.

Do not reinterpret mobile consumption sequences as Smc, and do not use a
guessed conversion factor. Web histogram CurrentDay has twelve 2h buckets,
one for each local 00:00–24:00 interval, with source 'series' names.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any


def parse_smc_report(payload: Any, now: datetime) -> dict[str, Any]:
    result = {
        "heating_smc_today": None, "dhw_smc_today": None,
        "heating_smc_2h": None, "dhw_smc_2h": None,
        "completed_interval": None,
        "reported_date": None,
    }
    if not isinstance(payload, dict) or now.tzinfo is None or now.utcoffset() is None:
        return result
    physical = payload.get("asPhysicalUnit")
    if not isinstance(physical, dict):
        return result
    histogram = physical.get("histogramData")
    if not isinstance(histogram, list):
        return result
    # Ariston keeps yesterday's CurrentDay visible from midnight until
    # the 02:00 reset. The 22:00–00:00 slot arrives at 00:00.
    previous_report_day = now.hour < 2
    finished = 11 if previous_report_day else now.hour // 2 - 1
    reference_date = now.date() - timedelta(days=1) if previous_report_day else now.date()
    result["reported_date"] = reference_date.isoformat()
    result["completed_interval"] = f"{2*finished:02}:00–{2*finished+2:02}:00"
    for cloud_name, key in (("Heating", "heating"), ("Dhw", "dhw")):
        matches = [
            row for row in histogram
            if isinstance(row, dict)
            and row.get("period") == "CurrentDay"
            and row.get("series") == cloud_name
        ]
        if len(matches) != 1:
            continue
        items = matches[0].get("items")
        if not isinstance(items, list) or len(items) != 12:
            continue
        values = []
        for point in items:
            if not isinstance(point, dict):
                break
            value = point.get("y")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                break
            v = float(value)
            if not math.isfinite(v) or not 0 <= v < 100_000:
                break
            values.append(v)
        if len(values) != 12:
            continue
        result[key + "_smc_today"] = round(sum(values[:finished + 1]), 6)
        result[key + "_smc_2h"] = round(values[finished], 6)
    return result
