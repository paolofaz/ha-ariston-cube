"""Minimal read-only client for the Ariston NET mobile cloud API.

Uses /api/v2/accounts/login and ar.authToken, not the old /R2 web login.
Device-setting endpoints are deliberately absent.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .const import BASE_URL
from .model import make_main_request, parse_plants

MOBILE_USER_AGENT = "RestSharp/106.11.7.0"


class AristonError(Exception):
    """Base error (no tokens, passwords or personal identifiers)."""


class AristonAuthError(AristonError):
    """Token invalid or login denied."""


class AristonConnectionError(AristonError):
    """Temporary network/cloud service error."""


class AristonResponseError(AristonError):
    """Cloud API response does not match the expected contract."""


def _phase(path: str) -> str:
    """Use non-sensitive request stage names for logs."""
    if path == "/api/v2/accounts/login":
        return "mobile_login"
    if "/plants/lite" in path:
        return "plant_discovery"
    if "/features?" in path:
        return "features"
    if "/dataItems/" in path:
        return "data_read"
    return "cloud_request"


class AristonClient:
    """Async read-only client with per-account token and feature cache."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._features: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def _request(
        self, method: str, path: str, *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        stage = _phase(path)
        headers = {
            "User-Agent": MOBILE_USER_AGENT,
            "ar.authToken": self._token or "",
        }
        try:
            async with self._session.request(
                method, BASE_URL + path, json=json_body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=25), allow_redirects=True,
            ) as response:
                if response.status in (401, 403, 405):
                    raise AristonAuthError(f"Ariston HTTP {response.status} at {stage}")
                if response.status in (408, 425, 429) or response.status >= 500:
                    raise AristonConnectionError(f"Ariston HTTP {response.status} at {stage}")
                if response.status >= 400:
                    raise AristonResponseError(f"Ariston HTTP {response.status} at {stage}")
                if "/account/login" in response.url.path.lower():
                    raise AristonAuthError(f"Redirected to web login at {stage}")
                try:
                    return await response.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError, ValueError) as exc:
                    raise AristonResponseError(f"Non-JSON cloud reply at {stage}") from exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise AristonConnectionError(
                f"Ariston {type(exc).__name__} at {stage}"
            ) from exc

    async def async_login(self) -> None:
        """Request an API token; never expose it in errors or logs."""
        reply = await self._request(
            "POST", "/api/v2/accounts/login",
            json_body={"usr": self._username, "pwd": self._password},
        )
        if not isinstance(reply, dict):
            raise AristonResponseError("Unexpected mobile login reply")
        token = reply.get("token")
        if isinstance(token, str) and token:
            self._token = token
            return
        if reply.get("ok") is False or reply.get("success") is False:
            raise AristonAuthError("Mobile login rejected")
        raise AristonResponseError("Mobile login response without token")

    async def async_list_plants(self) -> list[dict[str, str]]:
        """Fetch gateways using the mobile auth token."""
        if not self._token:
            await self.async_login()
        try:
            return parse_plants(await self._request("GET", "/api/v2/remote/plants/lite"))
        except ValueError as exc:
            raise AristonResponseError("Unexpected plant list response") from exc

    async def _load_features(self, plant_id: str) -> dict[str, Any]:
        if plant_id not in self._features:
            features = await self._request(
                "GET", f"/api/v2/remote/plants/{plant_id}/features?eagerMode=True"
            )
            if not isinstance(features, dict):
                raise AristonResponseError("Unexpected device features")
            self._features[plant_id] = features
        return self._features[plant_id]

    async def async_read_main(self, plant_id: str) -> dict[str, Any]:
        """Read status; refresh expired token at most once."""
        async with self._lock:
            if not self._token:
                await self.async_login()
            for attempt in range(2):
                try:
                    features = await self._load_features(plant_id)
                    result = await self._request(
                        "POST", f"/api/v2/remote/dataItems/{plant_id}/get?umsys=si",
                        json_body=make_main_request(features),
                    )
                    if not isinstance(result, dict):
                        raise AristonResponseError("Unexpected dataItems reply")
                    return result
                except AristonAuthError:
                    self._token = None
                    self._features.clear()
                    if attempt:
                        raise
                    await self.async_login()
            raise AristonAuthError("Token refresh failed")
