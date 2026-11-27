"""One-shot Cube S manual override until the next *real* weekly preset change.

The boiler knows only ZoneMode=2 (manual) and ZoneMode=3 (AUTO).
This module holds the temporary override state in Home Assistant, not Ariston.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta, timezone
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import AristonZoneModeNotSent
from .const import DOMAIN
from .states import enum_code
from .weekly_program import DAYS_IT

_LOGGER = logging.getLogger(__name__)
_STORE_VERSION = 1
_MAX_PREWRITE_RETRIES = 3


def next_preset_transition(program: dict[str, Any], after: datetime, tz: Any) -> datetime | None:
    """Find the next actual Comfort/Economy change, in UTC (not a redundant slice).

    Require all seven days: a partial or malformed cloud plan is not a safe
    foundation for an unattended boiler command. A prior day provides the
    incoming preset at midnight; eight future days cover the entire cycle.
    """
    if after.tzinfo is None or after.utcoffset() is None or tz is None:
        raise ValueError("An aware timestamp and boiler timezone are required")
    days = program.get("days") if isinstance(program, dict) else None
    if not isinstance(days, dict):
        raise ValueError("Cube S weekly schedule is unavailable")
    for name in DAYS_IT:
        if not isinstance(days.get(name), list) or not days[name]:
            raise ValueError("All seven Cube S schedule days are required")

    first = after.astimezone(tz).date() - timedelta(days=1)
    events: list[tuple[datetime, str]] = []
    for offset in range(10):
        day = first + timedelta(days=offset)
        day_index = (day.weekday() + 1) % 7  # Sunday=0 in Ariston.
        for item in days[DAYS_IT[day_index]]:
            if not isinstance(item, dict):
                raise ValueError("Invalid Cube S schedule slice")
            minute, preset = item.get("minute"), item.get("preset")
            if type(minute) is not int or not 0 <= minute < 1440 or preset not in ("Comfort", "Economy"):
                raise ValueError("Invalid Cube S time or preset")
            naive = datetime.combine(day, time(minute // 60, minute % 60))
            local = naive.replace(tzinfo=tz)
            utc = local.astimezone(timezone.utc)
            if utc.astimezone(tz).replace(tzinfo=None) != naive:
                raise ValueError("Schedule contains a nonexistent local time")
            events.append((utc, preset))
    events.sort(key=lambda item: item[0])
    previous = None
    after_utc = after.astimezone(timezone.utc)
    for timestamp, preset in events:
        if previous is not None and preset != previous and timestamp > after_utc:
            return timestamp
        previous = preset
    return None


class TemporaryManualController:
    """Persist, schedule, and verify a one-shot AUTO restoration.

    A completed/uncertain timer attempt is never replayed automatically.
    Only a positively identified pre-write failure permits bounded retries.
    Explicit new user commands remain possible.
    """

    def __init__(self, hass: Any, entry: Any, main: Any, weekly: Any) -> None:
        self.hass, self.entry, self.main, self.weekly = hass, entry, main, weekly
        self._store = Store(hass, _STORE_VERSION, f"{DOMAIN}_temporary_manual_{entry.entry_id}")
        self._lock = asyncio.Lock()
        self.activated_at: datetime | None = None
        self.deadline: datetime | None = None
        self.attempted = False
        self.retry_count = 0
        self.retry_at: datetime | None = None
        self.error: str | None = None
        self._cancel_timer = None
        self._unsubscribers: list[Any] = []
        self._stopped = False

    @property
    def active(self) -> bool:
        return self.deadline is not None

    def attributes(self) -> dict[str, Any]:
        if not self.active:
            return {}
        return {
            "ariston_ritorno_auto_previsto": self.deadline.isoformat(),
            "ariston_manuale_temporaneo_scaduto": self.attempted,
            "ariston_manuale_temporaneo_esito": self.error or ("scaduto" if self.attempted else "programmato"),
        }

    async def async_initialize(self) -> None:
        raw = await self._store.async_load()
        if isinstance(raw, dict) and raw.get("deadline") and raw.get("activated_at"):
            try:
                activated = datetime.fromisoformat(raw["activated_at"])
                deadline = datetime.fromisoformat(raw["deadline"])
                if (activated.utcoffset() is None or deadline.utcoffset() is None
                        or deadline <= activated):
                    raise ValueError("Invalid saved override timestamps")
            except (TypeError, ValueError, OverflowError) as exc:
                _LOGGER.warning("Ignoring invalid saved Cube S temporary override: %s", type(exc).__name__)
            else:
                self.activated_at, self.deadline = activated, deadline
                self.attempted = raw.get("attempted") is True
                self.error = "non_confermato" if self.attempted else None
                retry_count = raw.get("retry_count", 0)
                self.retry_count = retry_count if type(retry_count) is int and 0 <= retry_count <= _MAX_PREWRITE_RETRIES else _MAX_PREWRITE_RETRIES
                if not self.attempted and raw.get("retry_at"):
                    try:
                        retry_at = datetime.fromisoformat(raw["retry_at"])
                        if retry_at.utcoffset() is None:
                            raise ValueError("Naive retry timestamp")
                        self.retry_at = max(deadline, retry_at)
                        self.error = "nuovo_tentativo_programmato"
                    except (TypeError, ValueError, OverflowError):
                        self.attempted = True
                        self.error = "non_confermato"
                mode = enum_code((self.main.data or {}).get("ZoneMode"))
                if mode is not None and mode != 2:
                    await self._clear_locked()
                elif not self.attempted:
                    self._arm_timer()
                else:
                    self._alert_restore_failure()
        self._unsubscribers.extend((
            self.main.async_add_listener(self._on_main_update),
            self.weekly.async_add_listener(self._on_schedule_update),
        ))
        self.main.async_update_listeners()

    def stop(self) -> None:
        self._stopped = True
        self._cancel_clock()
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    def _notify(self) -> None:
        self.main.async_update_listeners()

    def _cancel_clock(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    def _arm_timer(self) -> None:
        self._cancel_clock()
        if self._stopped or not self.active or self.attempted:
            return
        due = self.retry_at or self.deadline
        if due <= dt_util.utcnow():
            self.entry.async_create_background_task(
                self.hass, self.async_expire(), "Ariston Cube overdue AUTO restoration"
            )
        else:
            self._cancel_timer = async_track_point_in_utc_time(
                self.hass, self.async_expire, due
            )

    async def _save(self) -> None:
        value = ({
            "activated_at": self.activated_at.isoformat(),
            "deadline": self.deadline.isoformat(),
            "attempted": self.attempted,
            "retry_count": self.retry_count,
            "retry_at": self.retry_at.isoformat() if self.retry_at else None,
        } if self.active else {})
        await self._store.async_save(value)

    async def _clear_locked(self) -> None:
        self._cancel_clock()
        self.activated_at = self.deadline = None
        self.attempted = False
        self.retry_count = 0
        self.retry_at = None
        self.error = None
        await self._save()
        self._dismiss_restore_failure()
        self._notify()

    async def async_activate(self) -> None:
        async with self._lock:
            if self._stopped:
                raise HomeAssistantError("Ariston Cube is unloading")
            if self.active and not self.attempted:
                return
            # A fresh programme read precedes any cloud mode write.
            try:
                await self.weekly.async_refresh()
                if not self.weekly.last_update_success or not self.weekly.data:
                    raise ValueError("Weekly schedule is not available")
                started = dt_util.utcnow()
                tz = dt_util.get_time_zone(self.hass.config.time_zone)
                deadline = next_preset_transition(self.weekly.data, started, tz)
                if deadline is None:
                    raise ValueError("No upcoming Comfort/Economy transition")
            except (ValueError, HomeAssistantError) as exc:
                raise HomeAssistantError(str(exc)) from exc
            # Existing, guarded GET/POST/GET. A cloud failure never arms a timer.
            await self.main.async_set_zone_mode(2)
            self.activated_at, self.deadline = started, deadline
            self.attempted, self.error = False, None
            self.retry_count, self.retry_at = 0, None
            try:
                await self._save()
            except Exception as exc:
                _LOGGER.error("Cube S temporary override persistence failed (%s)", type(exc).__name__)
                # Still schedule locally; no additional cloud command is safe here.
            self._arm_timer()
            self._dismiss_restore_failure()
            self._notify()

    async def async_select_permanent(self, mode: int) -> None:
        async with self._lock:
            await self.main.async_set_zone_mode(mode)
            if self.active:
                await self._clear_locked()

    async def async_expire(self, _now: datetime | None = None) -> None:
        async with self._lock:
            if (self._stopped or not self.active or self.attempted
                    or dt_util.utcnow() < (self.retry_at or self.deadline)):
                return
            self._cancel_clock()
            # Persist attempt BEFORE the write: restart cannot replay a
            # possibly accepted POST with an ambiguous response.
            self.attempted = True
            self.retry_at = None
            self.error = "in_attesa"
            try:
                await self._save()
            except Exception as exc:
                self.error = "persistenza_non_disponibile"
                _LOGGER.error("Cube S AUTO restoration not sent: storage %s", type(exc).__name__)
                self._notify()
                self._alert_restore_failure()
                return
            self._notify()
            try:
                await self.main.async_set_zone_mode(3)
            except Exception as exc:
                cause = exc.__cause__ if isinstance(exc, HomeAssistantError) else exc
                if isinstance(cause, AristonZoneModeNotSent) and self.retry_count < _MAX_PREWRITE_RETRIES:
                    self.retry_count += 1
                    delay = max(300.0, self.main.client.rate_limit.remaining_seconds())
                    self.retry_at = dt_util.utcnow() + timedelta(seconds=delay)
                    self.attempted = False
                    self.error = "nuovo_tentativo_programmato"
                    try:
                        await self._save()
                    except Exception:
                        self.attempted = True
                        self.retry_at = None
                        self.error = "persistenza_non_disponibile"
                        self._alert_restore_failure()
                    else:
                        self._arm_timer()
                else:
                    self.error = "non_confermato"
                    _LOGGER.warning("Cube S AUTO restoration unconfirmed (%s); no retry", type(exc).__name__)
                    self._alert_restore_failure()
                self._notify()
            else:
                await self._clear_locked()

    def _dismiss_restore_failure(self) -> None:
        from homeassistant.components import persistent_notification

        persistent_notification.async_dismiss(
            self.hass, f"{DOMAIN}_temporary_manual_{self.entry.entry_id}"
        )

    def _alert_restore_failure(self) -> None:
        """Make an unconfirmed restoration visible outside the entity attributes."""
        from homeassistant.components import persistent_notification

        persistent_notification.async_create(
            self.hass,
            "Il ritorno automatico in AUTO non è confermato. Verifica la modalità del Cube S nell’app Ariston NET.",
            title="Ariston Cube: ritorno in AUTO non confermato",
            notification_id=f"{DOMAIN}_temporary_manual_{self.entry.entry_id}",
        )

    def _on_main_update(self) -> None:
        if self._stopped or not self.active or self._lock.locked():
            return
        mode = enum_code((self.main.data or {}).get("ZoneMode"))
        if mode is not None and mode != 2:
            self.entry.async_create_background_task(
                self.hass, self._cancel_on_external_mode(),
                "Ariston Cube cancel temporary override on external mode"
            )

    async def _cancel_on_external_mode(self) -> None:
        async with self._lock:
            if self.active and enum_code((self.main.data or {}).get("ZoneMode")) not in (None, 2):
                await self._clear_locked()

    def _on_schedule_update(self) -> None:
        if self._stopped or not self.active or self.attempted:
            return
        self.entry.async_create_background_task(
            self.hass, self.async_recompute(), "Ariston Cube reschedule temporary override"
        )

    async def async_recompute(self) -> None:
        async with self._lock:
            if self._stopped or not self.active or self.attempted or self.retry_count or not self.weekly.data:
                return
            try:
                tz = dt_util.get_time_zone(self.hass.config.time_zone)
                deadline = next_preset_transition(self.weekly.data, self.activated_at, tz)
            except ValueError as exc:
                _LOGGER.warning("Cube S temporary override reschedule skipped (%s)", type(exc).__name__)
                return
            if deadline is None or deadline == self.deadline:
                return
            self.deadline = deadline
            await self._save()
            self._arm_timer()
            self._notify()
