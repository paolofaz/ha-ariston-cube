"""Regression tests for the HA entry setup contract and 2026.10 entity API.

This lightweight harness fakes only the Home Assistant services required by
__init__.py, so it runs in CI without installing a full Home Assistant runtime.
"""

from __future__ import annotations

import asyncio
import ast
from pathlib import Path
import runpy
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def _setup_module(monkeypatch):
    class Platforms:
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        CLIMATE = "climate"
        WATER_HEATER = "water_heater"
        NUMBER = "number"
        SELECT = "select"
        SWITCH = "switch"
        CALENDAR = "calendar"

    hass_module = types.ModuleType("homeassistant")
    hass_module.__path__ = []
    const_module = types.ModuleType("homeassistant.const")
    const_module.Platform = Platforms
    helpers_module = types.ModuleType("homeassistant.helpers")
    helpers_module.__path__ = []
    clients_module = types.ModuleType("homeassistant.helpers.aiohttp_client")
    clients_module.async_get_clientsession = lambda hass: "shared-test-session"
    clients_module.async_create_clientsession = (
        lambda hass, **kwargs: "private-web-test-session"
    )

    package = types.ModuleType("_ariston_cube_setup_test")
    package.__path__ = [str(ROOT)]
    api_module = types.ModuleType("_ariston_cube_setup_test.api")
    coordinator_module = types.ModuleType("_ariston_cube_setup_test.coordinator")
    frontend_module = types.ModuleType("_ariston_cube_setup_test.frontend")

    async def register_mock_frontend(hass):
        hass.data["ariston_cube_frontend_registered"] = True

    frontend_module.async_register_weekly_card = register_mock_frontend

    class Client:
        def __init__(self, session, username, password, *, web_session=None):
            assert session == "shared-test-session"
            assert web_session == "private-web-test-session"
            assert username == "test-user"
            assert password == "test-password"

    class Coordinator:
        def __init__(self, hass, entry, client):
            self.first_refresh_called = False

        async def async_config_entry_first_refresh(self):
            self.first_refresh_called = True

    api_module.AristonClient = Client
    coordinator_module.AristonCoordinator = Coordinator

    for name, fake in {
        "homeassistant": hass_module,
        "homeassistant.const": const_module,
        "homeassistant.helpers": helpers_module,
        "homeassistant.helpers.aiohttp_client": clients_module,
        "_ariston_cube_setup_test": package,
        "_ariston_cube_setup_test.api": api_module,
        "_ariston_cube_setup_test.coordinator": coordinator_module,
        "_ariston_cube_setup_test.frontend": frontend_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, fake)

    import importlib.util

    location = ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "_ariston_cube_setup_test", location, submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_async_setup_entry_reports_success_and_forwards_eight_platforms(monkeypatch):
    integration = _setup_module(monkeypatch)
    platforms = []

    class ConfigEntries:
        async def async_forward_entry_setups(self, entry, requested):
            platforms.extend(requested)

    entry = types.SimpleNamespace(data={"username": "test-user", "password": "test-password"})
    hass = types.SimpleNamespace(config_entries=ConfigEntries(), data={})


    assert asyncio.run(integration.async_setup_entry(hass, entry)) is True
    assert hass.data["ariston_cube_frontend_registered"] is True
    assert entry.runtime_data.first_refresh_called
    assert set(platforms) == {"sensor", "binary_sensor", "climate", "water_heater", "number", "select", "switch", "calendar"}


def test_setup_does_not_return_none(monkeypatch):
    integration = _setup_module(monkeypatch)
    assert integration.async_setup_entry.__annotations__["return"] == "bool"


@pytest.mark.parametrize("filename", ["climate.py"])
def test_climate_uses_2026_10_temperature_interface(filename):
    """2026.11 native_ properties are not supported by HA Core 2026.10."""
    source = (ROOT / filename).read_text(encoding="utf-8")
    module = ast.parse(source)
    entities = [
        node for node in module.body
        if isinstance(node, ast.ClassDef) and node.name.startswith("Ariston")
    ]
    assert len(entities) == 1
    cls = entities[0]
    methods = {
        node.name for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "current_temperature" in methods
    assert "target_temperature" in methods
    assert "native_current_temperature" not in methods
    assert "native_target_temperature" not in methods
    assert "_attr_temperature_unit = UnitOfTemperature.CELSIUS" in source
    assert "_attr_native_temperature_unit" not in source
    assert "_attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE" in source
    assert '"ZoneComfortTemp"' in source


@pytest.mark.parametrize(
    ("filename", "domain"),
    [("climate.py", "climate"), ("number.py", "number")],
)
def test_platforms_emit_setup_and_entity_registration_diagnostics(filename, domain):
    source = (ROOT / filename).read_text(encoding="utf-8")
    assert f"Ariston Cube {domain} platform setup invoked" in source
    assert f"Ariston Cube {domain} entity added to Home Assistant" in source
    assert "async def async_added_to_hass(self)" in source
    assert "await super().async_added_to_hass()" in source



def test_release_marker_and_diagnostics_format_are_consistent():
    import json
    manifest = json.loads((ROOT / "manifest.json").read_text())
    source = (ROOT / "__init__.py").read_text()
    diag = (ROOT / "diagnostics.py").read_text()
    assert manifest["version"] == "1.0.0"
    assert "Ariston Cube 1.0.0 starting" in source
    assert '"version": "1.0.0"' in diag
