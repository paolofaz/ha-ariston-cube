"""Exercise number entity values and service calls with fake Home Assistant APIs."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def load_module(monkeypatch):
    package_name = "_ariston_cube_number_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]

    class BaseEntity:
        def __init__(self, coordinator, key):
            self.coordinator = coordinator
            self._key = key

        @property
        def available(self):
            return True

    class NumberEntity:
        pass

    class Error(Exception):
        pass

    number = types.ModuleType("homeassistant.components.number")
    number.NumberEntity = NumberEntity
    number.NumberDeviceClass = types.SimpleNamespace(TEMPERATURE="temperature")
    number.NumberMode = types.SimpleNamespace(BOX="box")
    core = types.ModuleType("homeassistant")
    core.__path__ = []
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    const = types.ModuleType("homeassistant.const")
    const.UnitOfTemperature = types.SimpleNamespace(CELSIUS="°C")
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = Error
    entity = types.ModuleType(package_name + ".entity")
    entity.AristonEntity = BaseEntity

    for name, mod in {
        "homeassistant": core,
        "homeassistant.components": components,
        "homeassistant.components.number": number,
        "homeassistant.const": const,
        "homeassistant.exceptions": exceptions,
        package_name: package,
        package_name + ".entity": entity,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    module_name = package_name + ".number"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "number.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, Error


def test_acs_number_reads_value_and_uses_one_degree_steps(monkeypatch):
    mod, _ = load_module(monkeypatch)
    values = {"DhwTemp": {"value": 49, "min": 35, "max": 64, "step": 1}}
    coordinator = types.SimpleNamespace(data=values)
    entity = mod.AristonCubeNumber(coordinator, "DhwTemp", "acs_temperature", 36, 60, 1)
    assert entity.native_value == 49.0
    assert entity.native_min_value == 36
    assert entity.native_max_value == 60
    assert entity.native_step == 1


def test_number_respects_tighter_limits_from_device(monkeypatch):
    mod, _ = load_module(monkeypatch)
    values = {"DhwTemp": {"value": 50, "min": 40, "max": 55}}
    entity = mod.AristonCubeNumber(
        types.SimpleNamespace(data=values), "DhwTemp", "acs_temperature", 36, 60, 1
    )
    assert (entity.native_min_value, entity.native_max_value) == (40, 55)


def test_number_service_calls_coordinator_only_when_valid(monkeypatch):
    mod, Error = load_module(monkeypatch)

    class Coordinator:
        data = {"DhwTemp": {"value": 49, "min": 36, "max": 60}}
        writes = []

        async def async_set_setpoint(self, field, value):
            self.writes.append((field, value))

    coordinator = Coordinator()
    entity = mod.AristonCubeNumber(coordinator, "DhwTemp", "acs_temperature", 36, 60, 1)
    asyncio.run(entity.async_set_native_value(50))
    assert coordinator.writes == [("DhwTemp", 50)]
    try:
        asyncio.run(entity.async_set_native_value(65))
    except Error:
        pass
    else:
        assert False, "Expected bounded temperature to fail"
    assert coordinator.writes == [("DhwTemp", 50)]


def test_economy_number_unavailable_when_cloud_has_no_value(monkeypatch):
    mod, _ = load_module(monkeypatch)
    entity = mod.AristonCubeNumber(
        types.SimpleNamespace(data={}), "ZoneEconomyTemp", "heating_economy", 10, 30, 0.5
    )
    assert not entity.available
