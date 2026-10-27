"""Regression checks for the Cube S AUTO/Manuale select entity.

Uses the real select implementation with only the HA base classes mocked.
No cloud or running Home Assistant instance required.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def load(monkeypatch):
    package_name = "_ariston_cube_select_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]

    class BaseEntity:
        def __init__(self, coordinator, key):
            self.coordinator = coordinator
            self._key = key

        @property
        def available(self):
            return True

    class SelectEntity:
        pass

    class Error(Exception):
        pass

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    select_component = types.ModuleType("homeassistant.components.select")
    select_component.SelectEntity = SelectEntity
    errors = types.ModuleType("homeassistant.exceptions")
    errors.HomeAssistantError = Error
    entity_module = types.ModuleType(package_name + ".entity")
    entity_module.AristonEntity = BaseEntity

    for name, module in {
        "homeassistant": ha,
        "homeassistant.components": components,
        "homeassistant.components.select": select_component,
        "homeassistant.exceptions": errors,
        package_name: package,
        package_name + ".entity": entity_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = package_name + ".select"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "select.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, Error


class Coordinator:
    def __init__(self, plant=1, zone=3, options=None):
        self.data = {
            "PlantMode": {"value": plant, "options": [0, 1, 5]},
            "ZoneMode": {
                "value": zone,
                "options": [0, 1, 2, 3] if options is None else options,
            },
        }
        self.commands = []

    async def async_set_zone_mode(self, value):
        self.commands.append(("zone", value))
        self.data["ZoneMode"]["value"] = value

    async def async_set_plant_control(self, name, value):
        self.commands.append((name, value))


def test_both_selects_are_registered_and_use_different_unique_keys(monkeypatch):
    module, _ = load(monkeypatch)
    coordinator = Coordinator()
    entry = types.SimpleNamespace(runtime_data=coordinator)
    entities = []
    asyncio.run(module.async_setup_entry(None, entry, lambda values: entities.extend(values)))
    assert len(entities) == 2
    assert isinstance(entities[0], module.AristonPlantModeSelect)
    assert isinstance(entities[1], module.AristonZoneProgrammeSelect)
    assert entities[0]._key == "plant_mode"
    assert entities[1]._key == "zone_program_mode"


def test_auto_manual_roundtrip_uses_existing_guarded_coordinator(monkeypatch):
    module, _ = load(monkeypatch)
    coordinator = Coordinator()
    select = module.AristonZoneProgrammeSelect(coordinator)
    assert select._attr_options == ["AUTO", "Manuale"]
    assert select.current_option == "AUTO"
    assert select.available
    asyncio.run(select.async_select_option("Manuale"))
    assert coordinator.commands == [("zone", 2)]
    assert select.current_option == "Manuale"
    asyncio.run(select.async_select_option("AUTO"))
    assert coordinator.commands == [("zone", 2), ("zone", 3)]
    assert select.current_option == "AUTO"


@pytest.mark.parametrize("plant,zone,options", [
    (0, 3, [2, 3]),  # summer
    (5, 3, [2, 3]),  # boiler off
    (6, 3, [2, 3]),  # unknown holiday state
    (1, 0, [0, 2, 3]),  # zone off stays off
    (1, 1, [1, 2, 3]),  # economy is not manual
    (1, 3, [0, 2]),  # AUTO not declared by cloud
    (1, 2, [0, 3]),  # manual not declared by cloud
    (1, 3, []),
])
def test_unsafe_or_unsupported_context_never_writes(monkeypatch, plant, zone, options):
    module, Error = load(monkeypatch)
    coordinator = Coordinator(plant, zone, options)
    select = module.AristonZoneProgrammeSelect(coordinator)
    assert not select.available
    with pytest.raises(Error):
        asyncio.run(select.async_select_option("Manuale"))
    assert coordinator.commands == []


def test_missing_data_and_invalid_option_never_write(monkeypatch):
    module, Error = load(monkeypatch)
    coordinator = Coordinator()
    select = module.AristonZoneProgrammeSelect(coordinator)
    with pytest.raises(Error):
        asyncio.run(select.async_select_option("OFF"))
    assert not coordinator.commands
    coordinator.data = {}
    assert not select.available
    assert select.current_option is None
    with pytest.raises(Error):
        asyncio.run(select.async_select_option("AUTO"))
    assert not coordinator.commands


def test_plant_selector_is_still_independent(monkeypatch):
    module, _ = load(monkeypatch)
    coordinator = Coordinator()
    plant = module.AristonPlantModeSelect(coordinator)
    assert plant.current_option == "Modalità inverno"
    asyncio.run(plant.async_select_option("Modalità estate"))
    assert coordinator.commands == [("PlantMode", 0)]


def test_flame_is_plant_wide_and_heat_request_is_zone_specific():
    model = (ROOT / "model.py").read_text(encoding="utf-8")
    binary = (ROOT / "binary_sensor.py").read_text(encoding="utf-8")
    assert '"IsFlameOn"' in model.split("PLANT_IDS", 1)[1].split("ZONE_IDS", 1)[0]
    assert '"ZoneHeatRequest"' in model.split("ZONE_IDS", 1)[1].split("def parse_plants", 1)[0]
    assert 'key="IsFlameOn"' in binary
    assert 'key="ZoneHeatRequest"' in binary
