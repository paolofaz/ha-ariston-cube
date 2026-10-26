"""Tests for Ariston monthly gas report—no cumulative counter assumptions."""

import importlib
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    m = types.ModuleType(PKG)
    m.__path__ = [str(ROOT)]
    sys.modules[PKG] = m
reports = importlib.import_module(PKG + ".gas_report")


def test_monthly_heating_acs_are_distinct():
    report = {"LastMonth": [
        {"gas": 230, "elect": 12},
        {"gas": 30, "elect": 8},
    ]}
    assert reports.parse_last_month_gas(report) == {
        "heating": 230.0, "dhw": 30.0
    }


def test_missing_values_are_unavailable_not_zero():
    assert reports.parse_last_month_gas({"LastMonth": []}) == {
        "heating": None, "dhw": None
    }
    assert reports.parse_last_month_gas({"LastMonth": [
        {"gas": 0}, {"gas": False},
    ]}) == {"heating": 0.0, "dhw": None}


def test_invalid_overflow_and_bad_shape_fail_closed():
    assert reports.parse_last_month_gas({"LastMonth": [
        {"gas": float("nan")}, {"gas": -1},
    ]}) == {"heating": None, "dhw": None}
    assert reports.parse_last_month_gas({"LastMonth": [
        {"gas": 4}, {"gas": 9}, {"gas": 3},
    ]}) == {"heating": None, "dhw": None}


def test_sensor_never_has_cumulative_energy_state_class():
    source = (ROOT / "sensor.py").read_text()
    klass = source.split("class AristonLastMonthGas", 1)[1]
    assert "_attr_state_class" not in klass
    assert '"gas_last_month_{report_key}"' in klass
    assert "UnitOfEnergy.KILO_WATT_HOUR" in klass
    assert "AristonGasCoordinator" in source


def test_low_frequency_gas_refresh_and_explicit_period():
    content = (ROOT / "gas_coordinator.py").read_text()
    assert "timedelta(hours=6)" in content
    assert "async_read_energy_account" in content
