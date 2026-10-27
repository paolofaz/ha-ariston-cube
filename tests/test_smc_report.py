"""Deterministic tests for direct web-portal Smc (no kWh conversion)."""

from datetime import datetime
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
smc = importlib.import_module(PKG + ".smc_report")
NOW = datetime(2026, 10, 26, 16, 44, tzinfo=ZoneInfo("Europe/Rome"))


def report(heating=None, dhw=None):
    if heating is None:
        heating = [float(i) for i in range(12)]
    if dhw is None:
        dhw = [float(i) / 10 for i in range(12)]
    return {
        "asPhysicalUnit": {
            "histogramData": [
                {"series": "Heating", "period": "CurrentDay",
                 "items": [{"x": str(i), "y": v} for i, v in enumerate(heating)]},
                {"series": "Dhw", "period": "CurrentDay",
                 "items": [{"x": str(i), "y": v} for i, v in enumerate(dhw)]},
            ]
        },
        "asKwhRaw": {"histogramData": [
            {"series": "Heating", "period": "CurrentDay",
             "items": [{"y": 99999.0}] * 12},
        ]},
    }


def test_reads_real_smc_not_as_kwh():
    data = smc.parse_smc_report(report(), NOW)
    assert data["completed_interval"] == "14:00–16:00"
    assert data["heating_smc_today"] == 28.0
    assert data["heating_smc_2h"] == 7.0
    assert data["dhw_smc_today"] == 2.8
    assert data["dhw_smc_2h"] == 0.7
    assert data["heating_smc_today"] != 99999.0


def test_observed_web_midnight_reset_uses_previousday_not_currentday():
    # Field diagnostic 2026-10-26 at 22:40 and 2026-10-27 at 00:10/02:10.
    from copy import deepcopy
    before = report(
        heating=[0, 0, 0, 1.3, 1.24, 0.08, 0.5, 0, 0.4, 0.3, 0.4, 0],
        dhw=[0, 0, 0, 0.2, 0.01, 0.01, 0.2, 0, 0.09, 0.03, 0.01, 0],
    )
    last = smc.parse_smc_report(before, NOW.replace(hour=22, minute=40))
    assert last["heating_smc_today"] == 4.22
    assert last["dhw_smc_today"] == 0.55

    midnight = report(heating=[0] * 12, dhw=[0] * 12)
    previous = {
        "Heating": [0, 0, 0, 1.3, 1.24, 0.08, 0.5, 0, 0.4, 0.3, 0.4, 0.4],
        "Dhw": [0, 0, 0, 0.2, 0.01, 0.01, 0.2, 0, 0.09, 0.03, 0.01, 0.3],
    }
    rows = midnight["asPhysicalUnit"]["histogramData"]
    for kind, values in previous.items():
        rows.append({
            "period": "PreviousDay", "series": kind,
            "items": [{"x": i, "y": v} for i, v in enumerate(values)],
        })
    when = NOW.replace(day=27, hour=0, minute=10)
    result = smc.parse_smc_report(midnight, when)
    assert result["reported_date"] == "2026-10-27"
    assert result["completed_interval_date"] == "2026-10-26"
    assert result["completed_interval"] == "22:00–00:00"
    assert result["heating_smc_today"] == 0
    assert result["dhw_smc_today"] == 0
    assert result["heating_smc_2h"] == 0.4
    assert result["dhw_smc_2h"] == 0.3

    again = smc.parse_smc_report(midnight, when.replace(hour=2))
    assert again["completed_interval_date"] == "2026-10-27"
    assert again["completed_interval"] == "00:00–02:00"
    assert again["heating_smc_2h"] == 0
    assert again["dhw_smc_2h"] == 0
    assert again["heating_smc_today"] == 0


def test_missing_previous_day_does_not_fabricate_midnight_last_bucket():
    data = smc.parse_smc_report(
        report(heating=[0] * 12, dhw=[0] * 12),
        NOW.replace(day=27, hour=0),
    )
    assert data["heating_smc_2h"] is None
    assert data["dhw_smc_2h"] is None
    assert data["heating_smc_today"] == 0


def test_no_fabricated_zero_from_missing_or_bad_series():
    for incoming in ({}, {"asKwhRaw": {"histogramData": []}},
                     report(heating=[True] * 12),
                     report(heating=[-2.0] * 12),
                     report(heating=[float("nan")] * 12),
                     report(heating=[1.0] * 11)):
        parsed = smc.parse_smc_report(incoming, NOW)
        assert parsed["heating_smc_today"] is None
    broken = report()
    broken["asPhysicalUnit"]["histogramData"].append(
        broken["asPhysicalUnit"]["histogramData"][0]
    )
    assert smc.parse_smc_report(broken, NOW)["heating_smc_2h"] is None


def test_smc_entities_not_misrepresented_as_lifetime_gas_meter():
    source = (ROOT / "sensor.py").read_text()
    cls = source.split("class AristonPhysicalGas", 1)[1].split("class AristonCumulativeGas", 1)[0]
    assert '_attr_native_unit_of_measurement = "Smc"' in cls
    assert "_attr_state_class" not in cls
    assert "_attr_device_class" not in cls
    assert "AristonSmcCoordinator" in source
