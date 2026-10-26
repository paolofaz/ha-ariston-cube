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


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_authentication_and_read_contract():
    session = Session(
        Response(),  # login
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
    assert session.calls[0][0] == "POST"
    assert "/R2/Account/Login" in session.calls[0][1]
    body = session.calls[3][2]["json"]
    assert body["useCache"] is False
    assert {"id": "ZoneMeasuredTemp", "zn": 1} in body["items"]
    assert not any("/temperatures" in url for _, url, _ in session.calls)


def test_expired_session_reauthenticates_only_once():
    session = Session(
        Response(),  # login
        Response(status=401),  # features -> unauthorized
        Response(),  # login again
        Response({"zones": [{"num": 1}]}),
        Response({"items": []}),
    )

    async def test():
        client = api.AristonClient(session, "test@example.invalid", "secret")
        assert await client.async_read_main("GW123") == {"items": []}

    asyncio.run(test())
    assert sum("/Account/Login" in url for _, url, _ in session.calls) == 2


def test_expired_session_login_redirect_raises_auth_error():
    session = Session(
        Response(),
        Response(payload=None, path="/R2/Account/Login"),
        Response(),
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
