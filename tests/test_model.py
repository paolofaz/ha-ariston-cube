"""Fast, pure response-parser tests without importing Home Assistant."""

import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "custom_components/ariston_cube/model.py")
)
parse_plants = MODULE["parse_plants"]
make_main_request = MODULE["make_main_request"]
parse_main_data = MODULE["parse_main_data"]
as_temperature = MODULE["as_temperature"]
as_boolean = MODULE["as_boolean"]


def test_plant_discovery():
    assert parse_plants([{"gwId": "ABC123", "name": "Home"}]) == [
        {"id": "ABC123", "name": "Home"}
    ]
    assert parse_plants([]) == []
    with pytest.raises(ValueError):
        parse_plants({"gwId": "ABC123"})
    with pytest.raises(ValueError):
        parse_plants([{"name": "missing plant id"}])


def test_read_request_zone_one_only():
    request = make_main_request({"zones": [{"num": 1}]})
    assert request["useCache"] is False
    assert request["features"]["zones"] == [{"num": 1}]
    assert {"id": "ZoneMeasuredTemp", "zn": 1} in request["items"]
    assert {"id": "DhwTemp", "zn": 0} in request["items"]
    assert all(item["zn"] in (0, 1) for item in request["items"])


def test_read_main_filters_other_zones_and_preserves_limits():
    payload = {"items": [
        {"id": "ZoneMeasuredTemp", "zone": 1, "value": 19.5, "unit": "C"},
        {"id": "ZoneMeasuredTemp", "zone": 2, "value": 30},
        {"id": "ZoneDesiredTemp", "zone": 1, "value": 20, "min": 10, "max": 30},
        {"id": "DhwTemp", "zone": 0, "value": 48},
        {"id": "ZoneHeatRequest", "zone": 1, "value": 1},
        {"id": "private", "zone": 0, "value": "ignored"},
    ]}
    values = parse_main_data(payload)
    assert as_temperature(values["ZoneMeasuredTemp"]) == 19.5
    assert values["ZoneDesiredTemp"]["min"] == 10
    assert as_boolean(values["ZoneHeatRequest"]) is True
    assert "private" not in values
    assert len(values) == 4


def test_unknown_and_malformed_values_are_not_faked_as_zero():
    assert as_temperature(None) is None
    assert as_temperature({"value": "not a number"}) is None
    assert as_temperature({"value": True}) is None
    assert as_boolean(None) is None
    assert as_boolean({"value": "unknown"}) is None
    assert as_boolean({"value": 0}) is False
    with pytest.raises(ValueError):
        parse_main_data({"items": None})


def test_label_mapping():
    values = parse_main_data({"items": [
        {"id": "ZoneMode", "zone": 1, "value": 1,
         "options": [0, 1], "optTexts": ["Manual", "Time program"]},
    ]})
    assert values["ZoneMode"]["label"] == "Time program"



def test_optional_boiler_read_request_identifiers():
    request = make_main_request({"zones": [{"num": 1}]})
    for code in ("ChFlowTemp", "ChFlowSetpointTemp", "OutsideTemp",
                 "HeatingCircuitPressure"):
        assert {"id": code, "zn": 0} in request["items"]
    parsed = parse_main_data({"items": [
        {"id": "ChFlowTemp", "zone": 0, "value": 49.0},
        {"id": "ChFlowSetpointTemp", "zone": 0, "value": 51.0},
        {"id": "OutsideTemp", "zone": 0, "value": 13.0},
        {"id": "HeatingCircuitPressure", "zone": 0, "value": 1.3, "unit": "bar"},
    ]})
    assert len(parsed) == 4
    assert parsed["HeatingCircuitPressure"]["unit"] == "bar"
