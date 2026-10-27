"""Tests for real two-hour Ariston gas sequences, not last-month reports."""

from datetime import datetime, timedelta
import importlib
from pathlib import Path
import sys
import types
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg
gas = importlib.import_module(PKG + ".gas_report")
NOW = datetime(2026, 10, 26, 14, 50, tzinfo=ZoneInfo("Europe/Rome"))


def raw(heat=None, dhw=None):
    heat = [0.0] * 16 + [1.0, 2.0, 0.0, 3.0, 0.0, 4.0, 1.0, 5.0] if heat is None else heat
    dhw = [0.0] * 16 + [0.0, 1.0, 0.0, 1.0, 2.0, 0.0, 1.0, 3.0] if dhw is None else dhw
    return [
        {"p": 1, "k": 7, "v": heat},
        {"p": 1, "k": 10, "v": dhw},
        {"p": 3, "k": 7, "v": [500.0] * 24},
        {"p": 1, "k": 20, "v": [9999.0] * 24},
    ]


def test_today_uses_calendar_day_and_two_hour_source():
    data = gas.parse_recent_gas(raw(), NOW)
    assert data["slot"] == "14:00–16:00"
    assert data["heating_2h"] == 5.0
    assert data["dhw_2h"] == 3.0
    # 00..14 = eight most recent two-hour bins.
    assert data["heating_today"] == 16.0
    assert data["dhw_today"] == 8.0


def test_midnight_does_not_roll_yesterday_into_today():
    at = NOW.replace(hour=0, minute=5)
    heat = [0.0] * 22 + [11.0, 2.0]
    out = gas.parse_recent_gas(raw(heat=heat), at)
    assert out["heating_today"] == 2.0
    assert out["heating_2h"] == 2.0


def test_missing_series_does_not_fabricate_zero():
    result = gas.parse_recent_gas([{"p": 1, "k": 7, "v": [1.0] * 24}], NOW)
    assert result["heating_today"] == 8.0
    assert result["dhw_today"] is None
    assert result["dhw_2h"] is None


def test_bad_buckets_and_duplicated_series_are_unavailable():
    for broken in ([True] * 24, [-1.0] * 24, [float("nan")] * 24, [1.0] * 23):
        data = gas.parse_recent_gas(raw(heat=broken), NOW)
        assert data["heating_today"] is None
        assert data["heating_2h"] is None
    duplicate = raw() + [{"p": 1, "k": 7, "v": [1.0] * 24}]
    data = gas.parse_recent_gas(duplicate, NOW)
    assert data["heating_today"] is None


def test_mobile_kwh_series_not_created_as_home_assistant_entities():
    source = (ROOT / "sensor.py").read_text()
    assert "AristonRecentGas" not in source
    assert "AristonGasCoordinator" not in source
    assert "recent_gas_" not in source
    assert "AristonPhysicalGas" in source

