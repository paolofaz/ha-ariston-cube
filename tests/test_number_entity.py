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


def test_acs_number_is_not_registered_anymore(monkeypatch):
    module, _ = load_module(monkeypatch)
    assert not any(item[0] == "DhwTemp" for item in module._NUMBERS)


def test_number_respects_tighter_limits_from_device(monkeypatch):
    mod, _ = load_module(monkeypatch)
    values = {"ZoneEconomyTemp": {"value": 20, "min": 15, "max": 25}}
    entity = mod.AristonCubeNumber(
        types.SimpleNamespace(data=values), "ZoneEconomyTemp", "heating_economy", 10, 30, 0.5
    )
    assert (entity.native_min_value, entity.native_max_value) == (15, 25)


def test_number_service_calls_coordinator_only_when_valid(monkeypatch):
    mod, Error = load_module(monkeypatch)

    class Coordinator:
        data = {"ZoneComfortTemp": {"value": 21, "min": 10, "max": 30}}
        writes = []

        async def async_set_setpoint(self, field, value):
            self.writes.append((field, value))

    coordinator = Coordinator()
    entity = mod.AristonCubeNumber(coordinator, "ZoneComfortTemp", "heating_comfort", 10, 30, 0.5)
    asyncio.run(entity.async_set_native_value(22))
    assert coordinator.writes == [("ZoneComfortTemp", 22)]
    try:
        asyncio.run(entity.async_set_native_value(35))
    except Error:
        pass
    else:
        assert False, "Expected bounded temperature to fail"
    assert coordinator.writes == [("ZoneComfortTemp", 22)]


def test_economy_number_unavailable_when_cloud_has_no_value(monkeypatch):
    mod, _ = load_module(monkeypatch)
    entity = mod.AristonCubeNumber(
        types.SimpleNamespace(data={}), "ZoneEconomyTemp", "heating_economy", 10, 30, 0.5
    )
    assert not entity.available


def test_both_comfort_and_economy_are_hard_capped_10_to_30(monkeypatch):
    module, Error = load_module(monkeypatch)
    for key in ("ZoneComfortTemp", "ZoneEconomyTemp"):
        coordinator = types.SimpleNamespace(
            data={key: {"value": 21, "min": 5, "max": 35, "step": 0.5}}
        )
        ent = module.AristonCubeNumber(
            coordinator, key, "heating_comfort", 10, 30, 0.5
        )
        assert ent.native_min_value == 10.0
        assert ent.native_max_value == 30.0
        assert ent.native_step == 0.5
        assert ent.native_value == 21.0


def test_number_definitions_include_comfort_and_economy(monkeypatch):
    module, _ = load_module(monkeypatch)
    assert ("ZoneEconomyTemp", "heating_economy", 10.0, 30.0, 0.5) in module._NUMBERS
    assert ("ZoneComfortTemp", "heating_comfort", 10.0, 30.0, 0.5) in module._NUMBERS
