"""Pure Cube S and DHW state mapping tests without importing Home Assistant."""

import importlib
from pathlib import Path
import runpy
import sys
import types

DIR = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(DIR)]
    sys.modules[PKG] = pkg

model = importlib.import_module(PKG + ".model")
states = importlib.import_module(PKG + ".states")


def data(plant=1, zone=2, request=False, flame=False, dhw=2):
    return {
        "PlantMode": {"value": plant},
        "ZoneMode": {"value": zone},
        "ZoneHeatRequest": {"value": request},
        "IsFlameOn": {"value": flame},
        "DhwMode": {"value": dhw},
    }


def test_winter_manual_no_demand_is_idle():
    readings = data(plant=1, zone=2)
    assert states.heating_mode(readings) == "heat"
    assert states.heating_activity(readings) == "idle"
    assert states.zone_program(readings) == "manual"


def test_heating_requires_zone_demand_and_real_flame():
    assert states.heating_activity(data(request=True, flame=True)) == "heating"
    assert states.heating_activity(data(request=True, flame=False)) == "idle"
    assert states.heating_activity(data(request=False, flame=True)) == "idle"


def test_summer_global_off_even_when_zone_programmed():
    readings = data(plant=0, zone=3, request=True, flame=True)
    assert states.heating_mode(readings) == "off"
    assert states.heating_activity(readings) == "off"
    assert states.zone_program(readings) == "time_program"


def test_plant_off_and_zone_off():
    assert states.heating_mode(data(plant=5, zone=2)) == "off"
    assert states.heating_mode(data(plant=1, zone=0)) == "off"


def test_unknown_state_is_not_misrepresented_as_off():
    assert states.heating_mode({"PlantMode": {"value": 1}}) is None
    assert states.heating_activity({"PlantMode": {"value": 1}}) is None
    assert states.heating_mode(data(plant=77)) is None
    assert states.heating_mode(data(plant="bad")) is None
    assert states.enum_code({"value": True}) is None


def test_dhw_operating_modes():
    assert states.hot_water_operation(data(dhw=0)) == "off"
    assert states.hot_water_operation(data(dhw=1)) == "scheduled"
    assert states.hot_water_operation(data(dhw=2)) == "always_active"
    assert states.hot_water_operation(data(dhw=99)) is None


def test_expanded_read_items_have_correct_zones():
    request = model.make_main_request({"zones": [{"num": 1}]})
    assert {"id": "ZoneComfortTemp", "zn": 1} in request["items"]
    assert {"id": "ZoneEconomyTemp", "zn": 1} in request["items"]
    assert {"id": "DhwMode", "zn": 0} in request["items"]
    assert {"id": "DhwTimeProgComfortTemp", "zn": 0} in request["items"]
    assert {"id": "DhwTimeProgEconomyTemp", "zn": 0} in request["items"]


def test_response_retains_new_fields():
    read = model.parse_main_data({"items": [
        {"id": "ZoneComfortTemp", "zone": 1, "value": 20.5},
        {"id": "ZoneEconomyTemp", "zone": 1, "value": 17.5},
        {"id": "DhwTimeProgComfortTemp", "zone": 0, "value": 50.0},
        {"id": "DhwMode", "zone": 0, "value": 1},
    ]})
    assert model.as_temperature(read["ZoneComfortTemp"]) == 20.5
    assert model.as_temperature(read["ZoneEconomyTemp"]) == 17.5
    assert states.hot_water_operation(read) == "scheduled"


def test_holiday_mode_is_not_automatically_treated_as_off():
    assert states.heating_mode(data(plant=6, zone=3)) is None


def test_integral_float_mode_codes_are_allowed():
    assert states.enum_code({"value": 2.0}) == 2
    assert states.enum_code({"value": 2.5}) is None
