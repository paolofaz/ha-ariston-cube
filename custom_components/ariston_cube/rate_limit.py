"""Shared, conservative HTTP 429 cooldown for the Ariston NET cloud.

The mobile API and cookie-authenticated R2 portal share one instance per
integration entry. Nothing here retries or queues cloud writes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time


class RateLimitActive(Exception):
    """Cloud requests are suspended locally after an HTTP 429."""


def _retry_after_seconds(headers: Mapping[str, str] | None) -> float:
    """Accept an RFC Retry-After delay or HTTP date without storing headers."""
    if not headers:
        return 0.0
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return 0.0
    value = str(raw).strip()
    if value.isdecimal():
        # Avoid absurdly long / malformed numeric values.
        return float(value) if len(value) < 12 else 0.0
    try:
        deadline = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return max(0.0, (deadline - datetime.now(timezone.utc)).total_seconds())


class RateLimitBackoff:
    """Fail fast during cooldown; never sleep in, queue, or retry an API call.

    After repeated HTTP 429 responses: 5, 10, 20, 40, then 60 minutes
    (capped). A valid Retry-After may demand a longer pause.
    A subsequent successful response resets the escalation only when the
    existing cooldown has expired. An in-flight success cannot clear a 429.
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._blocked_until = 0.0
        self._strikes = 0

    def remaining_seconds(self) -> float:
        return max(0.0, self._blocked_until - self._clock())

    def check(self) -> None:
        if self.remaining_seconds() > 0:
            raise RateLimitActive("Ariston HTTP 429 cooldown active")

    def record_429(self, headers: Mapping[str, str] | None = None) -> None:
        self._strikes = min(self._strikes + 1, 5)
        delay = min(300 * (2 ** (self._strikes - 1)), 3600)
        delay = max(delay, _retry_after_seconds(headers))
        self._blocked_until = max(self._blocked_until, self._clock() + delay)

    def record_success(self) -> None:
        if self.remaining_seconds() <= 0:
            self._blocked_until = 0.0
            self._strikes = 0
