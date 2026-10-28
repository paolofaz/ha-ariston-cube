"""Safely copy one Cube S weekday schedule onto multiple selected weekdays.

Builds the same proven {"plans": [...]} POST envelope as the existing
single-weekday writer. One fresh cloud read, full-zone fingerprint, a single
explicitly approved POST, and exact seven-day readback are required upstream.
No cloud access or Home Assistant imports in this module.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .weekly_preview import weekly_read_fingerprint
from .weekly_program import DAYS_IT, parse_weekly_program
from .weekly_write import confirm_weekly_write

_FINGERPRINT_RE = re.compile(r"[a-f0-9]{64}\Z")


def _selected_days(source_day: Any, destinations: Any) -> list[int]:
    if type(source_day) is not int or not 0 <= source_day <= 6:
        raise ValueError("Source weekday must be an integer from 0 to 6")
    if not isinstance(destinations, list) or not 1 <= len(destinations) <= 6:
        raise ValueError("Choose between one and six destination weekdays")
    if any(type(day) is not int or not 0 <= day <= 6 for day in destinations):
        raise ValueError("Destination weekdays must be integers from 0 to 6")
    if source_day in destinations:
        raise ValueError("Source weekday cannot also be a destination")
    if len(set(destinations)) != len(destinations):
        raise ValueError("Destination weekdays cannot be selected twice")
    return sorted(destinations)


def _validated_programme(raw: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    parsed = parse_weekly_program(raw)
    if any(slices is None for slices in parsed["days"].values()):
        raise ValueError("All seven weekdays must have a cloud programme")
    plans = raw["ChZn1"]["plans"]
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != {"days", "slices"}:
            raise ValueError("Unknown plan metadata; no cloud POST")
        if not all(
            isinstance(change, dict) and set(change) == {"from", "temp"}
            for change in plan["slices"]
        ):
            raise ValueError("Unknown slice metadata; no cloud POST")
    return parsed, plans


def preview_clone_weekly_days(
    raw: Any, source_day: int, destinations: list[int],
) -> dict[str, Any]:
    """Preview one source -> several destinations without any cloud writes."""
    chosen = _selected_days(source_day, destinations)
    parsed, _ = _validated_programme(raw)
    source_schedule = parsed["days"][DAYS_IT[source_day]]
    previous = {
        DAYS_IT[day]: deepcopy(parsed["days"][DAYS_IT[day]])
        for day in chosen
    }
    changed = [
        day for day in chosen
        if parsed["days"][DAYS_IT[day]] != source_schedule
    ]
    if not changed:
        raise ValueError("All selected destinations already match the source")

    return {
        "status": "preview_only_no_cloud_write",
        "kind": "clone",
        "can_submit": False,
        "changed": True,
        "source_day": source_day,
        "source_weekday": DAYS_IT[source_day],
        "destinations": chosen,
        "destination_weekdays": [DAYS_IT[day] for day in chosen],
        "changed_destinations": changed,
        "changed_weekdays": [DAYS_IT[day] for day in changed],
        "source_schedule": deepcopy(source_schedule),
        "before": previous,
        "after": {
            DAYS_IT[day]: deepcopy(source_schedule)
            for day in chosen
        },
        "source_fingerprint": weekly_read_fingerprint(raw),
    }


def build_clone_weekly_days(
    raw: Any, source_day: int, destinations: list[int],
    expected_fingerprint: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prepare a minimal existing-plans rewrite, changing only target days.

    Reuses the source plan; never multiplies the number of cloud plans.
    Unselected weekdays retain their original slices; selected destinations
    already identical to the source are left untouched.
    """
    if not isinstance(expected_fingerprint, str) or not _FINGERPRINT_RE.fullmatch(
        expected_fingerprint
    ):
        raise ValueError("Missing valid full-week preview fingerprint")
    if weekly_read_fingerprint(raw) != expected_fingerprint:
        raise ValueError("Cube S programme changed since preview; no POST sent")

    proposal = preview_clone_weekly_days(raw, source_day, destinations)
    before, original_plans = _validated_programme(raw)
    changed_set = set(proposal["changed_destinations"])
    new_plans = deepcopy(original_plans)

    matching_indexes = [
        i for i, plan in enumerate(new_plans) if source_day in plan["days"]
    ]
    if len(matching_indexes) != 1:
        raise ValueError("Source weekday has no unique plan")
    source_index = matching_indexes[0]

    for idx, plan in enumerate(new_plans):
        if idx == source_index:
            plan["days"] = sorted(set(plan["days"]) | changed_set)
        else:
            plan["days"] = [
                day for day in plan["days"] if day not in changed_set
            ]
    # All empty plans are removed; no added or guessed plan schema.
    new_plans = [plan for plan in new_plans if plan["days"]]
    expected = parse_weekly_program({"ChZn1": {"plans": new_plans}})

    for day in range(7):
        label = DAYS_IT[day]
        should_be = (
            proposal["source_schedule"]
            if day in changed_set else before["days"][label]
        )
        if expected["days"][label] != should_be:
            raise ValueError("Clone would modify an unselected weekday")
    if len(new_plans) > len(original_plans):
        raise ValueError("Clone may not expand the number of plans")
    return {"plans": new_plans}, expected, proposal


__all__ = (
    "preview_clone_weekly_days", "build_clone_weekly_days",
    "confirm_weekly_write",
)
