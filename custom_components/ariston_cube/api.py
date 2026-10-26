"""Read-only async client for the legacy Ariston NET cloud API.

The login sequence intentionally matches the historical requests.Session
client: POST credentials, then GET the discovered gateways. No speculative
preflight GET, CSRF cookie manipulation or nonstandard request headers.
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



def _phase(method: str, path: str) -> str:
    """Never expose gateway IDs or credentials in diagnostics."""
    if path.startswith("/R2/Account/Login"):
        return "login_submit"
    if "/plants/lite" in path:
        return "plant_discovery"
    if "/features?" in path:
        return "features"
    if "/dataItems/" in path:
        return "data_read"
    return "cloud_request"


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
        phase = _phase(method, path)
        try:
            async with self._session.request(
                method, BASE_URL + path, json=json_body,
                timeout=aiohttp.ClientTimeout(total=25), allow_redirects=True,
            ) as response:
                if response.status in (401, 403):
                    raise AristonAuthError(
                        f"Ariston HTTP {response.status} at {phase}"
                    )
                if response.status in (408, 425, 429) or response.status >= 500:
                    raise AristonConnectionError(
                        f"Ariston HTTP {response.status} at {phase}"
                    )
                if response.status >= 400:
                    raise AristonResponseError(
                        f"Ariston HTTP {response.status} at {phase}"
                    )
                if expect_json and "/account/login" in response.url.path.lower():
                    raise AristonAuthError(f"Redirected to login at {phase}")
                if expect_json:
                    try:
                        return await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, json.JSONDecodeError, ValueError) as exc:
                        raise AristonResponseError(
                            f"Ariston returned non-JSON content at {phase}"
                        ) from exc
                return {"path": response.url.path, "body": await response.text()}
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise AristonConnectionError(
                f"Ariston {type(exc).__name__} at {phase}"
            ) from exc

    async def async_login(self) -> None:
        """POST login exactly as in the historically working cloud client."""
        reply = await self._request(
            "POST", "/R2/Account/Login?returnUrl=%2FR2%2FHome",
            json_body={
                "email": self._username,
                "password": self._password,
                "rememberMe": False,
                "language": "English_Us",
            },
            expect_json=False,
        )
        body = reply["body"].strip()
        if body.startswith("{"):
            try:
                result = json.loads(body)
            except json.JSONDecodeError as exc:
                raise AristonResponseError("Invalid JSON login reply") from exc
            if not isinstance(result, dict):
                raise AristonResponseError("Unexpected JSON login reply")
            if result.get("ok") is False or result.get("success") is False:
                raise AristonAuthError("Ariston rejected the login (ok=false)")
        elif "/account/login" in reply["path"].lower() and (
            "<html" in body.lower() or "<form" in body.lower()
        ):
            raise AristonAuthError("Ariston returned the login form")
        # Login is only fully validated by the subsequent plant discovery.
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
