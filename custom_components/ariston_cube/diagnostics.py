"""On-demand, schema-only diagnostics for consumption and Cube S scheduling.

NEVER include cloud response values, credentials, plant identifiers, tokens,
timestamps, gas consumption readings, location or serial numbers.
"""

from __future__ import annotations

from typing import Any

from .api import AristonError
from .web_portal import WebPortalError, WebPortalComfortShapeError

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
    "ChZn1", "plans", "slices", "temp", "p", "k", "v",
    "electric", "cost", "energy", "total", "totals", "isActive",
    "gasEnergyUnit", "gasType", "currency", "elecCost", "gasCost",
})


def safe_shape(value: Any, depth: int = 0) -> dict[str, Any]:
    """Return only data types and aggregate structure (never scalar values)."""
    if depth >= 8:
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


# Code names are from the community Ariston mobile API implementation.
# Their physical meaning and unit must still be verified on this boiler.
_PERIOD_CANDIDATES = {
    1: "last_day_candidate",
    2: "last_week_candidate",
    3: "last_month_candidate",
    4: "last_year_candidate",
}
_TYPE_CANDIDATES = {
    1: "heating_total_energy_candidate",
    2: "dhw_total_energy_candidate",
    3: "cooling_total_energy_candidate",
    7: "heating_gas_candidate",
    8: "dhw_heat_pump_electricity_candidate",
    9: "dhw_resistor_electricity_candidate",
    10: "dhw_gas_candidate",
    20: "heating_electricity_candidate",
    21: "dhw_electricity_candidate",
}


def safe_consumption_inventory(raw: Any) -> dict[str, Any]:
    """Summarize series categories and sample counts, not measurements."""
    if not isinstance(raw, list):
        return {"kind": "not_a_list"}
    series = []
    for item in raw[:48]:
        if not isinstance(item, dict):
            series.append({"kind": "not_an_object"})
            continue
        period = item.get("p")
        kind = item.get("k")
        values = item.get("v")
        if not isinstance(period, int) or isinstance(period, bool):
            period = None
        if not isinstance(kind, int) or isinstance(kind, bool):
            kind = None
        series.append({
            "period_candidate": _PERIOD_CANDIDATES.get(period, "unknown"),
            "usage_candidate": _TYPE_CANDIDATES.get(kind, "unknown"),
            "sample_count": len(values) if isinstance(values, list) else None,
            "all_samples_numeric": (
                all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    for value in values
                ) if isinstance(values, list) else False
            ),
        })
    return {"series_count": len(raw), "series": series}


# Codes from the upstream GasEnergyUnit enumeration. This is the unit
# configured for gas consumption reporting, not proof of metered values.
GAS_UNIT_CANDIDATES = {
    0: "kWh", 1: "GJ", 2: "therm", 3: "MBtu",
    4: "Smc", 5: "m³",
}


def safe_consumption_units(raw: Any) -> dict[str, str]:
    """Expose only a recognized unit label; never tariff or cost amounts."""
    if not isinstance(raw, dict):
        return {"gas_unit_candidate": "unavailable"}
    value = raw.get("gasEnergyUnit")
    if type(value) is not int:
        return {"gas_unit_candidate": "unknown"}
    return {"gas_unit_candidate": GAS_UNIT_CANDIDATES.get(value, "unknown")}



def safe_dhw_comfort_menu(raw: Any) -> dict[str, str]:
    """Show only a known 0/1/2 Comfort ACS code, never raw web responses."""
    if isinstance(raw, WebPortalComfortShapeError):
        # Only schema metadata, no raw menu values, localization strings or IDs.
        return {
            "status": "formato_valore_sconosciuto",
            "value_kind": raw.value_kind,
            "dropdown_option_count": raw.option_count,
            "dropdown_option_value_kinds": raw.option_value_kinds,
        }
    if isinstance(raw, (AristonError, WebPortalError)):
        # Include only a numeric HTTP status from a strictly known error.
        # Never serialize a raw exception, URL, login HTML or credentials.
        import re
        match = re.fullmatch(r"Web login (?:form|POST) HTTP (\d{3})", str(raw))
        safe = {"status": "non_disponibile", "error_type": type(raw).__name__}
        if match:
            safe["http_status"] = int(match.group(1))
        return safe
    records = raw if isinstance(raw, list) else raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(records, list):
        return {"status": "formato_sconosciuto"}
    for record in records[:15]:
        if not isinstance(record, dict) or record.get("id") != "U6_9_2":
            continue
        value = record.get("value")
        # Reject booleans and incidental strings, not coercible arbitrary text.
        if isinstance(value, bool):
            break
        if value in (0, "0"):
            return {"status": "letto", "modalita": "spenta"}
        if value in (1, "1"):
            return {"status": "letto", "modalita": "temporizzata"}
        if value in (2, "2"):
            return {"status": "letto", "modalita": "sempre_attiva"}
        break
    return {"status": "valore_non_riconosciuto"}


async def async_get_config_entry_diagnostics(hass, entry) -> dict[str, Any]:
    """Issue one manual read per endpoint and report only schemas.

    Fetching Home Assistant diagnostics does not modify the boiler.
    It is not part of 60-second coordinator polling.
    """
    coordinator = entry.runtime_data
    snapshots = await coordinator.client.async_diagnostic_reports(coordinator.plant_id)
    comfort_probe = await coordinator.client.async_probe_dhw_comfort_menu(coordinator.plant_id)
    safe_reports = {}
    for key in ("weekly_program", "energy_account", "consumption_sequences",
                "consumption_settings"):
        result = snapshots.get(key)
        if isinstance(result, AristonError):
            safe_reports[key] = {"error_type": type(result).__name__}
        else:
            safe_reports[key] = safe_shape(result)
    # Only static entity names; no account or plant data in the output.
    return {
        "integration": "ariston_cube",
        "version": "0.8.8",
        "purpose": "schema_only_no_personal_values",
        "reports": safe_reports,
        "consumption_inventory": safe_consumption_inventory(
            snapshots.get("consumption_sequences")
        ),
        "comfort_acs_menu_probe": safe_dhw_comfort_menu(comfort_probe),
        "consumption_units": safe_consumption_units(
            snapshots.get("consumption_settings")
        ),
    }
