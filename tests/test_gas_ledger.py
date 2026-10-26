"""Regression tests for persisted cloud Smc accounting and daylight boundaries."""

from datetime import datetime, timedelta
from pathlib import Path
import importlib
import sys
import types
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg
gas = importlib.import_module(PKG + ".gas_ledger")
ROME = ZoneInfo("Europe/Rome")
MON = datetime(2026, 10, 26, 16, 25, tzinfo=ROME)
TUE = datetime(2026, 10, 27, 2, 25, tzinfo=ROME)
WED = datetime(2026, 10, 28, 2, 25, tzinfo=ROME)


def report(heating, dhw, *, yesterday=None):
    rows = [
        {"period": "CurrentDay", "series": "Heating",
         "items": [{"x": str(i), "y": x} for i, x in enumerate(heating)]},
        {"period": "CurrentDay", "series": "Dhw",
         "items": [{"x": str(i), "y": x} for i, x in enumerate(dhw)]},
    ]
    if yesterday is not None:
        for series, values in zip(("Heating", "Dhw"), yesterday):
            rows.append({
                "period": "PreviousDay", "series": series,
                "items": [{"x": str(i), "y": x} for i, x in enumerate(values)],
            })
    return {"asPhysicalUnit": {"histogramData": rows}}


def test_ledger_first_day_not_ready_until_full_yesterday_is_observed():
    s = gas.empty_state()
    s, changed = gas.apply_report(s, report([0.5] * 12, [0.1] * 12), MON)
    assert changed
    assert s["totals"]["heating"] == 4.0
    assert s["closed_through"] is None
    # Next day: all twelve slots of yesterday, including 22:00-00:00.
    s, changed = gas.apply_report(
        s, report([0.25] * 12, [0.05] * 12,
                  yesterday=([0.5] * 12, [0.1] * 12)), TUE,
    )
    assert changed
    assert s["totals"]["heating"] == 6.25
    assert s["totals"]["dhw"] == 1.25
    assert s["closed_through"] == "2026-10-26"
    assert s["previous_day_verified"] is True


def test_same_cloud_bucket_not_counted_twice_or_after_restart():
    first = gas.empty_state()
    raw = report([0.5] * 12, [0.1] * 12)
    applied, _ = gas.apply_report(first, raw, MON)
    exact_replay, changed = gas.apply_report(applied, raw, MON)
    assert not changed
    assert exact_replay["totals"] == applied["totals"]
    saved = gas.valid_state(exact_replay)
    assert saved == applied
    new_day = report([0.25] * 12, [0.05] * 12,
                     yesterday=([0.5] * 12, [0.1] * 12))
    closed, _ = gas.apply_report(saved, new_day, TUE)
    replayed, again = gas.apply_report(closed, new_day, TUE)
    assert not again
    assert closed["totals"] == replayed["totals"]


def test_late_cloud_downward_correction_is_signed_difference_not_reset():
    s = gas.empty_state()
    s, _ = gas.apply_report(
        s, report([0.5] * 12, [0.1] * 12,
                  yesterday=([1.0] * 12, [0.5] * 12)), MON,
    )
    original = s["totals"]["heating"]
    # A corrected yesterday's 22-24 period drops from 1.0 to 0.8.
    yesterday = [1.0] * 11 + [0.8]
    s2, changed = gas.apply_report(
        s, report([0.5] * 12, [0.1] * 12,
                  yesterday=(yesterday, [0.5] * 12)), MON,
    )
    assert changed
    assert round(s2["totals"]["heating"] - original, 6) == -0.2


def test_without_yesterdays_report_missing_final_slot_is_not_fabricated():
    s = gas.empty_state()
    s, _ = gas.apply_report(s, report([1.0] * 12, [0.5] * 12), MON)
    s, _ = gas.apply_report(s, report([1.0] * 12, [0.5] * 12), TUE)
    assert s["closed_through"] is None
    assert s["previous_day_verified"] is False
    assert s["tracking_start"] == "2026-10-26"


def test_skip_across_full_day_is_detected_as_an_unrecoverable_gap():
    s = gas.empty_state()
    s, _ = gas.apply_report(s, report([1.0] * 12, [1.0] * 12), MON)
    # Home Assistant was offline Tuesday; Wednesday's previous day is
    # Tuesday, so Monday's final slot can no longer be reconstructed.
    wed_report = report([1.0] * 12, [1.0] * 12,
                        yesterday=([1.0] * 12, [1.0] * 12))
    s, _ = gas.apply_report(s, wed_report, WED)
    assert s["continuity_lost"] is True
    assert s["closed_through"] is None


def test_no_unseen_future_slots_and_no_invalid_data():
    s = gas.empty_state()
    s, _ = gas.apply_report(
        s, report([1.0] * 8 + [999.0] * 4, [1.0] * 12), MON,
    )
    assert s["totals"]["heating"] == 8.0
    bad = report([-1.0] * 12, [True] * 12)
    s2, changed = gas.apply_report(s, bad, MON)
    assert not changed
    assert s2["totals"] == s["totals"]


def test_persisted_invalid_values_refuse_restore_instead_of_reset():
    s = gas.empty_state()
    assert gas.valid_state(s) == s
    s["totals"]["heating"] = float("nan")
    assert gas.valid_state(s) is None


def test_dst_date_slot_id_is_stable_on_repeated_local_clock():
    # Our 12 slot labels are the source histogram's fixed local two-hour
    # indices. Re-reading either DST fold never creates another slot key.
    before = datetime(2026, 10, 25, 2, 20, tzinfo=ROME, fold=0)
    after = before.replace(fold=1)
    s = gas.empty_state()
    data = report([0.1] * 12, [0.1] * 12)
    s, _ = gas.apply_report(s, data, before)
    s2, changed = gas.apply_report(s, data, after)
    assert not changed
    assert s2["totals"] == s["totals"]


def test_total_gas_entity_declares_ha_energy_supported_state_and_units():
    source = (ROOT / "sensor.py").read_text()
    ledger = source.split("class AristonCumulativeGas", 1)[1]
    assert "_attr_device_class = SensorDeviceClass.GAS" in ledger
    assert "_attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS" in ledger
    assert "_attr_state_class = SensorStateClass.TOTAL" in ledger
    assert "AristonPhysicalGas" in source
