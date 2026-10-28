"""Pure offline Cube S clone safety checks and full-week equivalence."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import importlib
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    package = types.ModuleType(PKG)
    package.__path__ = [str(ROOT)]
    sys.modules[PKG] = package

clone = importlib.import_module(PKG + ".weekly_clone")
weekly = importlib.import_module(PKG + ".weekly_program")
fingerprints = importlib.import_module(PKG + ".weekly_preview")


def source():
    """Realistic grouped full-week schedule; sun/sat share a plan."""
    return {"ChZn1": {
        "opaque_gateway_extra": {"revision": 3, "write_safe": False},
        "plans": [
            {"days": [0, 6], "slices": [
                {"from": 0, "temp": 0},
                {"from": 420, "temp": 1},
                {"from": 1080, "temp": 0},
            ]},
            {"days": [1, 2, 3, 4, 5], "slices": [
                {"from": 0, "temp": 0},
                {"from": 360, "temp": 1},
                {"from": 1290, "temp": 0},
            ]},
        ],
    }}


def distinct_source():
    """Seven days with genuinely different timetables."""
    raw = source()
    original = raw["ChZn1"]["plans"]
    raw["ChZn1"]["plans"] = [
        {"days": [day], "slices": deepcopy(
            original[0]["slices"] if day in (0, 6)
            else original[1]["slices"]
        )} for day in range(7)
    ]
    for day, plan in enumerate(raw["ChZn1"]["plans"]):
        if day not in (0, 6):
            # Different weekday start for each Mon–Fri, still 15-min aligned.
            plan["slices"][1]["from"] = 360 + day * 15
    return raw


def build(raw, day, destinations):
    return clone.build_clone_weekly_days(
        raw, day, destinations, fingerprints.weekly_read_fingerprint(raw)
    )


def test_one_source_clones_to_wed_fri_sunday_in_single_plans_body():
    raw = distinct_source()
    original = deepcopy(raw)
    before = weekly.parse_weekly_program(raw)["days"]
    body, expected, proposal = build(raw, 1, [3, 5, 0])
    assert set(body) == {"plans"}
    assert len(body["plans"]) <= len(original["ChZn1"]["plans"])
    assert proposal["source_weekday"] == "Lunedì"
    assert proposal["destination_weekdays"] == ["Domenica", "Mercoledì", "Venerdì"]
    assert proposal["changed_destinations"] == [0, 3, 5]
    assert proposal["can_submit"] is False
    assert proposal["status"] == "preview_only_no_cloud_write"
    monday = before["Lunedì"]
    for day in ("Mercoledì", "Venerdì", "Domenica"):
        assert expected["days"][day] == monday
        assert proposal["before"][day] == before[day]
        assert proposal["after"][day] == monday
    for day in ("Lunedì", "Martedì", "Giovedì", "Sabato"):
        assert expected["days"][day] == before[day]
    assert raw == original
    assert clone.confirm_weekly_write(
        {"ChZn1": {"plans": body["plans"], "opaque_gateway_extra":
                    raw["ChZn1"]["opaque_gateway_extra"]}}, expected
    )


def test_clone_some_matching_destinations_left_untouched():
    raw = source()  # Tuesday and Wednesday already share Monday's programme
    before = deepcopy(raw)
    proposal = clone.preview_clone_weekly_days(raw, 1, [2, 3, 0])
    assert proposal["destinations"] == [0, 2, 3]
    assert proposal["changed_destinations"] == [0]
    assert proposal["changed_weekdays"] == ["Domenica"]
    body, expected, _ = build(raw, 1, [2, 3, 0])
    assert expected["days"]["Domenica"] == expected["days"]["Lunedì"]
    assert expected["days"]["Martedì"] == expected["days"]["Lunedì"]
    assert raw == before
    assert len(body["plans"]) <= 2


def test_cloning_all_six_weekdays_never_creates_more_plans():
    raw = distinct_source()
    destinations = [0, 2, 3, 4, 5, 6]
    body, expected, result = build(raw, 1, destinations)
    assert len(body["plans"]) == 1
    assert body["plans"][0]["days"] == list(range(7))
    for day in weekly.DAYS_IT:
        assert expected["days"][day] == result["source_schedule"]


@pytest.mark.parametrize("source_day,destinations,reason", [
    (-1, [1], "Source"),
    (7, [0], "Source"),
    (True, [1], "Source"),
    ("1", [3], "Source"),
    (1, [], "one and six"),
    (1, list(range(7)), "one and six"),
    (1, [1], "Source weekday cannot"),
    (1, [0, 1, 3], "Source weekday cannot"),
    (1, [0, 0], "twice"),
    (1, [False], "integers"),
    (1, ["3"], "integers"),
    (1, [7], "integers"),
    (1, None, "one and six"),
    (1, {3, 5}, "one and six"),
])
def test_invalid_sources_or_targets_do_not_produce_payload(
        source_day, destinations, reason):
    with pytest.raises(ValueError, match=reason):
        clone.preview_clone_weekly_days(source(), source_day, destinations)


def test_complete_noop_is_rejected_without_post():
    with pytest.raises(ValueError, match="already match"):
        build(source(), 1, [2, 3, 4, 5])


def test_stale_whole_zone_fingerprint_blocks_cloning():
    raw = source()
    preview = clone.preview_clone_weekly_days(raw, 1, [0])
    raw["ChZn1"]["opaque_gateway_extra"]["revision"] = 4
    with pytest.raises(ValueError, match="changed since preview"):
        clone.build_clone_weekly_days(
            raw, 1, [0], preview["source_fingerprint"]
        )


@pytest.mark.parametrize("where", ["plan", "slice"])
def test_unknown_plan_or_slice_metadata_blocks_write(where):
    raw = source()
    if where == "plan":
        raw["ChZn1"]["plans"][1]["metadata"] = {"not_supported": True}
    else:
        raw["ChZn1"]["plans"][1]["slices"][1]["metadata"] = "keep"
    with pytest.raises(ValueError, match="metadata"):
        build(raw, 1, [0])


def test_missing_cloud_day_causes_refusal_before_write():
    raw = source()
    raw["ChZn1"]["plans"][1]["days"] = [1, 2, 3, 4]
    with pytest.raises(ValueError, match="All seven"):
        build(raw, 1, [0])


def test_bad_readback_on_unselected_day_is_detected():
    raw = source()
    body, expected, _ = build(raw, 1, [0])
    after = {"ChZn1": {"plans": deepcopy(body["plans"])}}
    assert clone.confirm_weekly_write(after, expected)
    other_plan = next(plan for plan in after["ChZn1"]["plans"] if 6 in plan["days"])
    other_plan["slices"][1]["from"] += 15
    assert not clone.confirm_weekly_write(after, expected)


def test_invalid_fingerprint_refused():
    with pytest.raises(ValueError, match="fingerprint"):
        clone.build_clone_weekly_days(source(), 1, [0], "not-a-fingerprint")


def test_pure_clone_helper_has_no_cloud_write_dependencies():
    code = (ROOT / "weekly_clone.py").read_text()
    assert "aiohttp" not in code
    assert "async def " not in code
    assert "async_write" not in code
    assert "gas_ledger" not in code
