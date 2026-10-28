"""Guarded automatic Energy-hour timer regression tests — no HA/Recorder writes.

Tests execute the clock callback and fake the existing field-tested aligner.
The actual Recorder-statistics import remains fully isolated in its original
manual-v1.1.1-rc.1 code and is not duplicated by automatic scheduling.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import importlib
import sys
import types
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    package = types.ModuleType(PKG)
    package.__path__ = [str(ROOT)]
    sys.modules[PKG] = package

auto = importlib.import_module(PKG + ".energy_automation")
alignment = importlib.import_module(PKG + ".energy_alignment")
ROME = ZoneInfo("Europe/Rome")


def local(hour: int, minute: int = 15, second: int = 0) -> datetime:
    return datetime(2026, 10, 28, hour, minute, second, tzinfo=ROME)


class FakeAligner:
    """Contract-compatible fake of the existing one-shot manual aligner."""

    def __init__(
        self, *, statuses=None, fail_preview=None, fail_apply=None,
        wait_to_preview=False,
    ):
        self.statuses = statuses or {"heating": "can_shift", "dhw": "can_shift"}
        self.fail_preview = fail_preview
        self.fail_apply = fail_apply
        self.wait_to_preview = wait_to_preview
        self.calls = []
        self.slot_target = None

    async def preview(self):
        self.calls.append("preview")
        if self.wait_to_preview:
            await asyncio.sleep(0)
        if self.fail_preview is not None:
            raise self.fail_preview
        return {
            "status": "preview_only_no_statistics_write",
            "target_start": self.slot_target,
            "local_bucket": "2026-10-28 12:00–14:00",
            "fingerprint": "a" * 64,
            "operations": [
                {"kind": key, "status": value}
                for key, value in self.statuses.items()
            ],
        }

    async def apply(self, fingerprint):
        assert fingerprint == "a" * 64
        self.calls.append("apply")
        if self.fail_apply is not None:
            raise self.fail_apply
        shifted = [
            "sensor.heating" if kind == "heating" else "sensor.dhw"
            for kind, status in self.statuses.items()
            if status == "can_shift"
        ]
        return {
            "status": "verified_hourly_import" if shifted else "no_change_needed",
            "target_start": self.slot_target,
            "shifted_entities": shifted,
            "untouched_entities": [
                "sensor.heating" if kind == "heating" else "sensor.dhw"
                for kind, status in self.statuses.items()
                if status != "can_shift"
            ],
        }


def setup_runner(aligner):
    main = SimpleNamespace(
        smc_coordinator=object(), energy_hour_aligner=aligner
    )
    return auto.AutomaticEnergyHourRunner(SimpleNamespace(), main)


@pytest.mark.parametrize("hour,target", [
    (1, "2026-10-27T22:00:00+00:00"),
    (9, "2026-10-28T06:00:00+00:00"),
    (11, "2026-10-28T08:00:00+00:00"),
    (13, "2026-10-28T10:00:00+00:00"),
    (15, "2026-10-28T12:00:00+00:00"),
    (17, "2026-10-28T14:00:00+00:00"),
    (19, "2026-10-28T16:00:00+00:00"),
    (21, "2026-10-28T18:00:00+00:00"),
    (23, "2026-10-28T20:00:00+00:00"),
])
def test_exact_quarter_past_odd_local_hours_selects_ending_second_hour(
        hour, target):
    assert auto.scheduled_target(local(hour)) == target


@pytest.mark.parametrize("hour,minute", [
    (8, 15), (10, 15), (12, 15), (14, 15), (16, 15),
    (15, 0), (15, 14), (15, 16), (15, 40), (17, 10),
    (17, 40),
])
def test_never_start_automatically_at_wrong_time(hour, minute):
    assert auto.scheduled_target(local(hour, minute)) is None


def test_1515_rome_shifts_only_the_correct_12_to_14_bucket():
    aligner = FakeAligner()
    aligner.slot_target = "2026-10-28T12:00:00+00:00"
    runner = setup_runner(aligner)
    asyncio.run(runner.async_tick(local(15)))
    assert aligner.calls == ["preview", "apply"]
    report = runner.status()
    assert report["status"] == "read_only_auto_energy_hour_status"
    assert report["enabled"] is True
    assert report["schedule"] == "odd_local_hours_at_minute_15"
    assert report["automatic_retries"] is False
    assert report["last_attempt"]["target_start"] == aligner.slot_target
    assert report["last_attempt"]["result"] == "verified_hourly_import"
    assert report["last_attempt"]["shifted_entities"] == [
        "sensor.heating", "sensor.dhw"
    ]


def test_three_automatic_buckets_are_separate_and_not_repeated():
    aligner = FakeAligner()
    runner = setup_runner(aligner)

    async def scenario():
        for hour in (15, 17, 19):
            aligner.slot_target = auto.scheduled_target(local(hour))
            await runner.async_tick(local(hour))
            await runner.async_tick(local(hour))  # duplicate callback ignored

    asyncio.run(scenario())
    assert aligner.calls == ["preview", "apply"] * 3
    records = runner.status()["recent_attempts"]
    assert [r["target_start"] for r in records] == [
        "2026-10-28T12:00:00+00:00",
        "2026-10-28T14:00:00+00:00",
        "2026-10-28T16:00:00+00:00",
    ]
    assert all(r["result"] == "verified_hourly_import" for r in records)


def test_no_gas_and_already_aligned_have_zero_automatic_imports():
    for statuses in (
        {"heating": "zero_consumption", "dhw": "zero_consumption"},
        {"heating": "already_aligned", "dhw": "already_aligned"},
        {"heating": "zero_consumption", "dhw": "already_aligned"},
    ):
        aligner = FakeAligner(statuses=statuses)
        aligner.slot_target = auto.scheduled_target(local(17))
        runner = setup_runner(aligner)
        asyncio.run(runner.async_tick(local(17)))
        assert aligner.calls == ["preview"]
        assert runner.status()["last_attempt"]["result"] == "no_change_needed"


def test_partial_consumption_imports_only_eligible_sensor():
    aligner = FakeAligner(statuses={
        "heating": "can_shift", "dhw": "zero_consumption"
    })
    aligner.slot_target = auto.scheduled_target(local(17))
    runner = setup_runner(aligner)
    asyncio.run(runner.async_tick(local(17)))
    record = runner.status()["last_attempt"]
    assert record["shifted_entities"] == ["sensor.heating"]
    assert record["untouched_entities"] == ["sensor.dhw"]


def test_preview_refusal_is_logged_but_never_applied_or_retried():
    aligner = FakeAligner(
        fail_preview=alignment.AlignmentRejected("Missing compiled Recorder rows")
    )
    runner = setup_runner(aligner)

    async def scenario():
        await runner.async_tick(local(17))
        await runner.async_tick(local(17))

    asyncio.run(scenario())
    assert aligner.calls == ["preview"]
    record = runner.status()["last_attempt"]
    assert record["result"] == "skipped_safety_check"
    assert "Recorder" in record["reason"]


def test_ambiguous_apply_never_retries_even_with_duplicate_timer():
    aligner = FakeAligner(
        fail_apply=alignment.AlignmentRejected(
            "Import sent but readback unconfirmed. Do not retry"
        )
    )
    aligner.slot_target = auto.scheduled_target(local(17))
    runner = setup_runner(aligner)

    async def scenario():
        await runner.async_tick(local(17))
        await runner.async_tick(local(17))
        await runner.async_tick(local(17, 40))

    asyncio.run(scenario())
    assert aligner.calls == ["preview", "apply"]
    assert runner.status()["last_attempt"]["result"] == "unconfirmed_do_not_retry"


def test_concurrent_duplicate_events_cannot_send_two_imports():
    aligner = FakeAligner(wait_to_preview=True)
    aligner.slot_target = auto.scheduled_target(local(19))
    runner = setup_runner(aligner)

    async def scenario():
        await asyncio.gather(
            runner.async_tick(local(19)), runner.async_tick(local(19))
        )

    asyncio.run(scenario())
    assert aligner.calls == ["preview", "apply"]


def test_stale_target_or_missing_coordinator_never_applies():
    aligner = FakeAligner()
    aligner.slot_target = auto.scheduled_target(local(15))
    runner = setup_runner(aligner)
    asyncio.run(runner.async_tick(local(17)))
    assert aligner.calls == ["preview"]
    assert runner.status()["last_attempt"]["result"] == "skipped_safety_check"

    other = setup_runner(aligner)
    other.coordinator.smc_coordinator = None
    asyncio.run(other.async_tick(local(17)))
    assert runner.status()["last_attempt"]["result"] == "skipped_safety_check"


def test_stopped_runner_has_no_clock_side_effects():
    aligner = FakeAligner()
    aligner.slot_target = auto.scheduled_target(local(17))
    runner = setup_runner(aligner)
    runner.stop()
    asyncio.run(runner.async_tick(local(17)))
    assert aligner.calls == []
    assert runner.status()["enabled"] is False


def test_status_is_read_only_copy_not_live_history_pointer():
    aligner = FakeAligner()
    aligner.slot_target = auto.scheduled_target(local(15))
    runner = setup_runner(aligner)
    asyncio.run(runner.async_tick(local(15)))
    results = runner.status()
    results["recent_attempts"].clear()
    assert len(runner.status()["recent_attempts"]) == 1


def test_unexpected_error_is_fail_closed_without_cloud_values():
    aligner = FakeAligner(fail_apply=RuntimeError("SECRET TOKEN NOT FOR LOGGING"))
    aligner.slot_target = auto.scheduled_target(local(17))
    runner = setup_runner(aligner)
    asyncio.run(runner.async_tick(local(17)))
    status = runner.status()["last_attempt"]
    assert status["result"] == "unconfirmed_do_not_retry"
    assert status["reason"] == "RuntimeError"
    assert "SECRET" not in str(status)


def test_dst_fall_back_rejects_unsafe_window_without_any_import():
    aligner = FakeAligner()
    aligner.slot_target = "incorrect"
    runner = setup_runner(aligner)
    # 03:15 is the first post-fallback odd-hour tick in Europe/Rome.
    local_dst = datetime(2026, 10, 25, 3, 15, tzinfo=ROME)
    asyncio.run(runner.async_tick(local_dst))
    assert aligner.calls == []
    assert runner.status()["last_attempt"]["result"] == "skipped_safety_check"


def test_no_external_gas_ledger_mutation_or_automatic_retry_loop():
    code = (ROOT / "energy_automation.py").read_text()
    assert "async_import_statistics" not in code
    assert "sqlite3" not in code
    assert "_store.async_save" not in code
    assert "asyncio.sleep" not in code
    assert "while True" not in code
    assert "async_track_time_interval" not in code
