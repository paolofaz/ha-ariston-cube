"""Redacted, persisted midnight Smc report snapshots for field diagnosis.

Contains ONLY the reported physical gas volumes (Smc), period names from a
strict allowlist, local capture time, and numeric series indices. No account,
plant ID, credentials, cookies, URLs, or full Ariston payloads are retained.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import math
from typing import Any

_ALLOWED_PERIODS = ("CurrentDay", "PreviousDay")
_ALLOWED_SERIES = ("Heating", "Dhw")
_MAX_SNAPSHOTS = 18
_RETENTION_HOURS = 40
_VERSION = 1


def _safe_values(series: Any) -> list[float] | None:
    """Recognize exactly twelve physical two-hour numeric slots."""
    if not isinstance(series, list) or len(series) != 12:
        return None
    values: list[float] = []
    for item in series:
        value = item.get("y") if isinstance(item, dict) else None
        if (isinstance(value, bool) or not isinstance(value, (float, int))
                or not math.isfinite(value) or value < 0 or value > 100000):
            return None
        values.append(round(float(value), 6))
    return values


def night_snapshot(payload: Any, now: datetime) -> dict[str, Any] | None:
    """Return a private-data-free snapshot for the 22:00–04:59 window."""
    if now.tzinfo is None or now.utcoffset() is None:
        return None
    if now.hour not in (22, 23, 0, 1, 2, 3, 4):
        return None
    if not isinstance(payload, dict):
        return None
    physical = payload.get("asPhysicalUnit")
    if not isinstance(physical, dict):
        return None
    rows = physical.get("histogramData")
    if not isinstance(rows, list):
        return None

    series: dict[str, dict[str, list[float] | None]] = {}
    for period in _ALLOWED_PERIODS:
        matches: dict[str, list[float] | None] = {}
        for name in _ALLOWED_SERIES:
            found = [
                row for row in rows
                if isinstance(row, dict) and row.get("series") == name
                and row.get("period") == period
            ]
            if not found:
                continue
            # Duplicate series are explicitly ambiguous, never silently
            # discard data by picking the first of several responses.
            matches[name] = (
                _safe_values(found[0].get("items"))
                if len(found) == 1 else None
            )
        if matches:
            series[period] = matches
    if not series:
        return None

    return {
        "captured_at": now.isoformat(timespec="seconds"),
        "clock_date": now.date().isoformat(),
        "clock_hour": now.hour,
        "utc_offset_minutes": int(now.utcoffset().total_seconds() // 60),
        "series": series,
    }


def add_snapshot(
    existing: Any, snapshot: dict[str, Any], now: datetime,
) -> list[dict[str, Any]]:
    """Keep a small, bounded local timeline, stable across HA restarts."""
    if existing is None:
        previous: list[dict[str, Any]] = []
    elif not isinstance(existing, list):
        raise ValueError("Unexpected stored Smc diagnostic shape")
    else:
        previous = existing
    threshold = now - timedelta(hours=_RETENTION_HOURS)
    saved = []
    for record in previous:
        if not isinstance(record, dict):
            raise ValueError("Unexpected stored Smc snapshot")
        raw_time = record.get("captured_at")
        if not isinstance(raw_time, str):
            raise ValueError("Malformed stored Smc timestamp")
        try:
            stamp = datetime.fromisoformat(raw_time)
        except ValueError as exc:
            raise ValueError("Malformed stored Smc timestamp") from exc
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Naive stored Smc timestamp")
        if stamp >= threshold and stamp != datetime.fromisoformat(snapshot["captured_at"]):
            saved.append(record)
    saved.append(snapshot)
    saved.sort(key=lambda row: datetime.fromisoformat(row["captured_at"]))
    return saved[-_MAX_SNAPSHOTS:]


class NightSmcHistory:
    """Persistent overnight diagnostics, sharing the existing cloud fetch."""

    def __init__(self, hass: Any, entry_id: str) -> None:
        from homeassistant.helpers.storage import Store

        self._store = Store(hass, _VERSION, f"ariston_cube_night_smc_{entry_id}")
        self._history: list[dict[str, Any]] | None = None

    async def async_record(self, report: Any, now: datetime) -> dict[str, Any]:
        if self._history is None:
            restored = await self._store.async_load()
            if restored is not None and not isinstance(restored, list):
                raise ValueError("Stored overnight report format is invalid")
            self._history = restored if restored is not None else []

        snapshot = night_snapshot(report, now)
        if snapshot is not None:
            updated = add_snapshot(self._history, snapshot, now)
            # Persist *before* exposing the snapshots to the entity, so
            # a restart does not wipe the critical 00:xx evidence.
            await self._store.async_save(updated)
            self._history = updated

        return {
            "snapshots": list(self._history),
            "count": len(self._history),
            "last_capture": (
                self._history[-1]["captured_at"] if self._history else None
            ),
        }
