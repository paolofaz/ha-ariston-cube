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



def _readback_items(comfort=21.5, dhw=50):
    return {"items": [
        {"id": "PlantMode", "zone": 0, "value": 1},
        {"id": "ZoneMode", "zone": 1, "value": 2},
        {"id": "ZoneComfortTemp", "zone": 1, "value": comfort,
         "min": 10, "max": 30, "step": 0.5},
        {"id": "DhwTemp", "zone": 0, "value": dhw,
         "min": 35, "max": 65, "step": 1},
    ]}


def test_live_setpoint_single_post_and_readback():
    session = Session(
        Response({"token": "TEST_TOKEN"}),
        Response({"zones": [{"num": 1}]}),
        Response(_readback_items(comfort=21, dhw=49)),
        Response(None),  # successful empty-body write response
        Response(_readback_items(comfort=21.5, dhw=49)),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        result = await client.async_set_setpoint("GW123", "ZoneComfortTemp", 21.5)
        assert result["ZoneComfortTemp"]["value"] == 21.5
    run(scenario())
    writes = [(url, opts["json"]) for method, url, opts in session.calls
              if "/dataItems/" in url and "/set?" in url]
    assert len(writes) == 1
    assert writes[0][1]["items"][0] == {
        "id": "ZoneComfortTemp", "zone": 1, "prevValue": 21.0, "value": 21.5
    }


def test_write_rejected_in_program_mode_before_any_set_post():
    readings = _readback_items()
    for item in readings["items"]:
        if item["id"] == "ZoneMode":
            item["value"] = 3
    session = Session(
        Response({"token": "TEST_TOKEN"}),
        Response({"zones": [{"num": 1}]}),
        Response(readings),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_set_setpoint("GW123", "ZoneComfortTemp", 22)
        except api.CommandRejected:
            return
        assert False, "Expected no write in time-program mode"
    run(scenario())
    assert not any("/set?" in url for _, url, _ in session.calls)


def test_no_duplicate_post_when_unchanged():
    session = Session(
        Response({"token": "TEST_TOKEN"}),
        Response({"zones": [{"num": 1}]}),
        Response(_readback_items(comfort=21.5, dhw=49)),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        result = await client.async_set_setpoint("GW123", "DhwTemp", 49)
        assert result["DhwTemp"]["value"] == 49
    run(scenario())
    assert not any("/set?" in url for _, url, _ in session.calls)


def test_write_not_retried_after_timeout_http_error():
    session = Session(
        Response({"token": "TEST_TOKEN"}),
        Response({"zones": [{"num": 1}]}),
        Response(_readback_items(comfort=21.5, dhw=49)),
        Response(status=503),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_set_setpoint("GW123", "DhwTemp", 50)
        except api.AristonConnectionError:
            return
        assert False, "Expected write service error"
    run(scenario())
    assert sum("/set?" in url for _, url, _ in session.calls) == 1


def test_write_accepted_but_readback_mismatch_is_not_retried():
    session = Session(
        Response({"token": "TEST_TOKEN"}),
        Response({"zones": [{"num": 1}]}),
        Response(_readback_items(comfort=21.5, dhw=49)),
        Response(None),
        Response(_readback_items(comfort=21.5, dhw=49)),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_set_setpoint("GW123", "DhwTemp", 50)
        except api.AristonResponseError as exc:
            assert "not yet confirmed" in str(exc)
            return
        assert False, "Expected non-confirmation warning"
    run(scenario())
    assert sum("/set?" in url for _, url, _ in session.calls) == 1
