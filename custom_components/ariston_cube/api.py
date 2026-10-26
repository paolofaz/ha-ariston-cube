"""Minimal async client for the legacy Ariston NET cloud API.

Read-only: there are no endpoints for changing boiler settings here.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .const import BASE_URL
from .model import make_main_request, parse_plants


class AristonError(Exception):
    """Base class for expected API failures."""


class AristonAuthError(AristonError):
    """Credentials rejected or session expired."""


class AristonConnectionError(AristonError):
    """Cloud network or HTTP availability problem."""


class AristonResponseError(AristonError):
    """Cloud returned an unsupported response."""


class AristonClient:
    """Authenticated, cookie-backed async reader for one Ariston account."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._authenticated = False
        self._features: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        try:
            async with self._session.request(
                method, BASE_URL + path, json=json_body,
                timeout=aiohttp.ClientTimeout(total=25), allow_redirects=True,
            ) as response:
                if response.status in (401, 403):
                    raise AristonAuthError("Ariston rejected the session")
                if response.status >= 400:
                    raise AristonConnectionError(f"Ariston returned HTTP {response.status}")
                if expect_json:
                    # An expired session can redirect to the HTML login page.
                    if "/Account/Login" in response.url.path:
                        raise AristonAuthError("Ariston session expired")
                    try:
                        return await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, json.JSONDecodeError, ValueError) as exc:
                        raise AristonResponseError("Ariston did not return JSON") from exc
                await response.read()
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise AristonConnectionError("Ariston network request failed") from exc

    async def async_login(self) -> None:
        """Authenticate, then validate via a separate plants request."""
        await self._request(
            "POST", "/R2/Account/Login?returnUrl=%2FR2%2FHome",
            json_body={
                "email": self._username,
                "password": self._password,
                "rememberMe": False,
                "language": "English_Us",
            },
            expect_json=False,
        )
        self._authenticated = True

    async def async_list_plants(self) -> list[dict[str, str]]:
        """Fetch account plant IDs; an empty list is not a login failure."""
        if not self._authenticated:
            await self.async_login()
        try:
            result = await self._request("GET", "/api/v2/remote/plants/lite")
            return parse_plants(result)
        except ValueError as exc:
            raise AristonResponseError("Invalid plants payload") from exc

    async def _ensure_login(self) -> None:
        if not self._authenticated:
            await self.async_login()

    async def _load_features(self, plant_id: str) -> dict[str, Any]:
        if plant_id not in self._features:
            features = await self._request(
                "GET", f"/api/v2/remote/plants/{plant_id}/features?eagerMode=True"
            )
            if not isinstance(features, dict):
                raise AristonResponseError("Invalid device features")
            self._features[plant_id] = features
        return self._features[plant_id]

    async def async_read_main(self, plant_id: str) -> dict[str, Any]:
        """Read the selected plant, retrying authentication once if necessary."""
        async with self._lock:
            await self._ensure_login()
            for attempt in range(2):
                try:
                    features = await self._load_features(plant_id)
                    return await self._request(
                        "POST", f"/api/v2/remote/dataItems/{plant_id}/get?umsys=si",
                        json_body=make_main_request(features),
                    )
                except AristonAuthError:
                    self._authenticated = False
                    self._features.clear()
                    if attempt:
                        raise
                    await self.async_login()
            raise AristonAuthError("Unable to authenticate")
