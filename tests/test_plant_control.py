"""Fail-closed tests for whole-plant mode and thermoregulation controls."""

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

commands = importlib.import_module(PKG + ".commands")
model = importlib.import_module(PKG + ".model")

FEATURES = {"zones": [{"num": 1}]}


def snapshot(plant=1, options=None, auto=0.0):
    return {
        "PlantMode": {"value": plant, "options": [0, 1, 2, 5] if options is None else options},
        "AutomaticThermoregulation": {"value": auto},
        "ZoneMode": {"value": 3},
    }


def test_plant_mode_uses_id_zone_zero_and_previous_code():
    req = commands.build_plant_control_request(snapshot(), FEATURES, "PlantMode", 0)
    assert req == {
        "items": [{"id": "PlantMode", "zone": 0, "prevValue": 1, "value": 0}],
        "features": FEATURES,
    }
    assert commands.build_plant_control_request(snapshot(), FEATURES, "PlantMode", 1) is None


def test_plant_mode_rejects_undeclared_modes():
    with pytest.raises(commands.CommandRejected):
        commands.build_plant_control_request(snapshot(options=[]), FEATURES, "PlantMode", 5)
    with pytest.raises(commands.CommandRejected):
        commands.build_plant_control_request(snapshot(options=[0, 1]), FEATURES, "PlantMode", 5)


@pytest.mark.parametrize("value", [-1, 2, 3, 4, 6, 999, 1.0, True, "1"])
def test_plant_mode_only_allows_three_explicit_codes(value):
    with pytest.raises(commands.CommandRejected):
        commands.build_plant_control_request(snapshot(), FEATURES, "PlantMode", value)


def test_automatic_thermoregulation_bool_has_own_property():
    req = commands.build_plant_control_request(
        snapshot(auto=0.0), FEATURES, "AutomaticThermoregulation", 1
    )
    assert req["items"] == [{
        "id": "AutomaticThermoregulation", "zone": 0,
        "prevValue": 0, "value": 1,
    }]
    assert commands.build_plant_control_request(
        snapshot(auto=1), FEATURES, "AutomaticThermoregulation", 1
    ) is None


def test_never_conflate_thermoregulation_with_zone_auto_or_acs_comfort():
    snap = snapshot()
    snap["ZoneMode"]["value"] = 2
    req = commands.build_plant_control_request(
        snap, FEATURES, "AutomaticThermoregulation", 1
    )
    assert "ZoneMode" not in repr(req)
    for item in ("DhwMode", "DhwComfortFunction", "U6_9_2", "ZoneMode"):
        with pytest.raises(commands.CommandRejected):
            commands.build_plant_control_request(snap, FEATURES, item, 1)


def test_new_plant_item_is_requested_and_parseable():
    request = model.make_main_request(FEATURES)
    assert {"id": "AutomaticThermoregulation", "zn": 0} in request["items"]
    result = model.parse_main_data({"items": [
        {"id": "AutomaticThermoregulation", "zone": 0, "value": 1.0},
        {"id": "PlantMode", "zone": 0, "value": 1, "options": [0, 1, 5]},
    ]})
    assert result["AutomaticThermoregulation"]["value"] == 1.0
    assert result["PlantMode"]["options"] == [0, 1, 5]
