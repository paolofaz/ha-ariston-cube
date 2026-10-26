"""Pure tests for the actual Cube S time-prog schema (no cloud/HA)."""

import importlib
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PACKAGE = "_ariston_cube_testpkg"
if PACKAGE not in sys.modules:
    pkg = types.ModuleType(PACKAGE)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = pkg

weekly = importlib.import_module(PACKAGE + ".weekly_program")


def sample():
    return {"ChZn1": {"plans": [
        {"days": [0, 6], "slices": [
            {"from": 1080, "temp": 0},
            {"from": 420, "temp": 1},
            {"from": 0, "temp": 0},
        ]},
        {"days": [1, 2], "slices": [
            {"from": 360, "temp": 1},
            {"from": 1320, "temp": 0},
        ]},
        {"days": [3, 4, 5], "slices": [
            {"from": 480, "temp": 1},
            {"from": 1020, "temp": 0},
        ]},
    ]}}


def test_three_plans_cover_week_and_sorted_slices():
    parsed = weekly.parse_weekly_program(sample())
    assert parsed["plan_count"] == 3
    assert len(parsed["days"]) == 7
    assert weekly.daily_description(parsed["days"]["Domenica"]) == (
        "00:00 Economy · 07:00 Comfort · 18:00 Economy"
    )
    assert weekly.daily_description(parsed["days"]["Lunedì"]) == (
        "06:00 Comfort · 22:00 Economy"
    )
    assert weekly.daily_description(parsed["days"]["Sabato"]) == (
        "00:00 Economy · 07:00 Comfort · 18:00 Economy"
    )


def test_incomplete_week_preserves_missing_days_as_none():
    parsed = weekly.parse_weekly_program({
        "ChZn1": {"plans": [{"days": [0], "slices": [{"from": 0, "temp": 0}]}]}
    })
    assert parsed["days"]["Lunedì"] is None
    assert weekly.daily_description(parsed["days"]["Lunedì"]) is None


@pytest.mark.parametrize("bad", [
    {},
    {"ChZn1": {}},
    {"ChZn1": {"plans": []}},
    {"ChZn1": {"plans": [{"days": [7], "slices": [{"from": 0, "temp": 0}]}]}},
    {"ChZn1": {"plans": [{"days": [True], "slices": [{"from": 0, "temp": 0}]}]}},
    {"ChZn1": {"plans": [{"days": [0], "slices": [{"from": 1440, "temp": 0}]}]}},
    {"ChZn1": {"plans": [{"days": [0], "slices": [{"from": 10, "temp": 2}]}]}},
    {"ChZn1": {"plans": [{"days": [0], "slices": [{"from": 0, "temp": 0},
                                                 {"from": 0, "temp": 1}]}]}},
    {"ChZn1": {"plans": [{"days": [0], "slices": []}]}},
    {"ChZn1": {"plans": [
        {"days": [0], "slices": [{"from": 0, "temp": 0}]},
        {"days": [0], "slices": [{"from": 120, "temp": 1}]},
    ]}},
])
def test_rejects_malformed_or_conflicting_schedule(bad):
    with pytest.raises(ValueError):
        weekly.parse_weekly_program(bad)


def test_weekly_schedule_platform_is_read_only_and_infrequent():
    schedule_source = (ROOT / "schedule_coordinator.py").read_text()
    sensor_source = (ROOT / "sensor.py").read_text()
    assert "timedelta(hours=3)" in schedule_source
    assert "AristonWeeklySchedule" in sensor_source
    assert "entry.async_create_background_task" in sensor_source
    assert "async_read_weekly_program" in schedule_source
    assert "async_set_" not in (ROOT / "weekly_program.py").read_text()
