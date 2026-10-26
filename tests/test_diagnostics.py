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


def test_diagnostic_api_uses_read_requests_only():
    from pathlib import Path
    source = (ROOT / "api.py").read_text(encoding="utf-8")
    method = source.split("async def async_diagnostic_reports", 1)[1]
    assert 'self._request("GET", path)' in method
    assert '_request("POST"' not in method


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
