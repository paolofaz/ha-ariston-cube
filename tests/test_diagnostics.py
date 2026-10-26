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
