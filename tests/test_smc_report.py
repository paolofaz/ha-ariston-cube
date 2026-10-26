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


def test_midnight_reports_yesterdays_last_22_to_00_bucket():
    # The vendor's CurrentDay rolls over at 02:00, NOT midnight.
    result = smc.parse_smc_report(report(), NOW.replace(day=27, hour=0))
    assert result["reported_date"] == "2026-10-26"
    assert result["completed_interval"] == "22:00–24:00"
    assert result["heating_smc_today"] == 66.0
    assert result["heating_smc_2h"] == 11.0
    # At 02:00 CurrentDay begins the new calendar-day accumulation.
    after = smc.parse_smc_report(report(), NOW.replace(day=27, hour=2))
    assert after["reported_date"] == "2026-10-27"
    assert after["completed_interval"] == "00:00–02:00"
    assert after["heating_smc_today"] == 0.0


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
