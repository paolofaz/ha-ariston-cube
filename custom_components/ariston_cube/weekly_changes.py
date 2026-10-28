"""One guarded Cube S weekday edit: move, add finite band, or remove a boundary.

Offline pure helpers. Cloud operations live in api.py, require a fresh GET,
a matching full-week fingerprint, one POST, then seven-day readback.
The first (00:00) boundary stays fixed for add/remove/move in this editor.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .weekly_preview import (
    MAX_SLICES, preview_day_edit, preview_one_boundary_move,
    weekly_read_fingerprint,
)
from .weekly_program import DAYS_IT, parse_weekly_program
from .weekly_write import confirm_weekly_write

_ALLOWED = ("move", "add", "remove")
_TIME_RE = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]\Z")


def _minute(text: str) -> int:
    if not isinstance(text, str) or not _TIME_RE.fullmatch(text):
        raise ValueError("Use an HH:MM time from 00:00 to 23:59")
    return int(text[:2]) * 60 + int(text[3:])


def preview_weekly_change(
    raw: Any, day: int, operation: str, *,
    from_time: str = "", to_time: str = "", end_time: str = "",
    preset: str = "",
) -> dict[str, Any]:
    """Preview exactly one change to a known weekday, with NO cloud write."""
    if type(day) is not int or not 0 <= day <= 6:
        raise ValueError("Day must be Sunday=0 through Saturday=6")
    if operation not in _ALLOWED:
        raise ValueError("Operation must be move, add or remove")
    before = parse_weekly_program(raw)["days"][DAYS_IT[day]]
    if before is None:
        raise ValueError("Cannot edit a weekday missing from the source")
    if operation == "move":
        if preset or end_time:
            raise ValueError("A move does not accept a preset or an end_time")
        if _minute(to_time) % 15 != 0:
            raise ValueError("New times must use 15-minute steps")
        if _minute(from_time) == 0 or _minute(to_time) == 0:
            raise ValueError("00:00 boundary is fixed in this editor")
        result = preview_one_boundary_move(raw, day, from_time, to_time)
    elif operation == "add":
        if from_time:
            raise ValueError("Adding a band does not accept from_time")
        start_minute = _minute(to_time)
        end_minute = _minute(end_time)  # REQUIRED: never silently ends at 24:00
        if start_minute == 0:
            raise ValueError("00:00 boundary is fixed")
        if start_minute % 15 or end_minute % 15:
            raise ValueError("Start/end must be 15-minute steps")
        if end_minute <= start_minute:
            raise ValueError("End time must be later than start time")
        if preset not in ("Comfort", "Economy"):
            raise ValueError("New band must use Comfort or Economy")
        if any(row["minute"] == start_minute for row in before):
            raise ValueError("A boundary already exists at the start time")

        preceding = [row for row in before if row["minute"] < start_minute]
        if not preceding:
            # We do not guess the preset inherited from the preceding day.
            raise ValueError("Cannot determine preset preceding the new band")
        original_preset = preceding[-1]["preset"]
        if original_preset == preset:
            raise ValueError("New band matches the current preset; no change")
        # Do not overwrite a pre-existing transition. Exactly at a following
        # boundary the old plan already resumes, so no new end row is needed.
        existing_inside = [
            row["minute"] for row in before
            if start_minute < row["minute"] < end_minute
        ]
        if existing_inside:
            raise ValueError("New band overlaps an existing schedule boundary")
        restore_at_end = not any(
            row["minute"] == end_minute for row in before
        )
        required_slices = 1 + int(restore_at_end)
        if len(before) + required_slices > MAX_SLICES:
            raise ValueError("Maximum number of weekday time bands reached")

        changes = [
            {"from": row["minute"], "temp": 1 if row["preset"] == "Comfort" else 0}
            for row in before
        ]
        changes.append({
            "from": start_minute, "temp": 1 if preset == "Comfort" else 0
        })
        if restore_at_end:
            changes.append({
                "from": end_minute,
                "temp": 1 if original_preset == "Comfort" else 0,
            })
        result = preview_day_edit(raw, DAYS_IT[day], changes)
    else:
        if to_time or end_time or preset:
            raise ValueError("Removing a boundary accepts only from_time")
        old_minute = _minute(from_time)
        if old_minute == 0:
            raise ValueError("Cannot remove the start-of-day boundary")
        if not any(row["minute"] == old_minute for row in before):
            raise ValueError("Boundary to remove was not found")
        if len(before) <= 1:
            raise ValueError("Cannot remove the last time band")
        # Removing a finite inserted band must also remove its redundant
        # restoration boundary, when the following preset is exactly the
        # same as the preset preceding the deleted band. This restores the
        # original day rather than leaving a no-op time change behind.
        index = next(
            i for i, row in enumerate(before) if row["minute"] == old_minute
        )
        redundant_end = None
        if (
            0 < index < len(before) - 1
            and before[index + 1]["preset"] == before[index - 1]["preset"]
        ):
            redundant_end = before[index + 1]["minute"]
        changes = [
            {"from": row["minute"], "temp": 1 if row["preset"] == "Comfort" else 0}
            for row in before
            if row["minute"] != old_minute and row["minute"] != redundant_end
        ]
        result = preview_day_edit(raw, DAYS_IT[day], changes)

    if not result["changed"]:
        raise ValueError("No effective weekday change")
    result["day_index"] = day
    result["operation"] = operation
    result["from_time"] = from_time
    result["to_time"] = to_time
    result["end_time"] = end_time
    result["preset"] = preset
    return result


def build_weekly_change(
    raw: Any, day: int, operation: str, *,
    from_time: str = "", to_time: str = "", end_time: str = "",
    preset: str = "", expected_fingerprint: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Construct one full-week POST body only if every safety check passes."""
    if (
        not isinstance(expected_fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_fingerprint)
    ):
        raise ValueError("Missing valid preview fingerprint")
    if weekly_read_fingerprint(raw) != expected_fingerprint:
        raise ValueError("Cube S schedule changed since preview; no POST sent")

    proposal = preview_weekly_change(
        raw, day, operation, from_time=from_time, to_time=to_time,
        end_time=end_time, preset=preset,
    )
    original = parse_weekly_program(raw)
    if any(week is None for week in original["days"].values()):
        raise ValueError("All seven original weekdays must be available")

    zone = raw["ChZn1"]
    # The live Cube S GET includes additional ChZn1 keys. The already field-
    # tested rc.3 move command POSTs ONLY {"plans": ...} even when those
    # keys exist, and validates every weekday on the subsequent GET.
    #
    # Keep the identical proven POST envelope for add/remove. Extra zone
    # keys remain in the whole-zone fingerprint, so any concurrent change
    # to them invalidates the preview; they are never silently stripped
    # from the source or serialized into an unverified write schema.
    # Unknown metadata *inside* plans/slices is still rejected below.
    plans = zone["plans"]
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != {"days", "slices"}:
            raise ValueError("Unexpected plan metadata; no POST sent")
        if not all(
            isinstance(item, dict) and set(item) == {"from", "temp"}
            for item in plan["slices"]
        ):
            raise ValueError("Unexpected slice metadata; no POST sent")
    indexes = [i for i, plan in enumerate(plans) if day in plan["days"]]
    if len(indexes) != 1:
        raise ValueError("Selected day has no unique source plan")
    index = indexes[0]

    replacement = deepcopy(plans[index])
    replacement["days"] = [day]
    replacement["slices"] = [
        {"from": row["minute"], "temp": 1 if row["preset"] == "Comfort" else 0}
        for row in proposal["after"]
    ]

    updated_plans = deepcopy(plans)
    if len(plans[index]["days"]) == 1:
        updated_plans[index] = replacement
    else:
        if len(plans) >= 14:
            raise ValueError("Cannot split shared weekdays: plan limit reached")
        updated_plans[index]["days"] = [
            d for d in plans[index]["days"] if d != day
        ]
        updated_plans.insert(index + 1, replacement)

    expected = parse_weekly_program({"ChZn1": {"plans": updated_plans}})
    for label in DAYS_IT:
        permitted = proposal["after"] if label == DAYS_IT[day] else original["days"][label]
        if expected["days"][label] != permitted:
            raise ValueError("Proposed POST would change another weekday")
    return {"plans": updated_plans}, expected, proposal


__all__ = (
    "preview_weekly_change", "build_weekly_change", "confirm_weekly_write",
)
