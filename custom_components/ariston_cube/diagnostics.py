"""On-demand, schema-only diagnostics for consumption and Cube S scheduling.

NEVER include cloud response values, credentials, plant identifiers, tokens,
timestamps, gas consumption readings, location or serial numbers.
"""

from __future__ import annotations

from typing import Any

from .api import AristonError

# A strict semantic key allowlist: unknown/dynamic keys are not returned.
_ALLOWED_FIELDS = frozenset({
    "data", "items", "results", "series", "usages", "usage",
    "unit", "units", "value", "values", "count", "type",
    "date", "time", "start", "end", "startTime", "endTime",
    "from", "to", "hours", "day", "days", "week", "weeks",
    "interval", "intervals", "dateFrom", "dateTo",
    "startDate", "endDate", "period", "periods", "timeBands",
    "schedule", "program", "programs", "timeProg", "timeProgs",
    "zone", "zoneId", "comfort", "economy", "comf", "econ",
    "active", "current", "selected", "type", "mode",
    "consumptions", "consumption", "consSequences",
    "year", "month", "months", "LastMonth", "LastDay",
    "Today", "ThisMonth", "ThisYear", "Ch", "Dhw",
    "gas", "elect", "electricity", "heat", "heating", "cool",
    "electric", "cost", "energy", "total", "totals", "isActive",
})


def safe_shape(value: Any, depth: int = 0) -> dict[str, Any]:
    """Return only data types and aggregate structure (never scalar values)."""
    if depth >= 5:
        return {"kind": "max_depth"}
    if isinstance(value, dict):
        fields = {
            key: safe_shape(val, depth + 1)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            if isinstance(key, str) and key in _ALLOWED_FIELDS
        }
        # Show anonymous *shapes* for unknown keys, never their names or
        # scalar values. The 0.4.1 diagnostics obscured the whole weekly
        # schedule and every field in consumption-sequence entries.
        unknown = [
            safe_shape(val, depth + 1)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            if not (isinstance(key, str) and key in _ALLOWED_FIELDS)
        ]
        return {
            "kind": "object",
            "fields": fields,
            "omitted_keys": len(unknown),
            "unnamed_field_shapes": unknown[:4],
        }
    if isinstance(value, list):
        return {
            "kind": "list",
            "count": len(value),
            "first_shape": safe_shape(value[0], depth + 1) if value else None,
        }
    if isinstance(value, bool):
        return {"kind": "boolean"}
    if isinstance(value, int):
        return {"kind": "integer"}
    if isinstance(value, float):
        return {"kind": "number"}
    if isinstance(value, str):
        return {"kind": "string"}
    if value is None:
        return {"kind": "null"}
    return {"kind": "other"}


async def async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]:
    """Issue one manual read per endpoint and report only schemas.

    Fetching Home Assistant diagnostics does not modify the boiler.
    It is not part of 60-second coordinator polling.
    """
    coordinator = entry.runtime_data
    snapshots = await coordinator.client.async_diagnostic_reports(coordinator.plant_id)
    safe_reports = {}
    for key in ("weekly_program", "energy_account", "consumption_sequences"):
        result = snapshots.get(key)
        if isinstance(result, AristonError):
            safe_reports[key] = {"error_type": type(result).__name__}
        else:
            safe_reports[key] = safe_shape(result)
    # Only static entity names; no account or plant data in the output.
    return {
        "integration": "ariston_cube",
        "version": "0.5.0",
        "purpose": "schema_only_no_personal_values",
        "reports": safe_reports,
    }
