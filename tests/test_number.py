"""Static and pure-logic tests for water heater and heating numbers."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def test_water_heater_platform_replaces_acs_number_without_touching_old_sensors():
    init = (ROOT / "__init__.py").read_text()
    assert "Platform.NUMBER" in init
    assert "Platform.WATER_HEATER" in init
    assert "Platform.SENSOR" in init
    assert "Platform.CLIMATE" in init
    sensor = (ROOT / "sensor.py").read_text()
    assert "DhwTemp" in sensor
    assert "ZoneDesiredTemp" in sensor


def test_only_heating_numbers_still_use_box_and_device_limits():
    number = (ROOT / "number.py").read_text()
    tree = ast.parse(number)
    assert "NumberMode.BOX" in number
    assert '("DhwTemp", "acs_temperature", 36.0, 60.0, 1.0)' not in number
    assert '"ZoneEconomyTemp"' in number
    assert '("ZoneComfortTemp", "heating_comfort", 10.0, 30.0, 0.5)' in number
    assert "await self.coordinator.async_set_setpoint(self._field, value)" in number
    assert "async_def" not in number
    assert tree is not None


def test_acs_write_limits_are_36_to_60():
    commands = (ROOT / "commands.py").read_text()
    assert '"DhwTemp": (0, 36.0, 60.0)' in commands
