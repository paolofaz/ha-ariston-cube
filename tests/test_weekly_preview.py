"""Offline-only Cube S schedule draft tests: no device writes."""

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
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

weekly_preview = importlib.import_module(PKG + ".weekly_preview")


def sample():
    return {"ChZn1": {
        "plans": [
            {"days": [0, 6], "slices": [{"from": 0, "temp": 0},
                                         {"from": 420, "temp": 1},
                                         {"from": 1080, "temp": 0}]},
            {"days": [1, 2, 3, 4, 5], "slices": [{"from": 360, "temp": 1},
                                                 {"from": 1320, "temp": 0}]},
        ],
        "unknown_extension": {"device_feature": ["unchanged"]},
    }}


def test_previews_one_weekday_and_keeps_all_other_days_unchanged():
    source = sample()
    original = deepcopy(source)
    before = importlib.import_module(PKG + ".weekly_program").parse_weekly_program(source)
    draft = weekly_preview.preview_day_edit(
        source, "Martedì", [
            {"from": 1320, "temp": 0},
            {"from": 480, "temp": 1},
            {"from": 0, "temp": 0},
        ],
    )
    assert draft["kind"] == "offline_preview_only"
    assert draft["can_submit"] is False
    assert draft["changed"] is True
    assert [x["time"] for x in draft["after"]] == ["00:00", "08:00", "22:00"]
    assert draft["days"]["Martedì"] == draft["after"]
    assert draft["days"]["Lunedì"] == before["days"]["Lunedì"]
    assert draft["days"]["Domenica"] == before["days"]["Domenica"]
    assert source == original
    assert weekly_preview.source_unchanged(draft, deepcopy(source))


def test_noop_preview_has_no_write_intent():
    source = sample()
    draft = weekly_preview.preview_day_edit(source, "Domenica", [
        {"from": 0, "temp": 0},
        {"from": 420, "temp": 1},
        {"from": 1080, "temp": 0},
    ])
    assert not draft["changed"]
    assert draft["can_submit"] is False


def test_stale_schedule_or_unknown_extension_prevents_reuse_of_draft():
    source = sample()
    draft = weekly_preview.preview_day_edit(
        source, "Martedì", [{"from": 0, "temp": 0}],
    )
    modified = deepcopy(source)
    modified["ChZn1"]["plans"][0]["slices"][1]["from"] = 480
    assert not weekly_preview.source_unchanged(draft, modified)
    extension = deepcopy(source)
    extension["ChZn1"]["unknown_extension"]["device_feature"].append("new")
    assert not weekly_preview.source_unchanged(draft, extension)
    unordered = deepcopy(source)
    unordered["ChZn1"] = dict(reversed(list(unordered["ChZn1"].items())))
    assert weekly_preview.source_unchanged(draft, unordered)


@pytest.mark.parametrize("changes", [
    [],
    [{"from": 0, "temp": 2}],
    [{"from": 0, "temp": True}],
    [{"from": True, "temp": 0}],
    [{"from": -1, "temp": 0}],
    [{"from": 1440, "temp": 0}],
    [{"from": 60.0, "temp": 1}],
    [{"from": "12:00", "temp": 1}],
    [{"from": 0, "temp": 0}, {"from": 0, "temp": 1}],
    [{"from": 0, "temp": 0, "write": True}],
    [{"from": i, "temp": 0} for i in range(49)],
    "not-a-list",
])
def test_invalid_or_ambiguous_edit_rejected(changes):
    with pytest.raises(ValueError):
        weekly_preview.preview_day_edit(sample(), "Martedì", changes)


def test_missing_day_and_unknown_weekday_fail_closed():
    source = sample()
    source["ChZn1"]["plans"][1]["days"] = [1, 3, 4, 5]
    with pytest.raises(ValueError, match="missing"):
        weekly_preview.preview_day_edit(source, "Martedì", [{"from": 0, "temp": 1}])
    with pytest.raises(ValueError, match="Unknown weekday"):
        weekly_preview.preview_day_edit(sample(), "Tuesday", [{"from": 0, "temp": 1}])


def test_invalid_source_and_invalid_concurrent_read_fail_closed():
    with pytest.raises(ValueError):
        weekly_preview.preview_day_edit({}, "Lunedì", [{"from": 0, "temp": 0}])
    draft = weekly_preview.preview_day_edit(
        sample(), "Lunedì", [{"from": 0, "temp": 0}],
    )
    assert weekly_preview.source_unchanged(draft, {}) is False
    assert weekly_preview.source_unchanged({"kind": "draft"}, sample()) is False


def test_no_cloud_write_route_or_service_in_offline_preview():
    code = (ROOT / "weekly_preview.py").read_text(encoding="utf-8")
    assert "aiohttp" not in code
    assert "async_set_weekly" not in code
    assert "self._request(" not in code
    assert "await " not in code
    assert "/api/v2/remote/timeProgs" not in code
    assert "async_write" not in code
