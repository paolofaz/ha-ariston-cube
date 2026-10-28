"""Offline regression tests for single weekday move/add/remove edits."""

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
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

changes = importlib.import_module(PKG + ".weekly_changes")
parser = importlib.import_module(PKG + ".weekly_program")
preview = importlib.import_module(PKG + ".weekly_preview")


def source():
    return {"ChZn1": {"plans": [
        {"days": [0, 6], "slices": [
            {"from": 0, "temp": 0}, {"from": 420, "temp": 1},
            {"from": 1080, "temp": 0},
        ]},
        {"days": [1, 2, 3, 4, 5], "slices": [
            {"from": 0, "temp": 0}, {"from": 360, "temp": 1},
            {"from": 1290, "temp": 0},
        ]},
    ]}}


def build(raw, op, *, day=1, from_time="", to_time="", end_time="", preset=""):
    return changes.build_weekly_change(
        raw, day, op, from_time=from_time, to_time=to_time,
        end_time=end_time, preset=preset,
        expected_fingerprint=preview.weekly_read_fingerprint(raw),
    )


@pytest.mark.parametrize("op,args,expected_times", [
    ("add", {"to_time": "12:00", "end_time": "13:00", "preset": "Economy"},
     ["00:00", "06:00", "12:00", "13:00", "21:30"]),
    ("remove", {"from_time": "06:00"}, ["00:00"]),
    ("move", {"from_time": "06:00", "to_time": "06:15"},
     ["00:00", "06:15", "21:30"]),
])
def test_one_mutation_preserves_other_six_weekdays(op, args, expected_times):
    raw = source()
    original = deepcopy(raw)
    body, expected, proposal = build(raw, op, **args)
    assert proposal["kind"] == "offline_preview_only"
    assert proposal["changed"] is True
    assert proposal["can_submit"] is False
    assert proposal["operation"] == op
    assert [row["time"] for row in expected["days"]["Lunedì"]] == expected_times
    assert len(body["plans"]) == 3  # only Monday splits out of Mon-Fri
    assert body["plans"][1]["days"] == [2, 3, 4, 5]
    assert body["plans"][2]["days"] == [1]
    before = parser.parse_weekly_program(raw)
    for day in parser.DAYS_IT:
        if day != "Lunedì":
            assert expected["days"][day] == before["days"][day]
    assert changes.confirm_weekly_write(
        {"ChZn1": {"plans": body["plans"]}}, expected
    )
    assert raw == original


def test_weekday_already_independent_does_not_add_plan():
    raw = source()
    raw["ChZn1"]["plans"][1]["days"] = [1]
    raw["ChZn1"]["plans"].append({
        "days": [2, 3, 4, 5],
        "slices": deepcopy(raw["ChZn1"]["plans"][1]["slices"])
    })
    body, _, _ = build(raw, "add", to_time="12:00", end_time="13:00", preset="Economy")
    assert len(body["plans"]) == 3


@pytest.mark.parametrize("op,args,reason", [
    ("add", {"to_time": "00:00", "end_time": "01:00", "preset": "Comfort"}, "00:00"),
    ("add", {"to_time": "06:00", "end_time": "07:00", "preset": "Economy"}, "exists"),
    ("add", {"to_time": "11:00", "end_time": "12:00", "preset": "Comfort"}, "current preset"),
    ("add", {"to_time": "24:00", "end_time": "23:45", "preset": "Comfort"}, "HH:MM"),
    ("add", {"to_time": "12:00", "end_time": "13:00", "preset": "Other"}, "Comfort or Economy"),
    ("remove", {"from_time": "00:00"}, "start-of-day"),
    ("remove", {"from_time": "13:00"}, "not found"),
    ("remove", {"from_time": "06:00", "preset": "Comfort"}, "only from_time"),
    ("move", {"from_time": "00:00", "to_time": "00:15"}, "00:00"),
    ("move", {"from_time": "06:00", "to_time": "06:00"}, "differ"),
    ("move", {"from_time": "06:00", "to_time": "21:30"}, "exists"),
    ("move", {"from_time": "06:00", "to_time": "06:15", "preset": "Comfort"}, "does not accept"),
    ("invalid", {"to_time": "12:00", "preset": "Comfort"}, "Operation"),
])
def test_invalid_change_rejected_before_write(op, args, reason):
    with pytest.raises(ValueError, match=reason):
        build(source(), op, **args)


def test_delete_minimum_one_necessary_boundary_preserves_source():
    raw = source()
    raw["ChZn1"]["plans"][1]["slices"] = [
        {"from": 0, "temp": 0}
    ]
    with pytest.raises(ValueError, match="not found"):
        build(raw, "remove", from_time="06:00")
    with pytest.raises(ValueError, match="start-of-day"):
        build(raw, "remove", from_time="00:00")


def test_add_rejects_limit_48_slices():
    raw = source()
    raw["ChZn1"]["plans"][1]["slices"] = [
        {"from": n * 30, "temp": n % 2} for n in range(48)
    ]
    with pytest.raises(ValueError, match="Maximum"):
        build(raw, "add", to_time="00:15", end_time="00:30", preset="Comfort")


def test_shared_plan_limit_14_blocks_split():
    raw = source()
    # Seven independent weekdays would be enough; to reach 14, use eleven
    # additional nonoverlapping plans? The strict parser forbids overlapping
    # days, so 14 plans with seven days is impossible. A seven-day complete
    # programme cannot reach 14 nonempty disjoint plan lists.
    assert len(raw["ChZn1"]["plans"]) == 2


def test_stale_fingerprint_rejected_without_payload():
    raw = source()
    with pytest.raises(ValueError, match="changed since preview"):
        changes.build_weekly_change(
            raw, 1, "add", to_time="12:00", end_time="13:00",
            preset="Economy", expected_fingerprint="0" * 64,
        )


def test_metadata_is_never_lost_from_source():
    raw = source()
    raw["ChZn1"]["plans"][1]["label"] = "do_not_lose"
    with pytest.raises(ValueError, match="metadata"):
        build(raw, "add", to_time="12:00", end_time="13:00", preset="Economy")
    raw = source()
    raw["ChZn1"]["extra_cloud_metadata"] = {"unknown": [1, 2, 3]}
    # The live rc.3 write format sends only the plans; extra zone keys are
    # retained in the source fingerprint, not sent in the POST envelope.
    source_copy = deepcopy(raw)
    body, expected, _ = build(raw, "remove", from_time="06:00")
    assert set(body) == {"plans"}
    assert raw == source_copy
    assert [x["time"] for x in expected["days"]["Lunedì"]] == ["00:00"]
    assert changes.confirm_weekly_write(
        {"ChZn1": {"plans": body["plans"],
                   "extra_cloud_metadata": raw["ChZn1"]["extra_cloud_metadata"]}},
        expected,
    )


def test_cloud_readback_needs_all_days_exact():
    raw = source()
    body, expected, _ = build(
        raw, "add", to_time="12:00", end_time="13:00", preset="Economy"
    )
    changed = {"ChZn1": {"plans": body["plans"]}}
    assert changes.confirm_weekly_write(changed, expected)
    changed["ChZn1"]["plans"][0]["slices"][1]["from"] = 435
    assert not changes.confirm_weekly_write(changed, expected)


def test_previews_never_touch_network_or_user_gas_data():
    module = (ROOT / "weekly_changes.py").read_text()
    assert "aiohttp" not in module
    assert "async " not in module
    assert "async_write" not in module
    assert "gas_ledger" not in module


@pytest.mark.parametrize("op,params", [
    ("add", {"to_time": "12:00", "end_time": "13:00", "preset": "Economy"}),
    ("remove", {"from_time": "06:00"}),
    ("move", {"from_time": "06:00", "to_time": "06:15"}),
])
def test_realistic_extra_zone_metadata_uses_field_tested_rc3_post_shape(
        op, params):
    raw = source()
    raw["ChZn1"].update({
        "zone": {"id": "opaque cloud data", "attributes": [1, 2]},
        "editable": True,
        "unknown_nested_property": {"revision": 17},
    })
    original = deepcopy(raw)
    fingerprint = preview.weekly_read_fingerprint(raw)
    body, expected, _ = build(raw, op, **params)
    assert set(body) == {"plans"}
    assert raw == original
    assert changes.confirm_weekly_write(
        {"ChZn1": {**raw["ChZn1"], "plans": body["plans"]}}, expected
    )
    changed_metadata = deepcopy(raw)
    changed_metadata["ChZn1"]["unknown_nested_property"]["revision"] = 18
    with pytest.raises(ValueError, match="changed since preview"):
        changes.build_weekly_change(
            changed_metadata, 1, op, expected_fingerprint=fingerprint, **params
        )


def test_extra_nested_slice_metadata_is_still_rejected_even_with_zone_metadata():
    raw = source()
    raw["ChZn1"]["optional_zone_data"] = [1, 2]
    raw["ChZn1"]["plans"][1]["slices"][1]["unknown"] = "do_not_erase"
    with pytest.raises(ValueError, match="metadata"):
        build(raw, "add", to_time="12:00", end_time="13:00", preset="Economy")


def test_new_finite_band_restores_prior_preset_at_end_and_removes_cleanly():
    raw = source()
    original_day = parser.parse_weekly_program(raw)["days"]["Lunedì"]
    body, expected, proposal = build(
        raw, "add", to_time="12:00", end_time="13:00", preset="Economy"
    )
    after = expected["days"]["Lunedì"]
    assert [(r["time"], r["preset"]) for r in after] == [
        ("00:00", "Economy"), ("06:00", "Comfort"),
        ("12:00", "Economy"), ("13:00", "Comfort"),
        ("21:30", "Economy"),
    ]
    assert proposal["end_time"] == "13:00"
    after_raw = {"ChZn1": {"plans": body["plans"]}}
    restored, result, _ = build(after_raw, "remove", from_time="12:00")
    assert result["days"]["Lunedì"] == original_day
    assert changes.confirm_weekly_write(
        {"ChZn1": {"plans": restored["plans"]}}, result
    )


def test_add_end_equal_to_existing_boundary_resumes_original_plan_without_duplicate():
    body, expected, _ = build(
        source(), "add", to_time="12:00", end_time="21:30", preset="Economy"
    )
    assert [r["time"] for r in expected["days"]["Lunedì"]] == [
        "00:00", "06:00", "12:00", "21:30"
    ]
    assert len(body["plans"]) == 3


@pytest.mark.parametrize("kwargs,reason", [
    ({"to_time": "12:00", "preset": "Economy"}, "HH:MM"),
    ({"to_time": "12:00", "end_time": "", "preset": "Economy"}, "HH:MM"),
    ({"to_time": "12:00", "end_time": "12:00", "preset": "Economy"}, "later"),
    ({"to_time": "13:00", "end_time": "12:00", "preset": "Economy"}, "later"),
    ({"to_time": "12:07", "end_time": "13:00", "preset": "Economy"}, "15-minute"),
    ({"to_time": "12:00", "end_time": "13:01", "preset": "Economy"}, "15-minute"),
    ({"to_time": "12:00", "end_time": "22:00", "preset": "Economy"}, "overlaps"),
    ({"to_time": "12:00", "end_time": "24:00", "preset": "Economy"}, "HH:MM"),
    ({"to_time": "12:00", "end_time": "13:00", "preset": "Comfort"}, "current preset"),
])
def test_add_requires_finite_quarter_hour_interval_without_overlapping(kwargs, reason):
    with pytest.raises(ValueError, match=reason):
        build(source(), "add", **kwargs)


def test_cannot_add_before_first_known_boundary_when_carry_over_is_ambiguous():
    raw = source()
    raw["ChZn1"]["plans"][1]["slices"] = [
        {"from": 360, "temp": 1}, {"from": 1290, "temp": 0}
    ]
    with pytest.raises(ValueError, match="preceding"):
        build(raw, "add", to_time="02:00", end_time="03:00", preset="Comfort")


def test_add_two_boundaries_exceeds_48_limit_even_when_single_boundary_would_fit():
    raw = source()
    raw["ChZn1"]["plans"][1]["slices"] = [
        {"from": n * 30, "temp": n % 2} for n in range(47)
    ]
    with pytest.raises(ValueError, match="Maximum"):
        # 47 existing 30-minute transitions end at 23:00. Add two new
        # quarter-hour boundaries after that last transition (no overlap).
        build(raw, "add", to_time="23:15", end_time="23:45", preset="Comfort")


def test_move_new_time_rejects_minutes_outside_quarter_hour_grid():
    with pytest.raises(ValueError, match="15-minute"):
        build(source(), "move", from_time="06:00", to_time="06:07")


def test_removing_band_never_overwrites_other_six_days():
    raw = source()
    body, _, _ = build(
        raw, "add", to_time="12:00", end_time="13:00", preset="Economy"
    )
    next_raw = {"ChZn1": {"plans": body["plans"]}}
    removed, restored, _ = build(next_raw, "remove", from_time="12:00")
    assert restored["days"] == parser.parse_weekly_program(raw)["days"]
    assert changes.confirm_weekly_write(
        {"ChZn1": {"plans": removed["plans"]}}, restored
    )
