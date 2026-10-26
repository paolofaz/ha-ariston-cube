"""Parse period-specific Ariston gas summaries, not lifetime energy meters.

The upstream Galevo client defines energyAccount.LastMonth[0] as heating and
[1] as DHW; its source documents this last-month report in kWh.
"""

from __future__ import annotations

import math
from typing import Any


def _valid_nonnegative(value: Any) -> float | None:
    """Reject invalid cloud values rather than inventing zero consumption."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > 1_000_000:
        return None
    return result


def parse_last_month_gas(payload: Any) -> dict[str, float | None]:
    """Return two explicitly period-scoped heating and DHW kWh values."""
    values: dict[str, float | None] = {
        "heating": None,
        "dhw": None,
    }
    if not isinstance(payload, dict):
        return values
    last_month = payload.get("LastMonth")
    if not isinstance(last_month, list) or len(last_month) != 2:
        return values
    for key, index in (("heating", 0), ("dhw", 1)):
        item = last_month[index]
        if isinstance(item, dict):
            values[key] = _valid_nonnegative(item.get("gas"))
    return values
