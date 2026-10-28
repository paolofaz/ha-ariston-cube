"""EXPERIMENTAL hourly Energy-dashboard attribution; stable gas ledger untouched.

A closed Ariston 2h bucket (06-08) usually increments a Recorder sensor
during 08-09. After 09-00, update ONLY the existing 07-08 hourly statistics
row, setting its cumulative sum to the 08-09 row's sum. Then:

07-08: +bucket, 08-09: 0, later sums: unchanged.

The integration NEVER changes an entity state, a short-term statistic,
Recorder SQLite directly, the gas ledger, or any earlier unrelated hour.
It uses HA's supported async_import_statistics on an existing hourly row.
This first experiment must be triggered manually, never in the background.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from typing import Any

_KINDS = {
    "heating": "total_heating_smc",
    "dhw": "total_dhw_smc",
}
_EPS = 0.0005
_MAX_BUCKET = 25.0  # fail closed on large/mixed/corrupt changes
UTC = timezone.utc


class AlignmentRejected(ValueError):
    """Fail closed; no statistics import attempted."""


def slot_from_now(now: datetime) -> datetime:
    """Return the latest 2h boundary with its *following* hourly row closed.

    Ariston two-hour boundaries are local clock even hours. Wait until
    :15 of the following odd hour for Recorder's hourly compilation.
    Do not cross DST offset transitions in this first field experiment.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise AlignmentRejected("Timezone-aware local time required")
    h = now.hour
    back = 2 if h % 2 == 0 else 1 if now.minute >= 15 else 3
    end = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=back)
    start = (end.astimezone(UTC) - timedelta(hours=1)).astimezone(now.tzinfo)
    next_hour = (end.astimezone(UTC) + timedelta(hours=1)).astimezone(now.tzinfo)
    if (
        end.hour % 2 != 0
        or start.hour != (end.hour - 1) % 24
        or next_hour.hour != (end.hour + 1) % 24
        or len({start.utcoffset(), end.utcoffset(), next_hour.utcoffset()}) != 1
    ):
        raise AlignmentRejected("DST boundary unsupported; no change attempted")
    if not timedelta(hours=1) <= now.astimezone(UTC) - end.astimezone(UTC) < timedelta(hours=5):
        raise AlignmentRejected("No recent completed two-hour bucket")
    return end


def plan_pair(
    *, entity_id: str, kind: str, bucket: float,
    target: dict[str, Any], following: dict[str, Any],
) -> dict[str, Any]:
    """Compare *existing* hourly statistics with the real 2h cloud bucket.

    The state difference verifies that the new sample in the following
    hour belongs to exactly this cloud bucket. Only then consider writing.
    """
    if kind not in _KINDS or not entity_id.startswith("sensor."):
        raise AlignmentRejected("Invalid gas statistic identity")
    if not isinstance(bucket, (int, float)) or isinstance(bucket, bool):
        raise AlignmentRejected("No verified Ariston bucket")
    if not math.isfinite(bucket) or not 0 <= bucket <= _MAX_BUCKET:
        raise AlignmentRejected("Unexpected Ariston bucket amount")
    fields = ("sum", "state")
    for row in (target, following):
        if not isinstance(row, dict) or any(
            not isinstance(row.get(f), (int, float))
            or isinstance(row.get(f), bool)
            or not math.isfinite(row[f])
            for f in fields
        ):
            raise AlignmentRejected("Missing or invalid hourly statistics")
    first_sum, second_sum = float(target["sum"]), float(following["sum"])
    state_delta = round(float(following["state"]) - float(target["state"]), 6)
    sum_delta = round(second_sum - first_sum, 6)
    if state_delta < -_EPS or abs(state_delta - bucket) > _EPS:
        raise AlignmentRejected(
            "Recorder state change does not match the Ariston 2h bucket"
        )
    if bucket < _EPS and abs(sum_delta) < _EPS:
        status = "zero_consumption"
    elif abs(sum_delta) < _EPS:
        status = "already_aligned"
    elif abs(sum_delta - bucket) <= _EPS:
        status = "can_shift"
    else:
        raise AlignmentRejected(
            "Recorder hourly sum does not match the Ariston bucket"
        )
    return {
        "kind": kind, "entity_id": entity_id, "status": status,
        "bucket_smc": round(float(bucket), 6),
        "current_target_sum": first_sum,
        "current_following_sum": second_sum,
        "proposed_target_sum": second_sum,
        "original_target_state": float(target["state"]),
    }


def fingerprint_plan(plan: dict[str, Any]) -> str:
    return sha256(json.dumps(
        {"target_start": plan["target_start"],
         "following_start": plan["following_start"],
         "operations": plan["operations"]},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


class EnergyHourAligner:
    """One-shot field operation for the currently selected last closed slot."""

    def __init__(self, hass: Any, main: Any):
        self.hass = hass
        self.main = main
        self._lock = asyncio.Lock()

    def _bucket(self, kind: str, end: datetime) -> float:
        smc = getattr(self.main, "smc_coordinator", None)
        state = getattr(getattr(smc, "gas_ledger", None), "_state", None)
        if not isinstance(state, dict) or state.get("continuity_lost"):
            raise AlignmentRejected("Gas ledger not ready or continuity lost")
        # Check that an actual, current, published sensor reading exists.
        data = getattr(smc, "data", None)
        if not isinstance(data, dict) or data.get(_KINDS[kind]) is None:
            raise AlignmentRejected("Smc sensor unavailable; no change attempted")
        start = (end.astimezone(UTC) - timedelta(hours=1)).astimezone(end.tzinfo)
        day = start.date().isoformat()
        idx = str(start.hour // 2)
        bucket = state.get("days", {}).get(day, {}).get(kind, {}).get(idx)
        if bucket is None:
            raise AlignmentRejected("Verified Ariston bucket not available in ledger")
        return bucket

    async def _statistics_window(
        self, stat_id: str, start: datetime, hours: int
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Read only already-compiled hourly Recorder rows using its API."""
        from functools import partial
        from homeassistant.components import recorder
        from homeassistant.components.recorder import statistics as stats

        instance = recorder.get_instance(self.hass)
        meta = await instance.async_add_executor_job(
            partial(stats.get_metadata, self.hass, statistic_ids={stat_id})
        )
        if stat_id not in meta:
            raise AlignmentRejected("Existing gas statistic not found")
        metadata = meta[stat_id][1]
        if (
            metadata.get("source") != "recorder"
            or not metadata.get("has_sum")
            or metadata.get("unit_of_measurement") != "m³"
        ):
            raise AlignmentRejected("Existing gas statistic metadata is not compatible")
        rows = await instance.async_add_executor_job(
            stats.statistics_during_period,
            self.hass, start, start + timedelta(hours=hours), {stat_id},
            "hour", {}, {"state", "sum"},
        )
        found = {
            int(float(row["start"])): row for row in rows.get(stat_id, [])
            if "start" in row
        }
        selected = [
            found.get(int((start + timedelta(hours=idx)).timestamp()))
            for idx in range(hours)
        ]
        if any(row is None for row in selected):
            raise AlignmentRejected("Requested completed hourly rows not available")
        return metadata, selected

    async def _statistics(self, stat_id: str, start: datetime):
        metadata, rows = await self._statistics_window(stat_id, start, 2)
        return metadata, rows[0], rows[1]

    async def inspect_hour(self, target_start: str) -> dict[str, Any]:
        """Explicit read-only status for an earlier hour, including this morning.

        Reads three hourly statistics rows (preceding, target, following).
        No gas ledger mutation, no statistics import, no hidden retries.
        """
        from homeassistant.helpers import entity_registry as er
        from homeassistant.util import dt as dt_util

        try:
            target = datetime.fromisoformat(target_start)
        except (TypeError, ValueError) as exc:
            raise AlignmentRejected("Use an ISO 8601 timestamp with UTC offset") from exc
        if target.tzinfo is None or target.utcoffset() is None:
            raise AlignmentRejected("Target timestamp must have timezone offset")
        target = target.astimezone(UTC)
        if any((target.minute, target.second, target.microsecond)):
            raise AlignmentRejected("Target timestamp must begin at a whole hour")
        now = dt_util.utcnow()
        if not timedelta(hours=2) <= now - target <= timedelta(hours=72):
            raise AlignmentRejected("Only fully compiled hours in the last 72h are readable")
        async with self._lock:
            registry = er.async_get(self.hass)
            findings = []
            for kind, source_key in _KINDS.items():
                entity_id = registry.async_get_entity_id(
                    "sensor", "ariston_cube",
                    f"{self.main.plant_id}_gas_meter_v1_{source_key}"
                )
                if not entity_id:
                    raise AlignmentRejected(f"Existing {kind} gas sensor not registered")
                _, rows = await self._statistics_window(
                    entity_id, target - timedelta(hours=1), 3
                )
                previous, current, following = rows
                values = [previous["sum"], current["sum"], following["sum"]]
                if any(type(value) not in (int, float)
                       or not math.isfinite(value) for value in values):
                    raise AlignmentRejected("Hourly statistics contain an invalid sum")
                findings.append({
                    "kind": kind, "entity_id": entity_id,
                    "preceding_sum": round(float(values[0]), 6),
                    "target_sum": round(float(values[1]), 6),
                    "following_sum": round(float(values[2]), 6),
                    "consumption_in_target_hour": round(values[1] - values[0], 6),
                    "consumption_in_following_hour": round(values[2] - values[1], 6),
                })
            return {
                "status": "read_only_no_statistics_write",
                "target_start": target.isoformat(),
                "following_start": (target + timedelta(hours=1)).isoformat(),
                "operations": findings,
            }

    async def _wait_for_readback(
        self, instance: Any, operation: dict[str, Any], start: datetime,
    ) -> None:
        """Await eventually consistent Recorder readback; NEVER import twice.

        The initial import is queued asynchronously. A single immediate read
        can race the commit, so poll only read operations for at most 12s.
        """
        for attempt in range(12):
            await instance.async_block_till_done()
            _, target, following = await self._statistics(
                operation["entity_id"], start
            )
            if (
                abs(float(target["sum"]) - operation["proposed_target_sum"]) <= _EPS
                and abs(float(following["sum"]) -
                        operation["current_following_sum"]) <= _EPS
            ):
                return
            if attempt < 11:
                await asyncio.sleep(1)
        raise AlignmentRejected(
            "The import was sent but readback is still unconfirmed after "
            "12 checks. Do not retry; use inspect_energy_hour_alignment."
        )

    async def _plan(self, now: datetime) -> dict[str, Any]:
        from homeassistant.helpers import entity_registry as er

        end = slot_from_now(now)
        start = end.astimezone(UTC) - timedelta(hours=1)
        registry = er.async_get(self.hass)
        operations = []
        for kind, source_key in _KINDS.items():
            entity_id = registry.async_get_entity_id(
                "sensor", "ariston_cube",
                f"{self.main.plant_id}_gas_meter_v1_{source_key}"
            )
            if not entity_id or self.hass.states.get(entity_id) is None:
                raise AlignmentRejected(f"Existing {kind} sensor not registered")
            metadata, first, next_ = await self._statistics(entity_id, start)
            operation = plan_pair(
                entity_id=entity_id, kind=kind,
                bucket=self._bucket(kind, end),
                target=first, following=next_,
            )
            # Preserve the exact metadata and state of the existing hourly
            # row, but NEVER expose private metadata or a raw DB handle.
            operation["_metadata"] = metadata
            operations.append(operation)
        safe_ops = [{k: v for k, v in item.items() if not k.startswith("_")}
                    for item in operations]
        plan = {
            "target_start": start.isoformat(),
            "following_start": (start + timedelta(hours=1)).isoformat(),
            "local_bucket": (
                (end - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
                + "–" + end.strftime("%H:%M")
            ),
            "operations": safe_ops,
        }
        plan["fingerprint"] = fingerprint_plan(plan)
        plan["_operations"] = operations
        return plan

    @staticmethod
    def _public(plan: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in plan.items()
                if not key.startswith("_")}

    async def preview(self) -> dict[str, Any]:
        from homeassistant.util import dt as dt_util

        async with self._lock:
            return {"status": "preview_only_no_statistics_write",
                    **self._public(await self._plan(dt_util.now()))}

    async def apply(self, expected_fingerprint: str) -> dict[str, Any]:
        from homeassistant.components import recorder
        from homeassistant.components.recorder import statistics as stats
        from homeassistant.util import dt as dt_util

        async with self._lock:
            plan = await self._plan(dt_util.now())
            if not isinstance(expected_fingerprint, str) or (
                plan["fingerprint"] != expected_fingerprint
            ):
                raise AlignmentRejected(
                    "Hourly values changed since preview; no import performed"
                )
            instance = recorder.get_instance(self.hass)
            modified = []
            for operation in plan["_operations"]:
                if operation["status"] != "can_shift":
                    continue
                start = datetime.fromisoformat(plan["target_start"])
                # No modification to raw sensor states, short-term rows, or
                # existing historical rows outside this single closed hour.
                row = {
                    "start": start, "sum": operation["proposed_target_sum"],
                    "state": operation["original_target_state"],
                    "last_reset": None,
                }
                stats.async_import_statistics(
                    self.hass, dict(operation["_metadata"]), [row]
                )
                # One import only. Poll read-only results until the Recorder
                # queue and its hourly statistics view agree, or time out.
                await self._wait_for_readback(instance, operation, start)
                modified.append(operation["entity_id"])
            return {
                "status": "verified_hourly_import"
                if modified else "no_change_needed",
                "target_start": plan["target_start"],
                "shifted_entities": modified,
                "untouched_entities": [
                    op["entity_id"] for op in plan["_operations"]
                    if op["entity_id"] not in modified
                ],
            }
