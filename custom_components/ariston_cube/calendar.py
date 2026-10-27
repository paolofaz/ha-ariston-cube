"""Home Assistant calendar view of the original Cube S heating timetable.

Read-only: calendar events are sourced from the cloud schedule, never written
back via undocumented timeProg endpoints. The source sensor remains available.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.util import dt as dt_util

from .entity import AristonEntity
from .schedule_coordinator import get_or_create_weekly_coordinator
from .weekly_program import calendar_intervals


async def async_setup_entry(hass, entry, async_add_entities):
    schedule = get_or_create_weekly_coordinator(hass, entry)
    async_add_entities([AristonCubeCalendar(schedule)])


class AristonCubeCalendar(AristonEntity, CalendarEntity):
    """Real daily Comfort/Economy timeline in Home Assistant's Calendar UI."""

    _attr_name = "Calendario riscaldamento Cube S"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator):
        super().__init__(coordinator, "weekly_calendar")

    def _events_between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        if not self.coordinator.data:
            return []
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        if tz is None:
            return []
        intervals = calendar_intervals(self.coordinator.data, start, end, tz)
        return [
            CalendarEvent(
                start=item["start"],
                end=item["end"],
                summary=item["preset"] + " riscaldamento",
                description="Programmazione originale Cube S (sola lettura)",
                uid=f"ariston_cube_{item['start'].isoformat()}_{item['preset']}",
            )
            for item in intervals
        ]

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        events = self._events_between(now - timedelta(days=1), now + timedelta(days=8))
        return next((e for e in events if e.end > now), None)

    async def async_get_events(
        self, hass, start_date: datetime, end_date: datetime,
    ) -> list[CalendarEvent]:
        return self._events_between(start_date, end_date)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
