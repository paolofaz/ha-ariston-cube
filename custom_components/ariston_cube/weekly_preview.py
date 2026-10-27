"""Validated, OFFLINE preview of a Cube S weekly schedule edit.

This module intentionally has no cloud client, write endpoint, or HA services.
The result is NOT an Ariston write payload. The official write contract for
ChZn1 has not been validated on the target boiler.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from .weekly_program import DAYS_IT, parse_weekly_program

MAX_SLICES = 48


def weekly_read_fingerprint(raw: Any) -> str:
    """Fingerprint the original COMPLETE zone payload for stale-edit checks.

    Unknown source fields are included in the digest; they must not disappear
    merely because the read-only UI currently ignores them. No raw schedule
    content is returned by this helper or written to logs.
    """
    parse_weekly_program(raw)
    try:
        encoded = json.dumps(
            raw["ChZn1"], ensure_ascii=True, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("Cube S source schedule cannot be fingerprinted") from exc
    return sha256(encoded).hexdigest()


def _validate_changes(changes: Any) -> list[dict[str, Any]]:
    """Accept only known Ariston read-schema slice primitives, not a POST body."""
    if not isinstance(changes, list) or not 1 <= len(changes) <= MAX_SLICES:
        raise ValueError("A day needs between 1 and 48 schedule changes")
    seen: set[int] = set()
    prepared = []
    for item in changes:
        if not isinstance(item, dict) or set(item) != {"from", "temp"}:
            raise ValueError("Only 'from' and 'temp' are accepted in a preview")
        minute, preset = item["from"], item["temp"]
        if type(minute) is not int or not 0 <= minute < 1440:
            raise ValueError("Change time must be an integer minute of the day")
        if type(preset) is not int or preset not in (0, 1):
            raise ValueError("Unknown Economy/Comfort preset")
        if minute in seen:
            raise ValueError("Duplicate schedule change")
        seen.add(minute)
        prepared.append({
            "minute": minute,
            "time": f"{minute // 60:02}:{minute % 60:02}",
            "preset": "Comfort" if preset == 1 else "Economy",
        })
    return sorted(prepared, key=lambda change: change["minute"])


def preview_day_edit(raw: Any, day: str, changes: Any) -> dict[str, Any]:
    """Build a UI-only draft for one known weekday without touching the boiler.

    Changes use the KNOWN READ-SCHEMA slice codes as input only. They are not
    serialized to any mobile/web request: the write endpoint is unverified.
    """
    parsed = parse_weekly_program(raw)
    if day not in DAYS_IT:
        raise ValueError("Unknown weekday")
    before = parsed["days"][day]
    if before is None:
        raise ValueError("Cannot edit a missing source-day schedule")
    after = _validate_changes(changes)
    days = deepcopy(parsed["days"])
    days[day] = deepcopy(after)
    return {
        "kind": "offline_preview_only",
        "can_submit": False,
        "weekday": day,
        "source_fingerprint": weekly_read_fingerprint(raw),
        "changed": before != after,
        "before": deepcopy(before),
        "after": deepcopy(after),
        "days": days,
    }


def source_unchanged(preview: dict[str, Any], fresh_read: Any) -> bool:
    """Detect concurrent changes; fail closed if a fresh read is not valid."""
    if (not isinstance(preview, dict)
            or preview.get("kind") != "offline_preview_only"
            or preview.get("can_submit") is not False):
        return False
    digest = preview.get("source_fingerprint")
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    try:
        return digest == weekly_read_fingerprint(fresh_read)
    except (TypeError, KeyError, ValueError):
        return False
