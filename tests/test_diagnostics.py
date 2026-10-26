"""Tests for no-leak schema-only Home Assistant diagnostics."""

import asyncio
import importlib
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_diag_test"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg

api = importlib.import_module(PKG + ".api")
diag = importlib.import_module(PKG + ".diagnostics")


def test_shapes_never_copy_values_or_arbitrary_dictionary_keys():
    secret = "PRIVATE_TOKEN__SERIAL_456"
    original = {
        "username": "owner@example.invalid",
        "password": secret,
        "gwId": secret,
        secret: {"data": secret},
        "LastMonth": [
            {"gas": 4.2, "elect": 2.5, "date": "2026-10-26",
             "otherID": "SECRET_ID"},
        ],
    }
    result = diag.safe_shape(original)
    serialized = repr(result)
    assert secret not in serialized
    assert "owner@" not in serialized
    assert "2026" not in serialized
    assert "4.2" not in serialized
    assert "2.5" not in serialized
    assert "otherID" not in serialized
    assert "password" not in serialized
    assert result["fields"]["LastMonth"]["first_shape"]["fields"]["gas"] == {
        "kind": "number"
    }


def test_schema_is_bounded_by_depth_and_list_first_only():
    original = {"data": [{"data": [{"data": [{"data": [{"data": ["TOP"]}]}]}]}]}
    result = diag.safe_shape(original)
    assert len(repr(result)) < 600


def test_on_demand_diagnostics_does_not_dump_raw_responses():
    class Client:
        calls = 0
        async def async_probe_dhw_comfort_menu(self, plant_id):
            return api.AristonAuthError("Login to web menu unavailable")
        async def async_diagnostic_reports(self, plant_id):
            self.calls += 1
            return {
                "weekly_program": {"week": [{"startTime": "08:00"}]},
                "energy_account": {"LastMonth": [{"gas": 64.8}]},
                "consumption_sequences": api.AristonConnectionError("Error at gateway"),
            }
    client = Client()
    coordinator = types.SimpleNamespace(client=client, plant_id="SECRET_GWID")
    entry = types.SimpleNamespace(runtime_data=coordinator)
    result = asyncio.run(diag.async_get_config_entry_diagnostics(None, entry))
    assert client.calls == 1
    assert result["reports"]["consumption_sequences"] == {
        "error_type": "AristonConnectionError"
    }
    assert "08:00" not in repr(result)
    assert "64.8" not in repr(result)
    assert "SECRET_GWID" not in repr(result)


def test_diagnostic_api_does_not_send_control_commands():
    from pathlib import Path
    source = (ROOT / "api.py").read_text(encoding="utf-8")
    method = source.split("async def async_diagnostic_reports", 1)[1].split(
        "async def async_set_plant_control", 1
    )[0]
    assert 'self._request("GET", path)' in method
    assert '"POST", path, json_body={}' in method
    assert "/set?" not in method
    assert "PlantMenu/Submit" not in method


def test_hidden_weekly_and_consumption_fields_are_anonymous_not_erased():
    weekly = {"PRIVATE_DYNAMIC_ID": [{"xSecretName": {"periods": [1, 2, 3]}}]}
    sequence = {"serialNumber": "PRIVATE", "internalCode": 42, "reading": 3.5}
    a = diag.safe_shape(weekly)
    b = diag.safe_shape(sequence)
    assert a["omitted_keys"] == 1
    assert a["unnamed_field_shapes"][0]["kind"] == "list"
    assert a["unnamed_field_shapes"][0]["count"] == 1
    assert b["omitted_keys"] == 3
    assert {entry["kind"] for entry in b["unnamed_field_shapes"]} == {
        "string", "integer", "number"
    }
    assert "PRIVATE" not in repr((a, b))
    assert "serialNumber" not in repr((a, b))
    assert "internalCode" not in repr((a, b))
    assert "reading" not in repr((a, b))


def test_unmapped_shapes_have_four_field_upper_bound():
    obj = {"sensitive_field_" + str(i): "secret" for i in range(99)}
    result = diag.safe_shape(obj)
    assert result["omitted_keys"] == 99
    assert len(result["unnamed_field_shapes"]) == 4
    assert "sensitive_field" not in repr(result)
    assert "secret" not in repr(result)



def test_schedule_field_shapes_without_program_values():
    sample = {
        "ChZn1": {
            "plans": [{
                "days": [0, 1],
                "slices": [{"from": 480, "temp": 0}, {"from": 1040, "temp": 1}],
            }]
        }
    }
    result = diag.safe_shape(sample)
    shown = repr(result)
    for field in ("'ChZn1'", "'plans'", "'slices'", "'days'", "'temp'"):
        assert field in shown
    assert "1040" not in shown
    assert "480" not in shown


def test_known_consumption_codes_show_provisional_names_not_measurements():
    rows = [
        {"p": 3, "k": 7, "v": [1234.5, 987.0]},
        {"p": 1, "k": 10, "v": [0.0]},
        {"p": 999999, "k": 888888, "v": [1000000.0, 7.5]},
    ]
    result = diag.safe_consumption_inventory(rows)
    assert result["series_count"] == 3
    assert result["series"][0] == {
        "period_candidate": "last_month_candidate",
        "usage_candidate": "heating_gas_candidate",
        "sample_count": 2,
        "all_samples_numeric": True,
    }
    assert result["series"][1]["usage_candidate"] == "dhw_gas_candidate"
    assert result["series"][2]["usage_candidate"] == "unknown"
    for value in ("1234.5", "987.0", "1000000.0", "999999", "888888"):
        assert value not in repr(result)


def test_consumption_metadata_is_fail_closed():
    assert diag.safe_consumption_inventory({}) == {"kind": "not_a_list"}
    row = diag.safe_consumption_inventory([{"p": True, "k": "20", "v": [None]}])
    assert row["series"][0]["period_candidate"] == "unknown"
    assert row["series"][0]["usage_candidate"] == "unknown"
    assert not row["series"][0]["all_samples_numeric"]



def test_consumption_units_are_allowlisted_and_never_expose_costs():
    assert diag.safe_consumption_units({"gasEnergyUnit": 0, "gasCost": 9999.9}) == {
        "gas_unit_candidate": "kWh"
    }
    assert diag.safe_consumption_units({"gasEnergyUnit": 4}) == {
        "gas_unit_candidate": "Smc"
    }
    assert diag.safe_consumption_units({"gasEnergyUnit": 999999}) == {
        "gas_unit_candidate": "unknown"
    }
    assert diag.safe_consumption_units({"gasEnergyUnit": True}) == {
        "gas_unit_candidate": "unknown"
    }
    assert diag.safe_consumption_units(None) == {
        "gas_unit_candidate": "unavailable"
    }


def test_diagnostics_include_only_safe_unit_name_when_present():
    class Client:
        async def async_probe_dhw_comfort_menu(self, plant_id):
            return [{"id": "U6_9_2", "value": 2}]
        async def async_diagnostic_reports(self, plant_id):
            return {
                "weekly_program": {"ChZn1": {"plans": []}},
                "energy_account": {"LastMonth": []},
                "consumption_sequences": [],
                "consumption_settings": {
                    "gasEnergyUnit": 5,
                    "gasCost": 999.12,
                    "elecCost": 456.0,
                },
            }
    entry = types.SimpleNamespace(runtime_data=types.SimpleNamespace(
        client=Client(), plant_id="SECRET_GW"
    ))
    result = asyncio.run(diag.async_get_config_entry_diagnostics(None, entry))
    assert result["consumption_units"] == {"gas_unit_candidate": "m³"}
    assert "999.12" not in repr(result)
    assert "456.0" not in repr(result)
    assert "SECRET_GW" not in repr(result)



def test_comfort_probe_sanitizes_web_values_and_auth_failure():
    assert diag.safe_dhw_comfort_menu([{
        "id": "U6_9_2", "value": 0, "email": "secret@example.invalid",
    }]) == {"status": "letto", "modalita": "spenta"}
    assert diag.safe_dhw_comfort_menu([{
        "id": "U6_9_2", "value": "2", "token": "secret",
    }]) == {"status": "letto", "modalita": "sempre_attiva"}
    assert diag.safe_dhw_comfort_menu([{
        "id": "U6_9_2", "value": 1
    }]) == {"status": "letto", "modalita": "temporizzata"}
    assert diag.safe_dhw_comfort_menu(api.AristonAuthError("secret_token")) == {
        "status": "non_disponibile", "error_type": "AristonAuthError",
    }
    assert "secret" not in repr(diag.safe_dhw_comfort_menu({
        "account": "secret", "items": [{"id": "U6_9_2", "value": 2}]
    }))


def test_comfort_probe_uses_separate_web_portal_and_never_submits():
    api_source = (ROOT / "api.py").read_text()
    probe = api_source.split("async def async_probe_dhw_comfort_menu", 1)[1].split(
        "async def async_read_weekly_program", 1
    )[0]
    assert "web_portal.async_read_comfort(plant_id)" in probe
    assert "async_set_comfort" not in probe
    web_source = (ROOT / "web_portal.py").read_text()
    assert "/R2/PlantMenu/Refresh?" in web_source
    assert "/R2/PlantMenu/Submit/" in web_source
    assert 'self._request("GET", path)' in web_source



def test_web_portal_http_status_is_safely_reported():
    from _ariston_cube_diag_test.web_portal import WebPortalAuthError
    error = WebPortalAuthError("Web login form HTTP 403")
    assert diag.safe_dhw_comfort_menu(error) == {
        "status": "non_disponibile",
        "error_type": "WebPortalAuthError",
        "http_status": 403,
    }
    assert diag.safe_dhw_comfort_menu(WebPortalAuthError("secret_payload")) == {
        "status": "non_disponibile", "error_type": "WebPortalAuthError"
    }
