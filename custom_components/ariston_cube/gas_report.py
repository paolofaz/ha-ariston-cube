"""Today's and current two-hour gas use from Ariston consumption sequences.

The legacy Ariston implementation maps k=7 to heating gas, k=10 to DHW
gas and p=1 to 24 two-hour buckets. The last bucket corresponds to the
current local two-hour window (which may still be incomplete).
No lifetime counters are inferred and raw readings are never persisted.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any

_KINDS = {"heating": 7, "dhw": 10}
_BUCKET_COUNT = 24


def _valid_bucket(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    if not math.isfinite(converted) or converted < 0 or converted > 1_000_000:
        return None
    return converted


def parse_recent_gas(payload: Any, now: datetime) -> dict[str, Any]:
    """Compute two separated present-day totals and the current 2h bucket.

    The source is an array of period/type/value triples, with 24 successive
    two-hour samples, oldest first. Treat missing/duplicate/invalid series
    as unavailable instead of zero. "Today" is local calendar-day use so
    far, not an all-time meter.
    """
    empty: dict[str, Any] = {
        "heating_today": None, "dhw_today": None,
        "heating_2h": None, "dhw_2h": None,
        "slot": None,
    }
    if now.tzinfo is None or now.utcoffset() is None or not isinstance(payload, list):
        return empty
    latest_start = now.replace(
        hour=(now.hour // 2) * 2, minute=0, second=0, microsecond=0
    )
    latest_end = latest_start + timedelta(hours=2)
    result = dict(empty)
    result["slot"] = (
        f"{latest_start:%H:%M}–{latest_end:%H:%M}"
    )
    for name, expected_code in _KINDS.items():
        candidates = [
            item for item in payload
            if isinstance(item, dict)
            and type(item.get("k")) is int
            and type(item.get("p")) is int
            and item["k"] == expected_code and item["p"] == 1
        ]
        if len(candidates) != 1:
            continue
        raw_values = candidates[0].get("v")
        if not isinstance(raw_values, list) or len(raw_values) != _BUCKET_COUNT:
            continue
        samples = [_valid_bucket(value) for value in raw_values]
        if any(value is None for value in samples):
            continue
        # Align newest sample to the current two-hour local window, matching
        # the old Ariston client; buckets before midnight belong to yesterday.
        todays_samples = [
            value for index, value in enumerate(reversed(samples))
            if (latest_start - timedelta(hours=2 * index)).date() == now.date()
        ]
        if not todays_samples:
            continue
        result[f"{name}_today"] = round(sum(todays_samples), 3)
        result[f"{name}_2h"] = samples[-1]
    return result
