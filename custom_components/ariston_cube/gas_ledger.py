"""Persistent, period-aware ledger for normalized gas volume reported in Smc.

No guessed gas calorific factor; the dashboard's m³ represent the exact
numerical standard cubic metres reported in asPhysicalUnit.

Treat corrections as signed differences using HA's state_class TOTAL, not as
fictitious new usage or lifetime meter resets. Only advertise statistics once
the gateway has demonstrated it can supply a full PreviousDay histogram,
because the 22:00-00:00 bucket is not available from CurrentDay after 02:00.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import math
from typing import Any

_SERIES = {"Heating": "heating", "Dhw": "dhw"}
_PERIODS = ("PreviousDay", "CurrentDay")
_VERSION = 1


def empty_state() -> dict[str, Any]:
    return {
        "version": _VERSION,
        "totals": {"heating": 0.0, "dhw": 0.0},
        "days": {},
        "previous_day_verified": False,
    }


def valid_state(raw: Any) -> dict[str, Any] | None:
    """Fail closed on malformed persisted totals and ledger schema."""
    if not isinstance(raw, dict) or raw.get("version") != _VERSION:
        return None
    totals = raw.get("totals")
    if not isinstance(totals, dict):
        return None
    for key in _SERIES.values():
        value = totals.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not math.isfinite(value) or value < 0:
            return None
    days = raw.get("days")
    if not isinstance(days, dict) or len(days) > 8:
        return None
    for day, values in days.items():
        try:
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                return None
        except ValueError:
            return None
        if not isinstance(values, dict):
            return None
        for key, slots in values.items():
            if key not in _SERIES.values() or not isinstance(slots, dict):
                return None
            for index, value in slots.items():
                if index not in {str(i) for i in range(12)}:
                    return None
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value < 0):
                    return None
    if not isinstance(raw.get("previous_day_verified"), bool):
        return None
    return deepcopy(raw)


def _rows(report: Any, now: datetime) -> list[tuple[str, str, int, float]]:
    """Parse only explicit completed 2h slots; reject duplicated series."""
    if now.tzinfo is None or now.utcoffset() is None or not isinstance(report, dict):
        return []
    physical = report.get("asPhysicalUnit")
    histogram = physical.get("histogramData") if isinstance(physical, dict) else None
    if not isinstance(histogram, list):
        return []
    rows: list[tuple[str, str, int, float]] = []
    for period in _PERIODS:
        day = now.date() if period == "CurrentDay" else now.date() - timedelta(days=1)
        # CurrentDay index 0 (00-02) becomes complete at 02:00; previous day
        # allows all 12 buckets, including 22:00-00:00.
        completed = min(12, now.hour // 2) if period == "CurrentDay" else 12
        for raw_name, kind in _SERIES.items():
            matches = [
                item for item in histogram
                if isinstance(item, dict)
                and item.get("period") == period
                and item.get("series") == raw_name
            ]
            if len(matches) != 1:
                continue
            samples = matches[0].get("items")
            if not isinstance(samples, list) or len(samples) != 12:
                continue
            valid: list[float] = []
            for sample in samples:
                value = sample.get("y") if isinstance(sample, dict) else None
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value < 0 or value > 100000):
                    valid = []
                    break
                valid.append(float(value))
            if len(valid) != 12:
                continue
            for idx, value in enumerate(valid[:completed]):
                rows.append((day.isoformat(), kind, idx, round(value, 6)))
    return rows


def apply_report(
    original: dict[str, Any], report: Any, now: datetime,
) -> tuple[dict[str, Any], bool]:
    """Compute new snapshot; caller MUST persist it before publishing state."""
    state = valid_state(original)
    if state is None:
        raise ValueError("Invalid stored gas ledger")
    rows = _rows(report, now)
    if not rows:
        return state, False
    changed = False
    old_days = state["days"]
    for day, kind, idx, value in rows:
        slots = old_days.setdefault(day, {}).setdefault(kind, {})
        key = str(idx)
        old = slots.get(key)
        if old is not None and old == value:
            continue
        delta = value - (old if old is not None else 0.0)
        state["totals"][kind] = round(state["totals"][kind] + delta, 6)
        # Reductions are valid cloud corrections; "total" (not
        # "total_increasing") lets HA reduce the statistic once.
        if state["totals"][kind] < 0:
            raise ValueError("Negative corrected meter total")
        slots[key] = value
        changed = True
    previous = (now.date() - timedelta(days=1)).isoformat()
    if not state["previous_day_verified"]:
        # Prove server offers last day's final slot for BOTH usage kinds.
        prev = state["days"].get(previous, {})
        if all("11" in prev.get(kind, {}) for kind in _SERIES.values()):
            state["previous_day_verified"] = True
            changed = True
    # Keep this day, the previous two days and only their slot ledgers.
    # Lifetime totals remain untouched when old slot hashes are discarded.
    allowed_days = {(now.date() - timedelta(days=i)).isoformat() for i in range(3)}
    for day in list(old_days):
        if day not in allowed_days:
            del old_days[day]
            changed = True
    return state, changed


class StoredGasLedger:
    """Small HA .storage record; only current two-hour buckets are persisted."""

    def __init__(self, hass: Any, entry_id: str) -> None:
        from homeassistant.helpers.storage import Store

        self._store = Store(hass, _VERSION, f"ariston_cube_gas_ledger_{entry_id}")
        self._state: dict[str, Any] | None = None

    async def async_apply(self, report: Any, now: datetime) -> dict[str, Any]:
        if self._state is None:
            raw = await self._store.async_load()
            if raw is None:
                self._state = empty_state()
            else:
                self._state = valid_state(raw)
                if self._state is None:
                    raise ValueError("Existing gas ledger invalid; refusing to reset")
        candidate, changed = apply_report(self._state, report, now)
        if changed:
            await self._store.async_save(candidate)
        self._state = candidate
        if not candidate["previous_day_verified"]:
            # No supported previous-day reading: missing 22-24 would undercount.
            return {"heating": None, "dhw": None, "history_complete": False}
        return {
            "heating": candidate["totals"]["heating"],
            "dhw": candidate["totals"]["dhw"],
            "history_complete": True,
        }
