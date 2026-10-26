"""Async Ariston mobile API client with manually triggered temperature controls.

Uses /api/v2/accounts/login and ar.authToken. Writes are explicit, validated,
single-shot operations with read-before-write and readback; no retry on POST.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp

from .const import BASE_URL
from .model import make_main_request, parse_main_data, as_temperature, parse_plants
from .commands import CommandRejected, build_setpoint_request, build_zone_mode_request, build_plant_control_request
from .states import enum_code

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
    if "/getConsumptionsSettings" in path:
        return "consumption_settings_read"
    if "/features?" in path:
        return "features"
    if "/dataItems/" in path:
        return "data_write" if "/set?" in path else "data_read"
    return "cloud_request"


class AristonClient:
    """Async cloud client with serialized reads and bounded explicit writes."""

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

    async def async_set_setpoint(
        self, plant_id: str, item_id: str, value: float,
        *, require_manual: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """Single validated write from a fresh reading, followed by verification.

        Unlike ordinary reads, never retry the write POST: a timeout may mean
        the boiler applied it despite the response being lost.
        """
        async with self._lock:
            if not self._token:
                await self.async_login()
            features = await self._load_features(plant_id)
            read_path = f"/api/v2/remote/dataItems/{plant_id}/get?umsys=si"
            fresh_payload = await self._request(
                "POST", read_path, json_body=make_main_request(features),
            )
            fresh = parse_main_data(fresh_payload)
            request = build_setpoint_request(
                fresh, features, item_id, value, require_manual=require_manual
            )
            if request is None:
                return fresh  # unchanged: no POST to the write endpoint

            response = await self._request(
                "POST", f"/api/v2/remote/dataItems/{plant_id}/set?umsys=si",
                json_body=request,
            )
            if isinstance(response, dict) and (
                response.get("success") is False or response.get("ok") is False
            ):
                raise AristonResponseError("Ariston rejected the data write")
            # Readback is a separate read request; it does not resend the command.
            after_payload = await self._request(
                "POST", read_path, json_body=make_main_request(features),
            )
            after = parse_main_data(after_payload)
            actual = as_temperature(after.get(item_id))
            if actual is None or abs(actual - float(value)) > 0.01:
                raise AristonResponseError(
                    "Command submitted but not yet confirmed by cloud; do not repeat immediately"
                )
            return after


    async def async_set_zone_mode(
        self, plant_id: str, mode: int,
    ) -> dict[str, dict[str, Any]]:
        """Select OFF/MANUAL/SCHEDULE without changing the global plant mode."""
        async with self._lock:
            if not self._token:
                await self.async_login()
            features = await self._load_features(plant_id)
            read_path = f"/api/v2/remote/dataItems/{plant_id}/get?umsys=si"
            fresh = parse_main_data(await self._request(
                "POST", read_path, json_body=make_main_request(features),
            ))
            request = build_zone_mode_request(fresh, features, mode)
            if request is None:
                return fresh
            response = await self._request(
                "POST", f"/api/v2/remote/dataItems/{plant_id}/set?umsys=si",
                json_body=request,
            )
            if isinstance(response, dict) and (
                response.get("success") is False or response.get("ok") is False
            ):
                raise AristonResponseError("Ariston refused zone mode")
            after = parse_main_data(await self._request(
                "POST", read_path, json_body=make_main_request(features),
            ))
            if enum_code(after.get("ZoneMode")) != mode:
                raise AristonResponseError(
                    "Mode sent but not yet confirmed; do not retry immediately"
                )
            return after


    async def async_diagnostic_reports(self, plant_id: str) -> dict[str, Any]:
        """On-demand read-only inspection; never log payload or identifiers."""
        paths = {
            "weekly_program": f"/api/v2/remote/timeProgs/{plant_id}/ChZn1?umsys=si",
            "energy_account": f"/api/v2/remote/reports/{plant_id}/energyAccount",
            "consumption_settings": (
                f"/api/v2/remote/plants/{plant_id}/getConsumptionsSettings"
            ),
            "consumption_sequences": (
                f"/api/v2/remote/reports/{plant_id}/consSequencesApi8"
                "?usages=Ch%2CDhw"
            ),
        }
        responses: dict[str, Any] = {}
        async with self._lock:
            if not self._token:
                await self.async_login()
            for kind, path in paths.items():
                try:
                    # Ariston's getConsumptionsSettings is a read-only POST {}.
                    # Do not generalize this exception to control endpoints.
                    if kind == "consumption_settings":
                        responses[kind] = await self._request(
                            "POST", path, json_body={}
                        )
                    else:
                        responses[kind] = await self._request("GET", path)
                except AristonError as exc:
                    responses[kind] = exc
        return responses


    async def async_set_plant_control(self, plant_id: str, item_id: str, value: int):
        """One explicit global control write and a separate verification read."""
        async with self._lock:
            if not self._token:
                await self.async_login()
            features = await self._load_features(plant_id)
            read_path = f"/api/v2/remote/dataItems/{plant_id}/get?umsys=si"
            fresh = parse_main_data(await self._request(
                "POST", read_path, json_body=make_main_request(features)))
            body = build_plant_control_request(fresh, features, item_id, value)
            if body is None:
                return fresh
            response = await self._request(
                "POST", f"/api/v2/remote/dataItems/{plant_id}/set?umsys=si",
                json_body=body)
            if isinstance(response, dict) and (
                response.get("success") is False or response.get("ok") is False
            ):
                raise AristonResponseError("Ariston refused plant control")
            after = parse_main_data(await self._request(
                "POST", read_path, json_body=make_main_request(features)))
            if enum_code(after.get(item_id)) != value:
                raise AristonResponseError(
                    "Plant command sent but unconfirmed: do not retry immediately")
            return after



    async def async_probe_dhw_comfort_menu(self, plant_id: str) -> Any:
        """Read U6_9_2 via the two legacy *read* endpoints, on demand only.

        This intentionally does not attempt the unverified login or make any
        write; an unavailable/unauthorized result proves no control support.
        """
        paths = (
            f"/R2/PlantMenu/Refresh?id={plant_id}&paramIds=U6_9_2",
            f"/Menu/User/Refresh/{plant_id}?paramIds=U6_9_2",
        )
        async with self._lock:
            if not self._token:
                await self.async_login()
            last_error: AristonError | None = None
            for path in paths:
                try:
                    return await self._request("GET", path)
                except AristonError as exc:
                    last_error = exc
            return last_error or AristonResponseError(
                "Comfort ACS menu endpoint unavailable"
            )

    async def async_read_weekly_program(self, plant_id: str) -> dict[str, Any]:
        """Read the existing Cube S schedule. Never issue a programme write."""
        async with self._lock:
            if not self._token:
                await self.async_login()
            path = f"/api/v2/remote/timeProgs/{plant_id}/ChZn1?umsys=si"
            for attempt in range(2):
                try:
                    result = await self._request("GET", path)
                    if not isinstance(result, dict):
                        raise AristonResponseError("Unsupported weekly programme response")
                    return result
                except AristonAuthError:
                    self._token = None
                    self._features.clear()
                    if attempt:
                        raise
                    await self.async_login()
            raise AristonAuthError("Weekly programme authentication failed")



    async def async_read_energy_account(self, plant_id: str) -> dict[str, Any]:
        """Read last-month gas totals; never request a write endpoint."""
        async with self._lock:
            if not self._token:
                await self.async_login()
            path = f"/api/v2/remote/reports/{plant_id}/energyAccount"
            for attempt in range(2):
                try:
                    result = await self._request("GET", path)
                    if not isinstance(result, dict):
                        raise AristonResponseError("Invalid energy account response")
                    return result
                except AristonAuthError:
                    self._token = None
                    self._features.clear()
                    if attempt:
                        raise
                    await self.async_login()
            raise AristonAuthError("Energy report authorization failed")



    async def async_read_gas_sequences(self, plant_id: str) -> list[dict[str, Any]]:
        """Fetch two-hour heating/DHW consumption via the existing reports API."""
        async with self._lock:
            if not self._token:
                await self.async_login()
            path = (
                f"/api/v2/remote/reports/{plant_id}/consSequencesApi8"
                "?usages=Ch%2CDhw&hasSlp=False"
            )
            for attempt in range(2):
                try:
                    result = await self._request("GET", path)
                    if not isinstance(result, list):
                        raise AristonResponseError("Unexpected consumption-series response")
                    return result
                except AristonAuthError:
                    self._token = None
                    self._features.clear()
                    if attempt:
                        raise
                    await self.async_login()
            raise AristonAuthError("Consumption report authentication failed")
