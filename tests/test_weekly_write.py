"""Checks for explicitly requested, single-shot Cube S schedule field writes."""

from __future__ import annotations

from copy import deepcopy
import importlib
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    package = types.ModuleType(PKG)
    package.__path__ = [str(ROOT)]
    sys.modules[PKG] = package

writer = importlib.import_module(PKG + ".weekly_write")
preview = importlib.import_module(PKG + ".weekly_preview")
parser = importlib.import_module(PKG + ".weekly_program")


def sample():
    return {"ChZn1": {"plans": [
        {"days": [0, 6], "slices": [
            {"from": 0, "temp": 0}, {"from": 420, "temp": 1},
            {"from": 1080, "temp": 0},
        ]},
        {"days": [1, 2, 3, 4, 5], "slices": [
            {"from": 0, "temp": 0}, {"from": 345, "temp": 1},
            {"from": 1290, "temp": 0},
        ]},
    ]}}


def test_shared_monday_split_preserves_six_other_days():
    source = sample()
    untouched = deepcopy(source)
    fingerprint = preview.weekly_read_fingerprint(source)
    body, expected, local = writer.build_test_write(
        source, 1, "05:45", "06:00", fingerprint
    )
    assert set(body) == {"plans"}
    assert len(body["plans"]) == 3
    assert local["weekday"] == "Lunedì"
    assert local["changed"] is True
    assert local["can_submit"] is False
    original = parser.parse_weekly_program(source)
    for day in parser.DAYS_IT:
        if day != "Lunedì":
            assert expected["days"][day] == original["days"][day]
    assert [s["time"] for s in expected["days"]["Lunedì"]] == [
        "00:00", "06:00", "21:30"
    ]
    assert writer.confirm_weekly_write(
        {"ChZn1": {"plans": body["plans"]}}, expected
    )
    assert source == untouched


def test_singleton_day_changes_in_place():
    source = sample()
    source["ChZn1"]["plans"][1]["days"] = [1]
    source["ChZn1"]["plans"].append({"days": [2, 3, 4, 5], "slices": [
        {"from": 0, "temp": 0}, {"from": 345, "temp": 1},
        {"from": 1290, "temp": 0},
    ]})
    body, _, _ = writer.build_test_write(
        source, 1, "05:45", "06:00",
        preview.weekly_read_fingerprint(source)
    )
    assert len(body["plans"]) == len(source["ChZn1"]["plans"])


def test_fingerprint_mismatch_blocks_before_write():
    with pytest.raises(ValueError, match="changed since the preview"):
        writer.build_test_write(sample(), 1, "05:45", "06:00", "0" * 64)


@pytest.mark.parametrize("day,old,new", [
    (7, "05:45", "06:00"),
    (True, "05:45", "06:00"),
    (1, "06:15", "06:00"),
    (1, "05:45", "21:30"),
    (1, "05:45", "05:45"),
])
def test_invalid_requested_change_rejected(day, old, new):
    source = sample()
    with pytest.raises(ValueError):
        writer.build_test_write(
            source, day, old, new, preview.weekly_read_fingerprint(source)
        )


def test_incomplete_week_is_never_submitted():
    source = sample()
    source["ChZn1"]["plans"][1]["days"] = [1, 2, 3, 4]
    with pytest.raises(ValueError, match="seven"):
        writer.build_test_write(
            source, 1, "05:45", "06:00", preview.weekly_read_fingerprint(source)
        )


@pytest.mark.parametrize("where", ["plan", "slice"])
def test_unknown_cloud_metadata_does_not_get_lost(where):
    source = sample()
    if where == "plan":
        source["ChZn1"]["plans"][1]["extra"] = 100
    else:
        source["ChZn1"]["plans"][1]["slices"][1]["metadata"] = "important"
    with pytest.raises(ValueError, match="metadata"):
        writer.build_test_write(
            source, 1, "05:45", "06:00", preview.weekly_read_fingerprint(source)
        )


def test_after_readback_must_match_complete_week():
    source = sample()
    body, expected, _ = writer.build_test_write(
        source, 1, "05:45", "06:00", preview.weekly_read_fingerprint(source)
    )
    assert not writer.confirm_weekly_write(source, expected)
    changed_other_day = deepcopy({"ChZn1": {"plans": body["plans"]}})
    changed_other_day["ChZn1"]["plans"][0]["slices"][1]["from"] = 435
    assert not writer.confirm_weekly_write(changed_other_day, expected)
    assert not writer.confirm_weekly_write({}, expected)
