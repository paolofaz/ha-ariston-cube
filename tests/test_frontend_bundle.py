"""Ensure card bundle survives ordinary integration-directory installs."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def test_web_card_is_bundled_with_integration():
    card = (ROOT / "www" / "ariston-cube-weekly-card.js").read_text()
    assert 'customElements.define("ariston-cube-weekly-card"' in card
    assert "hass.callService" not in card
    assert "fetch(" not in card


def test_automatic_resource_registration_is_scoped_to_storage_mode():
    code = (ROOT / "frontend.py").read_text()
    assert "async_register_static_paths" in code
    assert 'resources.async_create_item' in code
    assert 'lovelace.resource_mode != MODE_STORAGE' in code
    assert '_FLAG = "ariston_cube_frontend_registered"' in code
    assert "async_get_info" in code
    entry = (ROOT / "__init__.py").read_text()
    assert "await async_register_weekly_card(hass)" in entry


def test_lovelace_dependency_declared_and_versioned():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert "frontend" in manifest["dependencies"]
    assert "http" in manifest["dependencies"]
    assert "lovelace" in manifest["after_dependencies"]
    assert manifest["version"] == "1.0.0"



def test_optional_acs_card_has_slider_and_separate_comfort_service():
    card = (ROOT / "www" / "ariston-cube-acs-card.js").read_text()
    assert 'customElements.define("ariston-cube-acs-card"' in card
    assert 'range.type = "range"' in card
    assert 'callService("water_heater", "set_temperature"' in card
    assert '"switch", current ? "turn_off" : "turn_on"' in card
    assert "fetch(" not in card
    frontend = (ROOT / "frontend.py").read_text()
    assert "_ACS_CARD_PATH" in frontend
    assert "_ACS_CARD_RESOURCE" in frontend
