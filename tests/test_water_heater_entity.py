"""Run the 2026.10 DHW water_heater against a lightweight fake HA contract."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def load(monkeypatch):
    package_name = "_ariston_cube_water_heater_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]

    class BaseEntity:
        def __init__(self, coordinator, key):
            self.coordinator = coordinator
            self._key = key

        @property
        def available(self):
            return True

        async def async_added_to_hass(self):
            return None

    class WaterHeaterEntity:
        pass

    class WaterHeaterEntityFeature:
        TARGET_TEMPERATURE = 1
        OPERATION_MODE = 2
        ON_OFF = 4

    class Error(Exception):
        pass

    registry = types.SimpleNamespace(
        existing={}, removed=[],
        async_get_entity_id=lambda domain, platform, unique_id: None,
        async_get=lambda entity_id: None,
        async_remove=lambda entity_id: None,
    )

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    water_heater = types.ModuleType("homeassistant.components.water_heater")
    water_heater.WaterHeaterEntity = WaterHeaterEntity
    water_heater.WaterHeaterEntityFeature = WaterHeaterEntityFeature
    const = types.ModuleType("homeassistant.const")
    const.ATTR_TEMPERATURE = "temperature"
    const.UnitOfTemperature = types.SimpleNamespace(CELSIUS="°C")
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = Error
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    registry_module = types.ModuleType("homeassistant.helpers.entity_registry")
    registry_module.async_get = lambda hass: registry
    entity = types.ModuleType(package_name + ".entity")
    entity.AristonEntity = BaseEntity

    for name, module in {
        "homeassistant": ha,
        "homeassistant.components": components,
        "homeassistant.components.water_heater": water_heater,
        "homeassistant.const": const,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": registry_module,
        package_name: package,
        package_name + ".entity": entity,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = package_name + ".water_heater"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "water_heater.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, Error, registry


def test_only_temperature_feature_and_read_only_current_mode(monkeypatch):
    module, _, _ = load(monkeypatch)
    coordinator = types.SimpleNamespace(data={
        "DhwTemp": {"value": 49, "min": 39, "max": 57, "step": 1},
        "DhwStorageTemperature": {"value": 44.5},
        "DhwMode": {"value": 2},
    })
    entity = module.AristonDhwWaterHeater(coordinator)
    assert entity._attr_supported_features == 1
    assert entity.target_temperature == 49
    assert entity.current_temperature == 44.5
    assert entity.current_operation == "always_active"
    assert (entity.min_temp, entity.max_temp) == (39, 57)
    assert entity.available
    assert not hasattr(entity, "async_set_operation_mode")
    assert not hasattr(entity, "operation_list")


def test_missing_storage_probe_stays_none_not_target_temperature(monkeypatch):
    module, _, _ = load(monkeypatch)
    coord = types.SimpleNamespace(data={"DhwTemp": {"value": 51}})
    ent = module.AristonDhwWaterHeater(coord)
    assert ent.target_temperature == 51
    assert ent.current_temperature is None
    assert ent.available
    coord.data = {}
    assert not ent.available


def test_valid_command_and_guarded_invalid_commands(monkeypatch):
    module, Error, _ = load(monkeypatch)

    class Coordinator:
        data = {"DhwTemp": {"value": 49, "min": 36, "max": 60, "step": 1}}
        writes = []

        async def async_set_setpoint(self, field, value):
            self.writes.append((field, value))

    instance = Coordinator()
    ent = module.AristonDhwWaterHeater(instance)
    asyncio.run(ent.async_set_temperature(temperature=50))
    assert instance.writes == [("DhwTemp", 50.0)]
    for bad in (35, 61, 50.5, True, "not a temperature", float("nan")):
        with pytest.raises(Error):
            asyncio.run(ent.async_set_temperature(temperature=bad))
    assert instance.writes == [("DhwTemp", 50.0)]


def test_only_own_obsolete_number_registry_entry_is_removed(monkeypatch):
    module, _, registry = load(monkeypatch)
    calls = []
    owned = types.SimpleNamespace(config_entry_id="own-entry")
    foreign = types.SimpleNamespace(config_entry_id="other-entry")
    old_unique = "plant_number_DhwTemp"

    def find(domain, platform, unique):
        calls.append((domain, platform, unique))
        return "number.old_acs" if unique == old_unique else None

    registry.async_get_entity_id = find
    registry.async_get = lambda entity_id: owned
    registry.async_remove = registry.removed.append
    entry = types.SimpleNamespace(
        entry_id="own-entry",
        runtime_data=types.SimpleNamespace(plant_id="plant", data={}),
    )
    added = []
    asyncio.run(module.async_setup_entry(None, entry, lambda x: added.extend(x)))
    assert calls == [("number", "ariston_cube", old_unique)]
    assert registry.removed == ["number.old_acs"]
    assert len(added) == 1

    registry.removed.clear()
    registry.async_get = lambda entity_id: foreign
    asyncio.run(module.async_setup_entry(None, entry, lambda x: None))
    assert registry.removed == []
