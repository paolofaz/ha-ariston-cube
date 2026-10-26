"""Poll scheduling checks for the verified Smc web reports and ACS Comfort."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def test_web_comfort_checks_phone_changes_within_five_minutes():
    comfort = (ROOT / "comfort_coordinator.py").read_text()
    assert "timedelta(minutes=5)" in comfort
    assert "timedelta(minutes=30)" not in comfort
    # User commands still perform a separate immediate readback.
    portal = (ROOT / "web_portal.py").read_text()
    assert 'self._request("POST", f"/R2/PlantMenu/Submit/{gateway}"' in portal
    assert 'confirmed = self.comfort_record(await self._request("GET", path))' in portal


def test_smc_local_bihourly_refresh_is_unloaded_with_config_entry():
    sensor = (ROOT / "sensor.py").read_text()
    assert "async_track_time_change(" in sensor
    assert "hour=tuple(range(2, 24, 2))" in sensor
    assert "minute=(10, 40)" in sensor
    assert "second=0" in sensor
    assert "entry.async_on_unload(unsubscribe)" in sensor
    assert "smc.async_refresh()" in sensor
    assert "gas.async_refresh()" not in sensor
    assert "AristonRecentGas" not in sensor
    assert "AristonPhysicalGas" in sensor


def test_smc_interval_is_fallback_not_main_schedule():
    coordinator = (ROOT / "smc_coordinator.py").read_text()
    assert "timedelta(hours=6)" in coordinator
    assert "async_read_metering(" in coordinator


def test_no_kwh_gas_sensors_in_translations():
    import json
    for lang in ["strings.json", "translations/it.json"]:
        data = json.loads((ROOT / lang).read_text())
        for key in ("heating_gas_today", "dhw_gas_today",
                    "heating_gas_2h", "dhw_gas_2h"):
            assert key not in data["entity"]["sensor"]
        for key in ("heating_smc_today", "dhw_smc_today",
                    "heating_smc_2h", "dhw_smc_2h"):
            assert key in data["entity"]["sensor"]
