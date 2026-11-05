"""Separate Ariston /R2 cookie login for read/write Comfort and Smc reports.

The mobile 'ar.authToken' does NOT authenticate /R2. The HTML login has an
anti-forgery form token that must be echoed as a cookie. No user credentials,
cookies or response payloads are ever logged.
"""

from __future__ import annotations

import asyncio
import html
import json
import math
import re
import time
from typing import Any

import aiohttp
from yarl import URL

from .const import BASE_URL
from .rate_limit import RateLimitActive, RateLimitBackoff

_TOKEN_RE = re.compile(
    r"""<input\b(?=[^>]*\bname=["']__RequestVerificationToken["'])(?=[^>]*\bvalue=["']([^"']+)["'])[^>]*>""",
    flags=re.IGNORECASE,
)
_XHR_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Ajax-Request": "json",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json; charset=UTF-8",
}


# Login-page navigation needs browser-style HTML headers, not the
# Home Assistant client User-Agent nor an API-specific JSON Accept header.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_LOGIN_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "User-Agent": _BROWSER_USER_AGENT,
}
_XHR_HEADERS["User-Agent"] = _BROWSER_USER_AGENT

# A forbidden web login is a host/access failure; no repeated requests
# every 30 minutes while Comfort / Smc remain unavailable.
_FORBIDDEN_RETRY_DELAY_SECONDS = 7200


class WebPortalError(Exception):
    """Sanitized web portal error—never includes raw response or URL."""


class WebPortalAuthError(WebPortalError):
    """Cookie login cannot be established."""


class WebPortalComfortShapeError(WebPortalError):
    """Schema-only details for diagnostics; never stores raw menu values."""

    def __init__(self, value: Any, options: Any) -> None:
        super().__init__("ACS Comfort menu value format not recognized")
        self.value_kind = type(value).__name__
        self.option_count = len(options) if isinstance(options, list) else None
        self.option_value_kinds = sorted({
            type(item.get("value")).__name__
            for item in options[:20] if isinstance(item, dict)
        }) if isinstance(options, list) else []


def comfort_option_code(raw: Any) -> int | None:
    """Canonical 0/1/2 for JSON integer, decimal, or numeric text.

    Never coerce bool or labels without matching the server's option list.
    """
    if type(raw) is int and raw in (0, 1, 2):
        return raw
    if type(raw) is float and math.isfinite(raw) and raw in (0.0, 1.0, 2.0):
        return int(raw)
    if isinstance(raw, str):
        value = raw.strip()
        if value in ("0", "1", "2", "0.0", "1.0", "2.0"):
            return int(value[0])
    return None


class AristonWebPortal:
    """Serializes /R2 requests; never mixes mobile and web authentication."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str,
        *, rate_limit: RateLimitBackoff | None = None,
    ):
        self._session = session
        self._username = username
        self._password = password
        self._logged_in = False
        self._lock = asyncio.Lock()
        self._rate_limit = rate_limit if rate_limit is not None else RateLimitBackoff()
        self._web_login_blocked_until = 0.0
        self._blocked_login_http_status: int | None = None

    async def _login(self) -> None:
        """Use the existing R2 anti-CSRF cookie login, once per session."""
        try:
            self._rate_limit.check()
        except RateLimitActive as exc:
            raise WebPortalAuthError("Web login form HTTP 429 (cooldown active)") from exc
        if self._logged_in:
            return
        if time.monotonic() < self._web_login_blocked_until:
            raise WebPortalAuthError(
                f"Web login form HTTP {self._blocked_login_http_status}"
            )
        try:
            async with self._session.get(
                BASE_URL + "/R2/Account/Login",
                headers=_LOGIN_HEADERS,
                timeout=aiohttp.ClientTimeout(total=25),
                allow_redirects=True,
                max_redirects=5,
            ) as response:
                if response.status != 200:
                    if response.status == 429:
                        self._rate_limit.record_429(getattr(response, "headers", None))
                    elif response.status == 403:
                        self._web_login_blocked_until = (
                            time.monotonic() + _FORBIDDEN_RETRY_DELAY_SECONDS
                        )
                        self._blocked_login_http_status = response.status
                    raise WebPortalAuthError(f"Web login form HTTP {response.status}")
                final_url = getattr(response, "url", URL(BASE_URL))
                if final_url.host != URL(BASE_URL).host or final_url.scheme != "https":
                    raise WebPortalAuthError("Web login form cross-host redirect")
                form = await response.text()
            match = _TOKEN_RE.search(form)
            if not match:
                raise WebPortalAuthError("Web login anti-forgery token unavailable")
            cookie = html.unescape(match.group(1))
            self._session.cookie_jar.update_cookies(
                {"__formRequestVerificationToken": cookie},
                response_url=URL(BASE_URL),
            )
            async with self._session.post(
                BASE_URL + "/R2/Account/Login",
                headers=_XHR_HEADERS,
                json={
                    "email": self._username,
                    "password": self._password,
                    "rememberMe": False,
                    "language": "Italian_It",
                },
                timeout=aiohttp.ClientTimeout(total=25),
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    if response.status == 429:
                        self._rate_limit.record_429(getattr(response, "headers", None))
                    raise WebPortalAuthError(f"Web login POST HTTP {response.status}")
                try:
                    data = await response.json(content_type=None)
                except (ValueError, json.JSONDecodeError, aiohttp.ContentTypeError):
                    raise WebPortalAuthError("Non-JSON web login reply") from None
            if not isinstance(data, dict) or data.get("ok") is not True:
                raise WebPortalAuthError("Web portal rejected login")
            self._logged_in = True
            self._rate_limit.record_success()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise WebPortalAuthError(
                f"Web portal {type(exc).__name__} during login"
            ) from exc

    async def _request(self, method: str, path: str, *, payload: Any = None) -> Any:
        """Authenticated web request with no retries on POST or errors."""
        try:
            self._rate_limit.check()
        except RateLimitActive as exc:
            raise WebPortalError("Ariston HTTP 429 cooldown active") from exc
        try:
            async with self._session.request(
                method, BASE_URL + path,
                headers=_XHR_HEADERS,
                json=payload if method == "POST" else None,
                timeout=aiohttp.ClientTimeout(total=35),
                allow_redirects=False,
            ) as response:
                if response.status in (301, 302, 303, 401, 403):
                    self._logged_in = False
                    raise WebPortalAuthError("Web portal authorization failed")
                if response.status == 429:
                    self._rate_limit.record_429(getattr(response, "headers", None))
                    raise WebPortalError("Web portal HTTP 429")
                if response.status != 200:
                    raise WebPortalError(f"Web portal HTTP {response.status}")
                try:
                    result = await response.json(content_type=None)
                    self._rate_limit.record_success()
                    return result
                except (ValueError, json.JSONDecodeError, aiohttp.ContentTypeError):
                    raise WebPortalError("Web portal returned non-JSON") from None
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise WebPortalError(f"Web portal {type(exc).__name__}") from exc

    @staticmethod
    def _unwrap(data: Any) -> Any:
        return data.get("data") if isinstance(data, dict) and "data" in data else data

    @staticmethod
    def comfort_record(data: Any) -> dict[str, Any]:
        """Find actual U6_9_2 option without guessing an unknown mode."""
        entries = AristonWebPortal._unwrap(data)
        if not isinstance(entries, list):
            raise WebPortalError("Unexpected ACS Comfort response")
        records = [
            row for row in entries
            if isinstance(row, dict) and row.get("id") == "U6_9_2"
        ]
        if len(records) != 1:
            raise WebPortalError("ACS Comfort parameter absent or duplicated")
        record = records[0]
        raw = record.get("value")
        options = record.get("dropDownOptions")
        code = comfort_option_code(raw)

        # The legacy integration used the declared dropdown value/text pairs
        # rather than assuming the REST response was an integer. Text matching
        # is allowed only when it identifies exactly ONE declared 0/1/2 option.
        if code is None and isinstance(raw, str) and isinstance(options, list):
            matches = [
                comfort_option_code(option.get("value"))
                for option in options
                if isinstance(option, dict)
                and isinstance(option.get("text"), str)
                and option["text"].strip().casefold() == raw.strip().casefold()
            ]
            if len(matches) == 1:
                code = matches[0]

        if code is None:
            raise WebPortalComfortShapeError(raw, options)
        return {"value": code, "dropDownOptions": options}

    async def async_read_comfort(self, gateway: str) -> dict[str, Any]:
        async with self._lock:
            await self._login()
            return self.comfort_record(await self._request(
                "GET", f"/R2/PlantMenu/Refresh?id={gateway}&paramIds=U6_9_2"
            ))

    async def async_set_comfort(self, gateway: str, desired: int) -> int:
        """Set only OFF (0) or ALWAYS (2), single non-retried write + readback."""
        if type(desired) is not int or desired not in (0, 2):
            raise WebPortalError("Only OFF and Always Active are supported")
        async with self._lock:
            await self._login()
            path = f"/R2/PlantMenu/Refresh?id={gateway}&paramIds=U6_9_2"
            before = self.comfort_record(await self._request("GET", path))
            old = before["value"]
            if old == 1:
                # We intentionally do not trample a time-based schedule.
                raise WebPortalError("Timed ACS Comfort must be changed at the boiler")
            options = before.get("dropDownOptions")
            if not isinstance(options, list):
                raise WebPortalError("Comfort choices not declared by gateway")
            allowed_list = [
                comfort_option_code(opt.get("value"))
                for opt in options if isinstance(opt, dict)
            ]
            allowed = {code for code in allowed_list if code is not None}
            # Reject ambiguous/malformed dropdown declarations.
            if len(allowed_list) != len(allowed) or old not in allowed:
                raise WebPortalError("Comfort choices ambiguous or incomplete")
            if desired not in allowed:
                raise WebPortalError("Desired Comfort mode not offered")
            if desired == old:
                return old
            response = await self._request(
                "POST", f"/R2/PlantMenu/Submit/{gateway}",
                payload=[{
                    "id": "U6_9_2", "value": desired, "prevValue": old,
                }],
            )
            if isinstance(response, dict) and (
                response.get("ok") is False or response.get("success") is False
            ):
                raise WebPortalError("ACS Comfort command rejected")
            confirmed = self.comfort_record(await self._request("GET", path))["value"]
            if confirmed != desired:
                raise WebPortalError(
                    "ACS Comfort write sent but not confirmed: do not repeat"
                )
            return confirmed

    async def async_read_metering(self, gateway: str) -> dict[str, Any]:
        """Read gateway-provided physical Smc report; no guessed conversion."""
        async with self._lock:
            await self._login()
            features = self._unwrap(await self._request(
                "GET", f"/R2/Plant/Features/{gateway}?eagerMode=true"
            ))
            if not isinstance(features, dict) or not features:
                raise WebPortalError("Metering features unavailable")
            report = self._unwrap(await self._request(
                "POST", f"/R2/PlantMetering/GetData/{gateway}",
                payload={"features": features, "hasCooling": False},
            ))
            if not isinstance(report, dict) or not isinstance(
                report.get("asPhysicalUnit"), dict
            ):
                raise WebPortalError("Physical Smc data not available")
            return report
