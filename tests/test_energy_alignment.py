"""Behavioral checks for opt-in hourly Energy attribution.

Pure tests: no real Recorder, SQLite, .storage, or gas metadata is written.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import importlib
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    package = types.ModuleType(PKG)
    package.__path__ = [str(ROOT)]
    sys.modules[PKG] = package

alignment = importlib.import_module(PKG + ".energy_alignment")
ROME = ZoneInfo("Europe/Rome")


def pair(bucket=0.4, target_sum=100.0, next_sum=100.4,
         target_state=500.0, next_state=500.4):
    return alignment.plan_pair(
        entity_id="sensor.ariston_cube_gas_heating",
        kind="heating", bucket=bucket,
        target={"sum": target_sum, "state": target_state},
        following={"sum": next_sum, "state": next_state},
    )


def test_0810_shift_is_07_to_08_after_0915():
    end = alignment.slot_from_now(datetime(2026, 10, 28, 9, 20, tzinfo=ROME))
    assert end.hour == 8
    assert end.minute == 0
    assert end.astimezone(timezone.utc).hour == 7
    result = pair()
    assert result["status"] == "can_shift"
    assert result["proposed_target_sum"] == 100.4
    assert result["current_following_sum"] == 100.4


def test_already_shifted_is_idempotent():
    result = pair(target_sum=100.4)
    assert result["status"] == "already_aligned"


def test_zero_consumption_is_a_no_op():
    result = pair(bucket=0, target_sum=100.0, next_sum=100.0,
                  target_state=500.0, next_state=500.0)
    assert result["status"] == "zero_consumption"


@pytest.mark.parametrize("bucket,target_sum,next_sum,target_state,next_state", [
    (0.4, 100.0, 100.7, 500.0, 500.4),  # unrelated cloud correction
    (0.4, 100.0, 100.4, 500.0, 500.5),  # state includes another increase
    (0.4, 100.5, 100.4, 500.0, 500.4),  # negative hourly increment
    (0.4, 100.0, 100.0, 500.0, 500.0),  # old source not yet committed
    (0.4, 100.0, 100.4, 500.5, 500.4),  # nonmonotonic meter
    (float("nan"), 100, 100.4, 500, 500.4),
    (30.0, 100, 130.0, 500, 530),
])
def test_mixed_buckets_and_anomalies_are_rejected(
        bucket, target_sum, next_sum, target_state, next_state):
    with pytest.raises(alignment.AlignmentRejected):
        pair(bucket, target_sum, next_sum, target_state, next_state)


@pytest.mark.parametrize("h, minute, expected_h, prev_day", [
    (9, 20, 8, False),
    (10, 30, 8, False),
    (9, 10, 6, False),
    (1, 20, 0, False),
    (0, 30, 22, True),
    (23, 20, 22, False),
])
def test_latest_closed_slot(h, minute, expected_h, prev_day):
    now = datetime(2026, 10, 28, h, minute, tzinfo=ROME)
    end = alignment.slot_from_now(now)
    assert end.hour == expected_h
    assert (end.date() < now.date()) is prev_day


def test_during_fall_dst_ambiguous_slot_is_not_modified():
    # Europe/Rome moves from CEST to CET at 03:00 on Oct 25.
    at = datetime(2026, 10, 25, 3, 20, tzinfo=ROME)
    with pytest.raises(alignment.AlignmentRejected):
        alignment.slot_from_now(at)


def test_fingerprint_changes_with_any_sum_or_entity():
    base = {
        "target_start": "2026-10-28T06:00:00+00:00",
        "following_start": "2026-10-28T07:00:00+00:00",
        "operations": [pair()],
    }
    first = alignment.fingerprint_plan(base)
    assert len(first) == 64
    modified = {**base, "operations": [{**pair(), "current_following_sum": 101}]}
    assert first != alignment.fingerprint_plan(modified)


def test_gas_alignment_remains_internal_and_does_not_touch_gas_ledger():
    code = (ROOT / "__init__.py").read_text()
    module = (ROOT / "energy_alignment.py").read_text()
    runner = (ROOT / "energy_automation.py").read_text()
    # No manual statistics-changing service is shown in the 1.3 Actions UI.
    assert '"apply_energy_hour_alignment"' not in code
    assert '"preview_energy_hour_alignment"' not in code
    assert '"inspect_energy_hour_alignment"' in code
    assert "async_import_statistics" in module
    assert "async_block_till_done" in module
    assert "async_import_statistics" not in runner
    assert "import sqlite3" not in module
    assert "_store.async_save" not in module
    assert "async_track_time_change" in code
    assert "AutomaticEnergyHourRunner" in code
    assert "async_track_time_change" not in module


def test_delayed_recorder_readback_is_accepted_without_second_write(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    aligner = alignment.EnergyHourAligner(None, None)
    read_count = 0
    waits = 0

    async def delayed_statistics(stat_id, start):
        nonlocal read_count
        read_count += 1
        return {}, {"sum": 100.0 if read_count <= 2 else 100.4}, {"sum": 100.4}

    async def no_time_sleep(duration):
        assert duration == 1

    class FakeRecorder:
        async def async_block_till_done(self):
            nonlocal waits
            waits += 1

    monkeypatch.setattr(aligner, "_statistics", delayed_statistics)
    monkeypatch.setattr(alignment.asyncio, "sleep", no_time_sleep)

    operation = {
        "entity_id": "sensor.ariston_cube_gas_heating",
        "proposed_target_sum": 100.4,
        "current_following_sum": 100.4,
    }
    asyncio.run(aligner._wait_for_readback(
        FakeRecorder(), operation, datetime(2026, 10, 28, 6, tzinfo=timezone.utc)
    ))
    assert read_count == 3
    assert waits == 3


def test_recorder_readback_timeout_is_ambiguous_not_an_automatic_retry(monkeypatch):
    import asyncio

    aligner = alignment.EnergyHourAligner(None, None)
    read_count = 0

    async def never_confirmed(stat_id, start):
        nonlocal read_count
        read_count += 1
        return {}, {"sum": 100.0}, {"sum": 100.4}

    async def no_time_sleep(duration):
        assert duration == 1

    class FakeRecorder:
        async def async_block_till_done(self):
            pass

    monkeypatch.setattr(aligner, "_statistics", never_confirmed)
    monkeypatch.setattr(alignment.asyncio, "sleep", no_time_sleep)
    with pytest.raises(alignment.AlignmentRejected, match="Do not retry"):
        asyncio.run(aligner._wait_for_readback(
            FakeRecorder(),
            {
                "entity_id": "sensor.ariston_cube_gas_heating",
                "proposed_target_sum": 100.4,
                "current_following_sum": 100.4,
            },
            datetime(2026, 10, 28, 6, tzinfo=timezone.utc),
        ))
    assert read_count == 12


def test_recorder_readback_requires_following_sum_unchanged(monkeypatch):
    import asyncio

    aligner = alignment.EnergyHourAligner(None, None)
    async def conflicting_statistic(stat_id, start):
        return {}, {"sum": 100.4}, {"sum": 100.6}

    async def no_time_sleep(duration):
        pass

    class FakeRecorder:
        async def async_block_till_done(self):
            pass

    monkeypatch.setattr(aligner, "_statistics", conflicting_statistic)
    monkeypatch.setattr(alignment.asyncio, "sleep", no_time_sleep)
    with pytest.raises(alignment.AlignmentRejected, match="unconfirmed"):
        asyncio.run(aligner._wait_for_readback(
            FakeRecorder(),
            {
                "entity_id": "sensor.ariston_cube_gas_heating",
                "proposed_target_sum": 100.4,
                "current_following_sum": 100.4,
            },
            datetime(2026, 10, 28, 6, tzinfo=timezone.utc),
        ))


def test_read_only_inspect_hour_reads_both_existing_sensors(monkeypatch):
    import asyncio
    from types import ModuleType, SimpleNamespace

    # Minimal fake Home Assistant imports; no database or writes.
    ha = ModuleType("homeassistant")
    ha.__path__ = []
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    registry_mod = ModuleType("homeassistant.helpers.entity_registry")
    registry_mod.async_get = lambda hass: SimpleNamespace(
        async_get_entity_id=lambda domain, platform, unique_id: (
            "sensor.ariston_c874_gas_riscaldamento_cumulativo_smc"
            if unique_id.endswith("total_heating_smc")
            else "sensor.ariston_c874_gas_acs_cumulativo_smc"
        )
    )
    util = ModuleType("homeassistant.util")
    util.__path__ = []
    dt_mod = ModuleType("homeassistant.util.dt")
    dt_mod.utcnow = lambda: datetime(2026, 10, 28, 10, 30, tzinfo=timezone.utc)
    for mod, obj in {
        "homeassistant": ha,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": registry_mod,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_mod,
    }.items():
        monkeypatch.setitem(sys.modules, mod, obj)
    aligner = alignment.EnergyHourAligner(
        SimpleNamespace(), SimpleNamespace(plant_id="c874")
    )

    async def dummy_read(stat_id, start, hours):
        assert start == datetime(2026, 10, 28, 5, tzinfo=timezone.utc)
        assert hours == 3
        if "riscaldamento" in stat_id:
            sums = (844.124985714, 844.524985714, 844.524985714)
        else:
            sums = (263.361004762, 263.561004762, 263.561004762)
        return {}, [{"sum": amount} for amount in sums]

    monkeypatch.setattr(aligner, "_statistics_window", dummy_read)
    result = asyncio.run(aligner.inspect_hour("2026-10-28T06:00:00+00:00"))
    assert result["status"] == "read_only_no_statistics_write"
    heating, dhw = result["operations"]
    assert heating["consumption_in_target_hour"] == 0.4
    assert heating["consumption_in_following_hour"] == 0.0
    assert dhw["consumption_in_target_hour"] == 0.2
    assert dhw["consumption_in_following_hour"] == 0.0


@pytest.mark.parametrize("date", [
    "2026-10-28T06:01:00+00:00",
    "2026-10-28T06:00:00",
    "not-a-date",
])
def test_read_only_inspect_rejects_invalid_target(date, monkeypatch):
    import asyncio
    from types import ModuleType, SimpleNamespace

    ha = ModuleType("homeassistant")
    ha.__path__ = []
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    registry_mod = ModuleType("homeassistant.helpers.entity_registry")
    util = ModuleType("homeassistant.util")
    util.__path__ = []
    dt_mod = ModuleType("homeassistant.util.dt")
    dt_mod.utcnow = lambda: datetime(2026, 10, 28, 10, 30, tzinfo=timezone.utc)
    for mod, obj in {
        "homeassistant": ha,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": registry_mod,
        "homeassistant.util": util,
        "homeassistant.util.dt": dt_mod,
    }.items():
        monkeypatch.setitem(sys.modules, mod, obj)

    aligner = alignment.EnergyHourAligner(
        SimpleNamespace(), SimpleNamespace(plant_id="c874")
    )
    with pytest.raises(alignment.AlignmentRejected):
        asyncio.run(aligner.inspect_hour(date))



def test_1515_rome_corrects_12_to_14_bucket_into_13_to_14():
    """Exact day-of-field-test hour, with Italy now on CET (UTC+1)."""
    from datetime import timedelta
    too_early = alignment.slot_from_now(
        datetime(2026, 10, 28, 15, 14, tzinfo=ROME)
    )
    assert too_early.hour == 12
    end = alignment.slot_from_now(
        datetime(2026, 10, 28, 15, 15, tzinfo=ROME)
    )
    assert end.hour == 14
    assert (end - timedelta(hours=2)).hour == 12
    target = end.astimezone(timezone.utc) - timedelta(hours=1)
    following = target + timedelta(hours=1)
    assert target.isoformat() == "2026-10-28T12:00:00+00:00"
    assert following.isoformat() == "2026-10-28T13:00:00+00:00"


def test_combined_rc_preserves_original_gas_sensor_unique_ids_and_ledger():
    sensor = (ROOT / "sensor.py").read_text()
    smc = (ROOT / "smc_coordinator.py").read_text()
    assert 'super().__init__(coordinator, "gas_meter_v1_" + source_key)' in sensor
    assert 'AristonCumulativeGas(smc, "total_heating_smc", "heating_gas_cumulative")' in sensor
    assert 'AristonCumulativeGas(smc, "total_dhw_smc", "dhw_gas_cumulative")' in sensor
    assert "coordinator.smc_coordinator = smc" in sensor
    assert "ariston_cube_gas_meter_v1_" in smc or "ariston_cube_gas_meter_v1_" in (
        ROOT / "gas_ledger.py"
    ).read_text()
    init = (ROOT / "__init__.py").read_text()
    assert '"preview_weekly_clone"' in init
    assert '"clone_weekly_days"' in init
    assert '"preview_energy_hour_alignment"' not in init
    assert '"inspect_energy_hour_alignment"' in init
    assert '"apply_energy_hour_alignment"' not in init
    assert "async_track_time_change" in init
    assert '"inspect_automatic_energy_hour_alignment"' in init
