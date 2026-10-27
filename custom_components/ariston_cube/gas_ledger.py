"""Restart-safe gas Smc accounting using real midnight web-report behavior.

At midnight the web report moves all of yesterday's 12 two-hour intervals
to PreviousDay (including 22:00–00:00), and CurrentDay is reset.
This behavior was verified against the 2026-10-27 web diagnostic captures;
it differs from the legacy mobile kWh-derived daily sensor.

Each usage/day/2-hour-slot is stored independently; equal adjacent
usage amounts are counted separately, while rereads of the same slot
are no-ops. Corrections to the same slot apply only the signed delta.
The storage checkpoint is saved BEFORE notifying Home Assistant.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
import math
from typing import Any

_SERIES = {"Heating": "heating", "Dhw": "dhw"}
_PERIODS = ("PreviousDay", "CurrentDay")
_VERSION = 4
_SLOT_KEYS = {str(i) for i in range(12)}


def empty_state() -> dict[str, Any]:
    return {
        "version": _VERSION,
        "totals": {"heating": 0.0, "dhw": 0.0},
        "days": {},
        "previous_day_verified": False,
        "tracking_start": None,
        "closed_through": None,
        "continuity_lost": False,
    }


def valid_state(raw: Any) -> dict[str, Any] | None:
    """Never silently reset an inconsistent or incompatible stored ledger."""
    if not isinstance(raw, dict) or raw.get("version") != _VERSION:
        return None
    totals, days = raw.get("totals"), raw.get("days")
    if not isinstance(totals, dict) or not isinstance(days, dict) or len(days) > 8:
        return None
    for kind in _SERIES.values():
        value = totals.get(kind)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            return None
    for key, kinds in days.items():
        try:
            if not isinstance(key, str) or date.fromisoformat(key).isoformat() != key:
                return None
        except ValueError:
            return None
        if not isinstance(kinds, dict):
            return None
        for kind, slots in kinds.items():
            if kind not in _SERIES.values() or not isinstance(slots, dict):
                return None
            for slot, value in slots.items():
                if (slot not in _SLOT_KEYS
                        or isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value) or value < 0):
                    return None
    if (not isinstance(raw.get("previous_day_verified"), bool)
            or not isinstance(raw.get("continuity_lost"), bool)):
        return None
    for field in ("tracking_start", "closed_through"):
        value = raw.get(field)
        if value is not None:
            try:
                if (not isinstance(value, str)
                        or date.fromisoformat(value).isoformat() != value):
                    return None
            except ValueError:
                return None
    return deepcopy(raw)


def _rows(report: Any, now: datetime) -> list[tuple[str, str, int, float]]:
    """Retrieve completed report buckets keyed by actual calendar date."""
    if now.tzinfo is None or now.utcoffset() is None or not isinstance(report, dict):
        return []
    physical = report.get("asPhysicalUnit")
    histogram = physical.get("histogramData") if isinstance(physical, dict) else None
    if not isinstance(histogram, list):
        return []

    # Field-verified: PreviousDay always names the previous calendar day,
    # even between 00:00 and 02:00; CurrentDay is new from midnight.
    rows: list[tuple[str, str, int, float]] = []
    for period in _PERIODS:
        day = (now.date() - timedelta(days=1)
               if period == "PreviousDay" else now.date())
        # From 00:00 to 02:00 the new day has NO completed slots.
        completed = 12 if period == "PreviousDay" else min(12, now.hour // 2)
        for cloud_name, kind in _SERIES.items():
            matching = [
                item for item in histogram
                if isinstance(item, dict)
                and item.get("series") == cloud_name
                and item.get("period") == period
            ]
            if len(matching) != 1:
                continue
            samples = matching[0].get("items")
            if not isinstance(samples, list) or len(samples) != 12:
                continue
            values = []
            for sample in samples:
                value = sample.get("y") if isinstance(sample, dict) else None
                if (isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value) or not 0 <= value < 100000):
                    values = []
                    break
                values.append(round(float(value), 6))
            if len(values) != 12:
                continue
            for index, value in enumerate(values[:completed]):
                rows.append((day.isoformat(), kind, index, value))
    return rows


def apply_report(
    original: dict[str, Any], report: Any, now: datetime,
) -> tuple[dict[str, Any], bool]:
    """Return candidate ledger; caller must persist before publishing."""
    state = valid_state(original)
    if state is None:
        raise ValueError("Invalid stored Smc gas ledger")
    rows = _rows(report, now)
    if not rows:
        return state, False

    changed = False
    days = state["days"]
    for day, kind, idx, amount in rows:
        slots = days.setdefault(day, {}).setdefault(kind, {})
        slot = str(idx)
        old = slots.get(slot)
        if old == amount:
            continue
        delta = amount - (old if old is not None else 0.0)
        updated_total = round(state["totals"][kind] + delta, 6)
        if updated_total < 0:
            raise ValueError("Invalid negative gas meter after correction")
        state["totals"][kind] = updated_total
        slots[slot] = amount
        changed = True

    if state["tracking_start"] is None and days:
        state["tracking_start"] = min(days)
        changed = True

    # Only close a day if both usage streams contain all 12 distinct slots,
    # in particular the midnight 22:00-00:00 slot. Never invent empty data.
    yesterday = now.date() - timedelta(days=1)
    completed_days = sorted(
        date.fromisoformat(day)
        for day, values in days.items()
        if date.fromisoformat(day) <= yesterday
        and all(len(values.get(kind, {})) == 12 for kind in _SERIES.values())
    )

    if not state["continuity_lost"]:
        for day in completed_days:
            closed = state["closed_through"]
            if closed is not None and day <= date.fromisoformat(closed):
                continue
            expected = (
                date.fromisoformat(closed) + timedelta(days=1)
                if closed is not None else date.fromisoformat(state["tracking_start"])
            )
            if day > expected:
                state["continuity_lost"] = True
                changed = True
                break
            if day == expected:
                state["closed_through"] = day.isoformat()
                state["previous_day_verified"] = True
                changed = True

        # The web PreviousDay report normally persists all day. If it is
        # absent at 02:00 and yesterday is still incomplete, refuse to
        # claim correct statistics instead of fabricating an empty slot.
        if now.hour >= 2 and state["tracking_start"] is not None:
            previous = state["closed_through"]
            if (date.fromisoformat(state["tracking_start"]) <= yesterday
                    and (previous is None or date.fromisoformat(previous) < yesterday)):
                state["continuity_lost"] = True
                changed = True

    allowed = {(now.date() - timedelta(days=offset)).isoformat() for offset in range(3)}
    for day in list(days):
        if day not in allowed:
            del days[day]
            changed = True
    return state, changed


class StoredGasLedger:
    """A small Home Assistant .storage snapshot, scoped per config entry."""

    def __init__(self, hass: Any, entry_id: str) -> None:
        from homeassistant.helpers.storage import Store
        self._store = Store(hass, _VERSION, f"ariston_cube_gas_meter_v1_{entry_id}")
        self._state: dict[str, Any] | None = None

    async def async_apply(self, report: Any, now: datetime) -> dict[str, Any]:
        if self._state is None:
            raw = await self._store.async_load()
            if raw is None:
                self._state = empty_state()
            else:
                self._state = valid_state(raw)
                if self._state is None:
                    raise ValueError("Stored gas accounting format unsupported")
        candidate, changed = apply_report(self._state, report, now)
        if changed:
            await self._store.async_save(candidate)
        self._state = candidate

        yesterday = (now.date() - timedelta(days=1)).isoformat()
        if (candidate["continuity_lost"]
                or not candidate["previous_day_verified"]
                or candidate["closed_through"] != yesterday):
            return {"heating": None, "dhw": None, "history_complete": False}
        return {
            "heating": candidate["totals"]["heating"],
            "dhw": candidate["totals"]["dhw"],
            "history_complete": True,
        }
