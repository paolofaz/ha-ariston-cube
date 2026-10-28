"""Single explicitly requested Cube S schedule write experiment.

POST method is advertised by the real gateway, but its JSON contract is NOT
verified. This code does not run automatically and is not part of stable.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .weekly_preview import preview_one_boundary_move, weekly_read_fingerprint
from .weekly_program import DAYS_IT, parse_weekly_program


def build_test_write(
    raw: Any, day: int, from_time: str, to_time: str, expected_fingerprint: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Propose a complete seven-day plan for exactly one boundary movement."""
    if not isinstance(expected_fingerprint, str) or len(expected_fingerprint) != 64:
        raise ValueError("Missing 64-character preview fingerprint")
    if weekly_read_fingerprint(raw) != expected_fingerprint:
        raise ValueError("Cube S schedule changed since the preview; no POST sent")

    proposal = preview_one_boundary_move(raw, day, from_time, to_time)
    original = parse_weekly_program(raw)
    if any(value is None for value in original["days"].values()):
        raise ValueError("All seven original weekdays must be available")

    zone = raw["ChZn1"]
    plans = zone["plans"]
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != {"days", "slices"}:
            raise ValueError("Unexpected plan metadata; no POST sent")
        if not all(
            isinstance(item, dict) and set(item) == {"from", "temp"}
            for item in plan["slices"]
        ):
            raise ValueError("Unexpected slice metadata; no POST sent")

    target_index = next(
        i for i, plan in enumerate(plans) if day in plan["days"]
    )
    old_minute = proposal["before"][
        next(i for i, s in enumerate(proposal["before"]) if s["time"] == from_time)
    ]["minute"]
    new_minute = proposal["after"][
        next(i for i, s in enumerate(proposal["after"]) if s["time"] == to_time)
    ]["minute"]

    replacement = deepcopy(plans[target_index])
    replacement["days"] = [day]
    for slice_ in replacement["slices"]:
        if slice_["from"] == old_minute:
            slice_["from"] = new_minute
    replacement["slices"].sort(key=lambda item: item["from"])

    updated_plans = deepcopy(plans)
    if len(plans[target_index]["days"]) == 1:
        updated_plans[target_index] = replacement
    else:
        if len(plans) >= 14:
            raise ValueError("Cannot split shared weekdays: plan limit reached")
        updated_plans[target_index]["days"] = [
            d for d in plans[target_index]["days"] if d != day
        ]
        updated_plans.insert(target_index + 1, replacement)

    expected = parse_weekly_program({"ChZn1": {"plans": updated_plans}})
    for label in DAYS_IT:
        correct = proposal["after"] if label == DAYS_IT[day] else original["days"][label]
        if expected["days"][label] != correct:
            raise ValueError("Proposed write would alter an unexpected time band")

    # This is a HYPOTHESIS based on the observed GET and other Ariston APIs.
    return {"plans": updated_plans}, expected, proposal


def confirm_weekly_write(raw_after: Any, expected: dict[str, Any]) -> bool:
    """Require an exact match across all seven weekdays after the POST."""
    try:
        actual = parse_weekly_program(raw_after)
    except (ValueError, KeyError, TypeError):
        return False
    return actual["days"] == expected["days"]
