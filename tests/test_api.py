"""Offline tests for the read-only Ariston mobile API client."""

import asyncio
import importlib
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PACKAGE = "_ariston_cube_testpkg"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = package
api = importlib.import_module(f"{PACKAGE}.api")


class Response:
    def __init__(self, payload=None, status=200, path="/api/v2/remote/dataItems"):
        self.payload = payload
        self.status = status
        self.url = types.SimpleNamespace(path=path)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def json(self, **_kwargs):
        return self.payload


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def run(coro):
    return asyncio.run(coro)


def test_mobile_login_then_plant_discovery_then_read():
    session = Session(
        Response({"token": "TEST_TOKEN"}, path="/api/v2/accounts/login"),
        Response([{"gwId": "GW123", "name": "Cube"}]),
        Response({"zones": [{"num": 1}]}),
        Response({"items": [{"id": "ZoneMeasuredTemp", "zone": 1, "value": 20.5}]}),
    )
    async def scenario():
        client = api.AristonClient(session, "user@example.invalid", "secret")
        assert (await client.async_list_plants())[0]["id"] == "GW123"
        assert (await client.async_read_main("GW123"))["items"][0]["value"] == 20.5
    run(scenario())
    method, url, opts = session.calls[0]
    assert method == "POST" and url.endswith("/api/v2/accounts/login")
    assert opts["json"] == {"usr": "user@example.invalid", "pwd": "secret"}
    assert opts["headers"]["User-Agent"] == api.MOBILE_USER_AGENT
    assert opts["headers"]["ar.authToken"] == ""
    method, url, opts = session.calls[1]
    assert method == "GET" and url.endswith("/api/v2/remote/plants/lite")
    assert opts["headers"]["ar.authToken"] == "TEST_TOKEN"
    method, url, opts = session.calls[3]
    assert method == "POST" and "/dataItems/GW123/get?" in url
    assert opts["headers"]["ar.authToken"] == "TEST_TOKEN"
    assert {"id": "ZoneMeasuredTemp", "zn": 1} in opts["json"]["items"]
    assert all("/R2/Account/Login" not in url for _, url, _ in session.calls)


def test_login_403_produces_mobile_login_stage():
    session = Session(Response(status=403, path="/api/v2/accounts/login"))
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_login()
        except api.AristonAuthError as exc:
            assert "HTTP 403 at mobile_login" in str(exc)
            return
        assert False, "Expected authentication failure"
    run(scenario())


def test_no_token_is_response_error():
    session = Session(Response({"unexpected": "response"}))
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_login()
        except api.AristonResponseError as exc:
            assert "without token" in str(exc)
            return
        assert False, "Expected API schema failure"
    run(scenario())


def test_relogin_once_on_expired_token_405():
    session = Session(
        Response({"token": "first"}),
        Response(status=405),  # first features query
        Response({"token": "renewed"}),
        Response({"zones": [{"num": 1}]}),
        Response({"items": []}),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        assert await client.async_read_main("GW123") == {"items": []}
    run(scenario())
    login_calls = [(method, opts) for method, url, opts in session.calls
                   if url.endswith("/api/v2/accounts/login")]
    assert len(login_calls) == 2
    assert session.calls[-1][2]["headers"]["ar.authToken"] == "renewed"


def test_throttle_is_connection_error():
    session = Session(Response(status=429, path="/api/v2/accounts/login"))
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_login()
        except api.AristonConnectionError as exc:
            assert "429 at mobile_login" in str(exc)
            return
        assert False, "Expected rate limit"
    run(scenario())


def test_expired_session_redirect_detected():
    session = Session(Response({"token": "discard"}, path="/R2/Account/Login"))
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_login()
        except api.AristonAuthError as exc:
            assert "web login" in str(exc)
            return
        assert False, "Expected redirect rejection"
    run(scenario())


def test_explicit_rejected_login():
    session = Session(Response({"ok": False}, path="/api/v2/accounts/login"))
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_login()
        except api.AristonAuthError as exc:
            assert "rejected" in str(exc)
            return
        assert False, "Expected rejected login"
    run(scenario())
