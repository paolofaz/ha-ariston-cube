"""Regression tests for the real 00:00/02:00 Ariston Smc publication cycle."""

from datetime import datetime
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
MON_08 = datetime(2026, 10, 26, 8, 25, tzinfo=ROME)
MON_16 = MON_08.replace(hour=16)
TUE_00 = datetime(2026, 10, 27, 0, 20, tzinfo=ROME)
TUE_02 = TUE_00.replace(hour=2)
WED_02 = TUE_02.replace(day=28)


def report(heat, dhw, *, previous=None):
    rows = [
        {"period": "CurrentDay", "series": "Heating",
         "items": [{"x": str(i), "y": x} for i, x in enumerate(heat)]},
        {"period": "CurrentDay", "series": "Dhw",
         "items": [{"x": str(i), "y": x} for i, x in enumerate(dhw)]},
    ]
    if previous is not None:
        for series, values in zip(("Heating", "Dhw"), previous):
            rows.append({
                "period": "PreviousDay", "series": series,
                "items": [{"x": str(i), "y": x} for i, x in enumerate(values)],
            })
    return {"asPhysicalUnit": {"histogramData": rows}}


def test_two_equal_adjacent_fasce_add_separately_but_rereads_do_not():
    # 04-06 = 0.1 and 06-08 = 0.1, two separate keys in the same day.
    samples = [0.0, 0.0, 0.1, 0.1] + [0.0] * 8
    source = report(samples, [0.0] * 12)
    state, changed = gas.apply_report(gas.empty_state(), source, MON_08)
    assert changed
    assert state["totals"]["heating"] == 0.2
    slots = state["days"]["2026-10-26"]["heating"]
    assert slots["2"] == 0.1  # 04-06
    assert slots["3"] == 0.1  # 06-08
    repeated, changed = gas.apply_report(state, source, MON_08)
    assert changed is False
    assert repeated["totals"]["heating"] == 0.2
    assert gas.valid_state(repeated) == state  # survives persistent replay


def test_22_to_00_is_assigned_to_yesterday_then_new_day_starts_at_02():
    monday = report([0.5] * 12, [0.1] * 12)
    first, _ = gas.apply_report(gas.empty_state(), monday, MON_16)
    assert first["totals"]["heating"] == 4.0
    assert first["closed_through"] is None
    # At 00:10 the Cloud already moved Monday to PreviousDay.
    # New Tuesday CurrentDay is empty; Monday's final slot is still there.
    midnight_report = report(
        [0] * 12, [0] * 12,
        previous=([0.5] * 12, [0.1] * 12),
    )
    midnight, changed = gas.apply_report(first, midnight_report, TUE_00)
    assert changed
    assert midnight["totals"]["heating"] == 6.0
    assert midnight["totals"]["dhw"] == 1.2
    assert midnight["days"]["2026-10-26"]["heating"]["11"] == 0.5
    assert "2026-10-27" not in midnight["days"]
    assert midnight["closed_through"] == "2026-10-26"
    assert midnight["previous_day_verified"] is True
    # At 02:10 CurrentDay's first completed 00-02 slot is new usage.
    tuesday = report([0.25] * 12, [0.05] * 12)
    after, changed = gas.apply_report(midnight, tuesday, TUE_02)
    assert changed
    assert after["totals"]["heating"] == 6.25
    assert after["totals"]["dhw"] == 1.25
    assert after["days"]["2026-10-27"]["heating"]["0"] == 0.25
    assert after["closed_through"] == "2026-10-26"
    assert after["continuity_lost"] is False
    again, changed = gas.apply_report(after, tuesday, TUE_02)
    assert changed is False
    assert again == after


def test_same_bucket_correction_applies_only_delta_and_may_be_negative():
    original = [0.5] * 12
    state, _ = gas.apply_report(
        gas.empty_state(), report(original, [0.1] * 12), MON_16,
    )
    start = state["totals"]["heating"]
    revised = original.copy()
    revised[2] = 0.8
    updated, changed = gas.apply_report(
        state, report(revised, [0.1] * 12), MON_16,
    )
    assert changed
    assert round(updated["totals"]["heating"] - start, 6) == 0.3
    revised[2] = 0.2
    lower, changed = gas.apply_report(
        updated, report(revised, [0.1] * 12), MON_16,
    )
    assert changed
    assert round(lower["totals"]["heating"] - start, 6) == -0.3


def test_missed_midnight_final_bucket_is_detected_after_02_reset():
    monday = report([1.0] * 12, [0.5] * 12)
    state, _ = gas.apply_report(gas.empty_state(), monday, MON_16)
    # Nothing was read 00:00-02:00, and there is no PreviousDay report.
    state, _ = gas.apply_report(
        state, report([1.0] * 12, [0.5] * 12), TUE_02,
    )
    assert state["closed_through"] is None
    assert state["continuity_lost"] is True
    assert state["days"]["2026-10-26"]["heating"].get("11") is None


def test_real_previous_day_report_can_restore_midnight_gap():
    monday = report([1.0] * 12, [0.5] * 12)
    state, _ = gas.apply_report(gas.empty_state(), monday, MON_16)
    current = report(
        [0.2] * 12, [0.1] * 12,
        previous=([1.0] * 12, [0.5] * 12),
    )
    state, _ = gas.apply_report(state, current, TUE_02)
    assert state["continuity_lost"] is False
    assert state["closed_through"] == "2026-10-26"
    assert state["totals"]["heating"] == 12.2


def test_repeated_midnight_poll_is_the_same_day_and_same_slot():
    raw = report(
        [0] * 12, [0] * 12,
        previous=([0.5] * 12, [0.1] * 12),
    )
    s, _ = gas.apply_report(gas.empty_state(), raw, TUE_00)
    s2, changed = gas.apply_report(s, raw, TUE_00.replace(minute=40))
    assert changed is False
    assert s2["totals"]["heating"] == 6.0


def test_missing_day_not_invented_and_no_future_slot_consumption():
    s, _ = gas.apply_report(
        gas.empty_state(),
        report([1.0] * 8 + [999.0] * 4, [1.0] * 12),
        MON_16,
    )
    assert s["totals"]["heating"] == 8.0
    s2, changed = gas.apply_report(
        s, report([-1] * 12, [True] * 12), MON_16,
    )
    assert not changed
    assert s2 == s
    # Tuesday missed completely, Wednesday cannot fake the history.
    s3, _ = gas.apply_report(
        s, report([1] * 12, [1] * 12), WED_02,
    )
    assert s3["continuity_lost"] is True


def test_invalid_persisted_record_is_not_recreated_silently():
    s = gas.empty_state()
    assert gas.valid_state(s) == s
    s["totals"]["heating"] = float("nan")
    assert gas.valid_state(s) is None


def test_repeated_02_clock_hour_at_end_of_dst_not_double_counted():
    first = datetime(2026, 10, 25, 2, 20, tzinfo=ROME, fold=0)
    second = first.replace(fold=1)
    s, _ = gas.apply_report(
        gas.empty_state(), report([0.1] * 12, [0.1] * 12), first,
    )
    s2, changed = gas.apply_report(
        s, report([0.1] * 12, [0.1] * 12), second,
    )
    assert changed is False
    assert s2["totals"]["heating"] == 0.1


def test_cumulative_sensor_declares_home_assistant_gas_unit():
    source = (ROOT / "sensor.py").read_text()
    cumulative = source.split("class AristonCumulativeGas", 1)[1]
    assert "_attr_device_class = SensorDeviceClass.GAS" in cumulative
    assert "_attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS" in cumulative
    assert "_attr_state_class = SensorStateClass.TOTAL" in cumulative



def test_real_web_night_snapshots_no_duplicate_previousday_after_02():
    # Exact heating and ACS numbers from 26/27 Oct 2026 field diagnostics.
    previous_heating = [0, 0, 0, 1.3, 1.24, 0.08, 0.5, 0, 0.4, 0.3, 0.4, 0.4]
    previous_dhw = [0, 0, 0, 0.2, 0.01, 0.01, 0.2, 0, 0.09, 0.03, 0.01, 0.3]
    before_heating = previous_heating[:-1] + [0]
    before_dhw = previous_dhw[:-1] + [0]
    state, _ = gas.apply_report(
        gas.empty_state(), report(before_heating, before_dhw), MON_16.replace(hour=22)
    )
    assert state["totals"]["heating"] == 4.22
    assert state["totals"]["dhw"] == 0.55
    web_midnight = report(
        [0] * 12, [0] * 12,
        previous=(previous_heating, previous_dhw),
    )
    state, _ = gas.apply_report(state, web_midnight, TUE_00)
    assert state["totals"]["heating"] == 4.62
    assert state["totals"]["dhw"] == 0.85
    assert state["closed_through"] == "2026-10-26"
    replayed, changed = gas.apply_report(state, web_midnight, TUE_02)
    assert not changed
    assert replayed["totals"] == {"heating": 4.62, "dhw": 0.85}
    assert replayed["continuity_lost"] is False
