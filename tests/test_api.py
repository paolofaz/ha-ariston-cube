"""Contract tests against fake aiohttp responses; no network, credentials or HA."""

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

    async def read(self):
        return b""

    async def text(self):
        return self.payload if isinstance(self.payload, str) else ""


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.cookie_jar = types.SimpleNamespace(update_cookies=lambda *_args, **_kwargs: None)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_authentication_and_read_contract():
    session = Session(
        Response(path="/R2/Account/Login"),  # preflight
        Response('{"ok":true}', path="/R2/Home"),  # login
        Response([{"gwId": "GW123", "name": "Cube"}]),  # plants
        Response({"zones": [{"num": 1}]}),  # features
        Response({"items": [{"id": "ZoneMeasuredTemp", "zone": 1, "value": 21}]}),
    )

    async def test():
        client = api.AristonClient(session, "test@example.invalid", "secret")
        assert (await client.async_list_plants())[0]["id"] == "GW123"
        result = await client.async_read_main("GW123")
        assert result["items"][0]["value"] == 21

    asyncio.run(test())
    assert session.calls[0][0] == "GET"
    assert session.calls[1][0] == "POST"
    assert session.calls[2][2]["headers"]["X-Requested-With"] == "XMLHttpRequest"
    body = session.calls[4][2]["json"]
    assert body["useCache"] is False
    assert {"id": "ZoneMeasuredTemp", "zn": 1} in body["items"]
    assert not any("/temperatures" in url for _, url, _ in session.calls)


def test_expired_session_reauthenticates_only_once():
    session = Session(
        Response(path="/R2/Account/Login"),  # preflight
        Response('{"ok":true}', path="/R2/Home"),  # login
        Response(status=401),  # features -> unauthorized
        Response(path="/R2/Account/Login"),  # preflight again
        Response('{"ok":true}', path="/R2/Home"),  # login again
        Response({"zones": [{"num": 1}]}),
        Response({"items": []}),
    )

    async def test():
        client = api.AristonClient(session, "test@example.invalid", "secret")
        assert await client.async_read_main("GW123") == {"items": []}

    asyncio.run(test())
    assert sum(method == "POST" and "/Account/Login" in url for method, url, _ in session.calls) == 2


def test_expired_session_login_redirect_raises_auth_error():
    session = Session(
        Response(path="/R2/Account/Login"),
        Response('{"ok":true}', path="/R2/Home"),
        Response(payload=None, path="/R2/Account/Login"),
        Response(path="/R2/Account/Login"),
        Response('{"ok":true}', path="/R2/Home"),
        Response(payload=None, path="/R2/Account/Login"),
    )

    async def test():
        client = api.AristonClient(session, "test@example.invalid", "secret")
        try:
            await client.async_read_main("GW123")
        except api.AristonAuthError:
            return
        assert False, "Expected auth error after retry"

    asyncio.run(test())


def test_denied_login_is_not_accepted():
    session = Session(
        Response(path="/R2/Account/Login"),
        Response('{"ok":false}', path="/R2/Account/Login"),
    )
    async def test():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_login()
        except api.AristonAuthError:
            return
        assert False, "Expected rejected login"
    asyncio.run(test())


def test_preflight_403_is_not_mislabeled_bad_password():
    session = Session(Response(status=403, path="/R2/Account/Login"))
    async def test():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_login()
        except api.AristonConnectionError as exc:
            assert "login_page" in str(exc)
            return
        assert False, "Expected cloud connection error"
    asyncio.run(test())
