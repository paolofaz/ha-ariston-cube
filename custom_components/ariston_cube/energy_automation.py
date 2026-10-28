"""Guarded every-two-hour Energy attribution using the field-tested aligner.

The timer invokes a *single* preview + fingerprint-checked apply at :15 of
odd LOCAL hours (01:15, 03:15 ... 23:15). No catch-up, backfill, polling or
retry is performed by this module. In particular, an unconfirmed Recorder
import is NEVER automatically sent a second time. The previously verified
manual services remain available for human inspection.

All writes and cloud validation remain inside energy_alignment.py; no gas
sensor, ledger, entity ID or short-term Recorder row is modified here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from .energy_alignment import AlignmentRejected, EnergyHourAligner, slot_from_now

_LOGGER = logging.getLogger(__name__)
UTC = timezone.utc
MAX_HISTORY = 8


def scheduled_target(now: datetime) -> str | None:
    """Return the exact eligible target UTC hour, or None off the :15 slot.

    HA's async_track_time_change passes timezone-aware LOCAL datetime.
    We intentionally do not run at even hours or try to catch up after a
    missed event or reload. Reject nonexistent/ambiguous DST slots through
    the existing slot_from_now safety checks.
    """
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return None
    if now.hour % 2 != 1 or now.minute != 15:
        return None
    end = slot_from_now(now)
    return (end.astimezone(UTC) - timedelta(hours=1)).isoformat()


class AutomaticEnergyHourRunner:
    """At most ONE correction attempt per 2-hour slot per running instance."""

    def __init__(self, hass: Any, coordinator: Any):
        self.hass = hass
        self.coordinator = coordinator
        self._attempted: set[str] = set()
        self._history: list[dict[str, Any]] = []
        self._stopped = False

    def stop(self) -> None:
        """Do not accept further ticks after the config entry has unloaded."""
        self._stopped = True

    def status(self) -> dict[str, Any]:
        """Read-only last-run diagnostics; no private cloud/ledger values."""
        return {
            "status": "read_only_auto_energy_hour_status",
            "enabled": not self._stopped,
            "schedule": "odd_local_hours_at_minute_15",
            "automatic_retries": False,
            "last_attempt": dict(self._history[-1]) if self._history else None,
            "recent_attempts": [dict(item) for item in self._history],
        }

    async def async_tick(self, now: datetime) -> None:
        """Called only by HA's local-time clock. Never throw into HA loop."""
        if self._stopped:
            return
        try:
            target_start = scheduled_target(now)
        except AlignmentRejected as exc:
            self._record({
                "at": now.isoformat(), "target_start": None,
                "result": "skipped_safety_check", "reason": str(exc),
                "shifted_entities": [],
            })
            return
        if target_start is None or target_start in self._attempted:
            return

        # Mark BEFORE await so concurrent duplicated callbacks never retry
        # a partially sent write, even while the Recorder readback is pending.
        self._attempted.add(target_start)
        report: dict[str, Any] = {
            "at": now.isoformat(), "target_start": target_start,
            "result": "skipped", "shifted_entities": [],
        }
        stage = "preview"
        try:
            if getattr(self.coordinator, "smc_coordinator", None) is None:
                raise AlignmentRejected("Gas coordinator not ready")
            aligner = getattr(self.coordinator, "energy_hour_aligner", None)
            if aligner is None:
                aligner = EnergyHourAligner(self.hass, self.coordinator)
                self.coordinator.energy_hour_aligner = aligner
            # A fresh cloud/Recorder comparison with the existing fail-closed
            # constraints. Not a second, weaker algorithm for auto mode.
            preview = await aligner.preview()
            if preview.get("target_start") != target_start:
                raise AlignmentRejected(
                    "Preview slot did not match the scheduled local-time slot"
                )
            report["local_bucket"] = preview.get("local_bucket")
            operations = preview.get("operations", [])
            statuses = {
                op.get("kind"): op.get("status") for op in operations
            }
            if set(statuses) != {"heating", "dhw"}:
                raise AlignmentRejected("Both existing gas sensors are required")
            if any(
                status not in ("can_shift", "zero_consumption", "already_aligned")
                for status in statuses.values()
            ):
                raise AlignmentRejected("Unknown gas alignment status")
            report["sensor_statuses"] = statuses
            if not any(status == "can_shift" for status in statuses.values()):
                report["result"] = "no_change_needed"
                _LOGGER.info(
                    "Ariston Cube automatic Energy hour: %s no correction needed",
                    target_start,
                )
                return
            stage = "apply"
            # apply() re-plans against fresh Recorder/ledger values, verifies
            # the fingerprint and performs exactly one import per eligible
            # sensor, polling read-only results without retry.
            result = await aligner.apply(preview["fingerprint"])
            if result.get("target_start") != target_start:
                raise AlignmentRejected("Applied slot differs from scheduled slot")
            if result.get("status") not in (
                "verified_hourly_import", "no_change_needed"
            ):
                raise AlignmentRejected("Automatic correction was not verified")
            report["result"] = (
                "verified_hourly_import" if result["shifted_entities"]
                else "no_change_needed"
            )
            report["shifted_entities"] = list(result["shifted_entities"])
            report["untouched_entities"] = list(result["untouched_entities"])
            _LOGGER.info(
                "Ariston Cube automatic Energy hour: %s %s; %d gas sensors shifted",
                target_start, report["result"], len(report["shifted_entities"]),
            )
        except AlignmentRejected as exc:
            # If apply() was entered an import might have been queued even
            # when readback times out; never retry this scheduled hour.
            report["result"] = (
                "unconfirmed_do_not_retry" if stage == "apply"
                else "skipped_safety_check"
            )
            report["reason"] = str(exc)
            _LOGGER.warning(
                "Ariston Cube automatic Energy hour %s: %s (%s). No retry",
                target_start, report["result"], type(exc).__name__,
            )
        except Exception as exc:
            # Avoid secrets or raw cloud response dumps in logs/status.
            report["result"] = (
                "unconfirmed_do_not_retry" if stage == "apply"
                else "skipped_error"
            )
            report["reason"] = type(exc).__name__
            _LOGGER.warning(
                "Ariston Cube automatic Energy hour %s: %s (%s). No retry",
                target_start, report["result"], type(exc).__name__,
            )
        finally:
            self._record(report)

    def _record(self, report: dict[str, Any]) -> None:
        self._history.append(report)
        self._history = self._history[-MAX_HISTORY:]
        if report.get("result") not in (
            "verified_hourly_import", "no_change_needed"
        ):
            _LOGGER.info(
                "Ariston Cube Energy hour status is available through "
                "inspect_automatic_energy_hour_alignment"
            )
