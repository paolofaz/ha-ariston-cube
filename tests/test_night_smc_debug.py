"""Tests for private-data-free overnight Smc diagnostics and restart retention."""

from datetime import datetime, timedelta
import asyncio
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
debug = importlib.import_module(PKG + ".night_smc_debug")
ROME = ZoneInfo("Europe/Rome")
MON_2240 = datetime(2026, 10, 26, 22, 40, tzinfo=ROME)
TUE_0010 = datetime(2026, 10, 27, 0, 10, tzinfo=ROME)
TUE_0210 = datetime(2026, 10, 27, 2, 10, tzinfo=ROME)


def report(*, last_monday=0.25, tuesday_first=0.0):
    def rows(h, d):
        return [
            {"period": "CurrentDay", "series": "Heating",
             "items": [{"x": i, "y": v} for i, v in enumerate(h)]},
            {"period": "CurrentDay", "series": "Dhw",
             "items": [{"x": i, "y": v} for i, v in enumerate(d)]},
        ]
    return {
        "plantId": "DO_NOT_STORE_THIS",
        "token": "SECRET_COOKIE_VALUE",
        "asKwhRaw": {"histogramData": [{"value": 12345}]},
        "asPhysicalUnit": {
            "account": "secret@example.invalid",
            "histogramData": rows(
                [0.1] * 11 + [last_monday],
                [tuesday_first] + [0.0] * 11,
            ),
        },
    }


def test_22_00_02_snapshots_have_distinct_capture_times_and_no_account_data():
    a = debug.night_snapshot(report(), MON_2240)
    b = debug.night_snapshot(report(), TUE_0010)
    c = debug.night_snapshot(report(last_monday=0, tuesday_first=0.25), TUE_0210)
    assert a["clock_date"] == "2026-10-26"
    assert b["clock_date"] == "2026-10-27"
    assert a["series"]["CurrentDay"]["Heating"][11] == 0.25
    assert b["series"]["CurrentDay"]["Heating"][11] == 0.25
    assert c["series"]["CurrentDay"]["Heating"][11] == 0
    assert c["series"]["CurrentDay"]["Dhw"][0] == 0.25
    recorded = str([a, b, c])
    for secret in ("DO_NOT_STORE_THIS", "SECRET_COOKIE_VALUE", "secret@example.invalid"):
        assert secret not in recorded
    assert a["utc_offset_minutes"] == 60


def test_daytime_is_skipped_to_keep_a_small_debug_history():
    at_noon = MON_2240.replace(hour=12)
    assert debug.night_snapshot(report(), at_noon) is None
    assert debug.night_snapshot({"account": "secret"}, TUE_0010) is None


def test_invalid_duplicate_and_non_numeric_slots_are_fail_closed():
    original = report()
    original["asPhysicalUnit"]["histogramData"][0]["items"][11]["y"] = True
    sample = debug.night_snapshot(original, TUE_0010)
    assert sample["series"]["CurrentDay"]["Heating"] is None
    assert sample["series"]["CurrentDay"]["Dhw"] is not None
    original = report()
    original["asPhysicalUnit"]["histogramData"].append(
        original["asPhysicalUnit"]["histogramData"][0]
    )
    sample = debug.night_snapshot(original, TUE_0010)
    assert sample["series"]["CurrentDay"]["Heating"] is None


def test_bounded_and_unique_on_exact_capture_stamp():
    original = debug.night_snapshot(report(), TUE_0010)
    assert debug.add_snapshot(None, original, TUE_0010) == [original]
    assert debug.add_snapshot([original], original, TUE_0010) == [original]
    slots = []
    for day in range(4):
        for minute in (10, 20, 30, 40, 50):
            at = TUE_0010 + timedelta(days=day, minutes=minute)
            snapshot = debug.night_snapshot(report(), at)
            slots = debug.add_snapshot(slots, snapshot, at)
    assert len(slots) <= 18
    assert slots[-1]["clock_date"] == "2026-10-30"
    assert all("captured_at" in s for s in slots)


def test_store_retains_snapshots_across_new_collector_instances(monkeypatch):
    records = {}

    class MockStore:
        def __init__(self, hass, version, key):
            self.key = key

        async def async_load(self):
            return records.get(self.key)

        async def async_save(self, data):
            records[self.key] = data

    storage_mod = types.ModuleType("homeassistant.helpers.storage")
    storage_mod.Store = MockStore
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.storage", storage_mod)
    first = debug.NightSmcHistory(None, "fake-entry")
    received = asyncio.run(first.async_record(report(), TUE_0010))
    assert received["count"] == 1
    second = debug.NightSmcHistory(None, "fake-entry")
    restored = asyncio.run(second.async_get_snapshots())
    assert len(restored) == 1
    assert restored[0]["clock_hour"] == 0
    asyncio.run(second.async_record(report(), TUE_0210))
    assert len(records["ariston_cube_night_smc_fake-entry"]) == 2


def test_debug_entity_removed_and_cumulative_gas_totals_enabled():
    source = (ROOT / "sensor.py").read_text()
    setup = source.split("async def async_setup_entry", 1)[1].split(
        "\nclass AristonTemperature", 1
    )[0]
    assert "AristonSmcOvernightDebug(smc)" not in setup
    assert "AristonCumulativeGas(smc" in setup
    coordinator = (ROOT / "smc_coordinator.py").read_text()
    assert "_SMC_TOTALS_VERIFIED = False" not in coordinator
    assert "self.night_history.async_record(" not in coordinator
    assert "self.gas_ledger.async_apply(report, now)" in coordinator
