"""Unit-test bounded setpoint command construction without cloud calls."""

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

commands = importlib.import_module(PACKAGE + ".commands")


def snapshot(**overrides):
    value = {
        "PlantMode": {"value": 1},
        "ZoneMode": {"value": 2},
        "ZoneDesiredTemp": {"value": 20, "min": 10, "max": 30, "step": 0.5},
        "ZoneComfortTemp": {"value": 21, "min": 10, "max": 30, "step": 0.5},
        "DhwTemp": {"value": 49, "min": 36, "max": 60, "step": 1},
    }
    value.update(overrides)
    return value


FEATURES = {"zones": [{"num": 1}]}


def test_valid_dry_run_manual_setpoint_has_zone_and_previous_value():
    body = commands.build_setpoint_request(snapshot(), FEATURES, "ZoneDesiredTemp", 20.5)
    assert body == {
        "items": [{"id": "ZoneDesiredTemp", "zone": 1, "prevValue": 20.0, "value": 20.5}],
        "features": FEATURES,
    }


def test_hot_water_dry_run_is_zone_zero():
    body = commands.build_setpoint_request(snapshot(), FEATURES, "DhwTemp", 50)
    assert body["items"][0] == {
        "id": "DhwTemp", "zone": 0, "prevValue": 49.0, "value": 50.0
    }


def test_same_value_does_not_create_post_body():
    assert commands.build_setpoint_request(snapshot(), FEATURES, "DhwTemp", 49) is None


@pytest.mark.parametrize("value", [-100, 31, float("nan"), float("inf"), True, "bad", 20.25])
def test_invalid_temperature_fails_closed(value):
    with pytest.raises(commands.CommandRejected):
        commands.build_setpoint_request(snapshot(), FEATURES, "ZoneDesiredTemp", value)


def test_missing_limits_do_not_fall_back_to_guessed_values():
    state = snapshot(ZoneDesiredTemp={"value": 20})
    with pytest.raises(commands.CommandRejected, match="limits"):
        commands.build_setpoint_request(state, FEATURES, "ZoneDesiredTemp", 21)


def test_no_writes_in_time_program_or_summer_mode():
    for state in (snapshot(ZoneMode={"value": 3}),
                  snapshot(PlantMode={"value": 0})):
        with pytest.raises(commands.CommandRejected):
            commands.build_setpoint_request(state, FEATURES, "ZoneDesiredTemp", 21)


def test_reject_non_whitelisted_properties():
    with pytest.raises(commands.CommandRejected):
        commands.build_setpoint_request(snapshot(), FEATURES, "PlantMode", 1)


def test_feature_snapshot_required():
    with pytest.raises(commands.CommandRejected):
        commands.build_setpoint_request(snapshot(), {}, "DhwTemp", 50)



def test_comfort_setpoint_write_requires_manual_zone_and_heat_plant():
    body = commands.build_setpoint_request(snapshot(), FEATURES, "ZoneComfortTemp", 21.5)
    assert body["items"][0] == {
        "id": "ZoneComfortTemp", "zone": 1, "prevValue": 21.0, "value": 21.5
    }
    for state in (snapshot(ZoneMode={"value": 3}), snapshot(PlantMode={"value": 0})):
        with pytest.raises(commands.CommandRejected, match="mode"):
            commands.build_setpoint_request(state, FEATURES, "ZoneComfortTemp", 21.5, require_manual=True)



def test_zone_mode_request_safe_for_manual_to_auto():
    readings = snapshot(ZoneMode={"value": 2, "options": [0, 2, 3]})
    body = commands.build_zone_mode_request(readings, FEATURES, 3)
    assert body["items"] == [{"id": "ZoneMode", "zone": 1,
                              "prevValue": 2, "value": 3}]
    assert commands.build_zone_mode_request(readings, FEATURES, 2) is None


def test_zone_mode_rejects_options_missing_or_summer_plant():
    for readings in [
        snapshot(ZoneMode={"value": 2}),
        snapshot(PlantMode={"value": 0}, ZoneMode={"value": 2, "options": [0, 2, 3]}),
        snapshot(ZoneMode={"value": 2, "options": [0, 2]}),
    ]:
        with pytest.raises(commands.CommandRejected):
            commands.build_zone_mode_request(readings, FEATURES, 3)


def test_comfort_preset_remains_editable_in_auto_but_active_target_does_not():
    state = snapshot(ZoneMode={"value": 3})
    body = commands.build_setpoint_request(state, FEATURES, "ZoneComfortTemp", 21.5)
    assert body["items"][0]["value"] == 21.5
    with pytest.raises(commands.CommandRejected, match="mode"):
        commands.build_setpoint_request(state, FEATURES, "ZoneDesiredTemp", 20.5)


@pytest.mark.parametrize("field,value", [
    ("ZoneComfortTemp", 9.5),
    ("ZoneComfortTemp", 30.5),
    ("ZoneEconomyTemp", 9.5),
    ("ZoneEconomyTemp", 30.5),
    ("ZoneComfortTemp", 20.25),
    ("ZoneEconomyTemp", 20.25),
    ("DhwTemp", 49.5),
])
def test_server_side_temperature_caps_and_step(field, value):
    state = snapshot(ZoneComfortTemp={"value": 21, "min": 8, "max": 32, "step": 0.5},
                     ZoneEconomyTemp={"value": 18, "min": 8, "max": 32, "step": 0.5},
                     DhwTemp={"value": 49, "min": 35, "max": 65, "step": 1})
    with pytest.raises(commands.CommandRejected):
        commands.build_setpoint_request(state, FEATURES, field, value)
