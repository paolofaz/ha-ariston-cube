"""Offline contract tests for the shared mobile / web Ariston HTTP 429 backoff."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import importlib
from pathlib import Path
import sys
import types

import pytest
from yarl import URL


ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PACKAGE = "_ariston_cube_testpkg"
if PACKAGE not in sys.modules:
    pkg = types.ModuleType(PACKAGE)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PACKAGE] = pkg

limiting = importlib.import_module(PACKAGE + ".rate_limit")
api = importlib.import_module(PACKAGE + ".api")
web = importlib.import_module(PACKAGE + ".web_portal")


class Reply:
    def __init__(self, value=None, *, status=200, headers=None, path="/R2/Account/Login"):
        self.value = value
        self.status = status
        self.headers = headers or {}
        self.url = URL(api.BASE_URL + path)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def json(self, **_kwargs):
        return self.value

    async def text(self):
        return self.value


class CookieJar:
    def update_cookies(self, *_args, **_kwargs):
        pass


class Session:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.cookie_jar = CookieJar()

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.replies.pop(0)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def test_backoff_5_10_20_40_60_and_cap():
    t = [100.0]
    limit = limiting.RateLimitBackoff(clock=lambda: t[0])
    for expected in (300, 600, 1200, 2400, 3600, 3600):
        limit.record_429()
        assert limit.remaining_seconds() == expected
        with pytest.raises(limiting.RateLimitActive):
            limit.check()
        t[0] += expected
        limit.check()  # Cooldown expired; an ordinary scheduled poll may try.
    # Repeated 429 responses escalate until a successful response occurs.
    limit.record_success()
    limit.record_429()
    assert limit.remaining_seconds() == 300


def test_retry_after_delay_and_date_are_respected():
    t = [100.0]
    limit = limiting.RateLimitBackoff(clock=lambda: t[0])
    limit.record_429({"Retry-After": "1800"})
    assert limit.remaining_seconds() == 1800
    t[0] += 1800
    date = format_datetime(datetime.now(timezone.utc) + timedelta(hours=2), usegmt=True)
    limit.record_429({"retry-after": date})
    assert 7190 < limit.remaining_seconds() <= 7201


def test_invalid_retry_after_uses_local_policy():
    limit = limiting.RateLimitBackoff(clock=lambda: 0.0)
    limit.record_429({"Retry-After": "invalid-date"})
    assert limit.remaining_seconds() == 300


def test_success_in_flight_cannot_cancel_active_cooldown():
    t = [0.0]
    limit = limiting.RateLimitBackoff(clock=lambda: t[0])
    limit.record_429()
    limit.record_success()
    assert limit.remaining_seconds() == 300
    t[0] = 300.0
    limit.record_429()
    assert limit.remaining_seconds() == 600


def test_mobile_429_blocks_mobile_and_web_without_new_network_requests():
    mobile = Session(
        Reply(status=429, headers={"Retry-After": "600"}, path="/api/v2/accounts/login"),
        Reply({"token": "ok"}, path="/api/v2/accounts/login"),
    )
    web_session = Session()
    client = api.AristonClient(mobile, "u", "p", web_session=web_session)
    t = [10.0]
    client.rate_limit._clock = lambda: t[0]
    with pytest.raises(api.AristonConnectionError, match="429 at mobile_login"):
        asyncio.run(client.async_login())
    assert len(mobile.calls) == 1
    assert client.rate_limit.remaining_seconds() == 600
    with pytest.raises(api.AristonConnectionError, match="429 cooldown"):
        asyncio.run(client.async_login())
    with pytest.raises(web.WebPortalAuthError, match="429"):
        asyncio.run(client.web_portal.async_read_comfort("GW123"))
    assert len(mobile.calls) == 1
    assert len(web_session.calls) == 0
    t[0] += 600
    asyncio.run(client.async_login())
    assert client.rate_limit.remaining_seconds() == 0
    assert len(mobile.calls) == 2


def test_web_login_429_blocks_mobile_login_as_well():
    mobile = Session()
    web_session = Session(Reply("limit", status=429))
    client = api.AristonClient(mobile, "u", "p", web_session=web_session)
    with pytest.raises(web.WebPortalAuthError, match="429"):
        asyncio.run(client.web_portal.async_read_metering("GW123"))
    with pytest.raises(api.AristonConnectionError, match="429 cooldown"):
        asyncio.run(client.async_login())
    assert len(web_session.calls) == 1
    assert mobile.calls == []


def test_web_data_429_blocks_mobile_and_additional_web_requests():
    mobile = Session()
    web_session = Session(Reply(status=429, headers={"Retry-After": "900"}))
    client = api.AristonClient(mobile, "u", "p", web_session=web_session)
    client.web_portal._logged_in = True
    with pytest.raises(web.WebPortalError, match="HTTP 429"):
        asyncio.run(client.web_portal.async_read_comfort("GW123"))
    assert client.rate_limit.remaining_seconds() > 800
    with pytest.raises(web.WebPortalAuthError, match="HTTP 429"):
        asyncio.run(client.web_portal.async_read_comfort("GW123"))
    with pytest.raises(api.AristonConnectionError, match="429 cooldown"):
        asyncio.run(client.async_login())
    assert len(web_session.calls) == 1
    assert mobile.calls == []


def test_r2_login_post_429_triggers_shared_cooldown():
    form = '<input type="hidden" name="__RequestVerificationToken" value="abc">'
    web_session = Session(Reply(form), Reply(status=429))
    mobile = Session()
    client = api.AristonClient(mobile, "u", "p", web_session=web_session)
    with pytest.raises(web.WebPortalAuthError, match="POST HTTP 429"):
        asyncio.run(client.web_portal.async_read_comfort("GW123"))
    assert len(web_session.calls) == 2
    with pytest.raises(api.AristonConnectionError, match="429 cooldown"):
        asyncio.run(client.async_login())
    assert mobile.calls == []


def test_429_on_command_post_is_not_retried_or_queued():
    session = Session(Reply(status=429, path="/api/v2/remote/dataItems/GW123/set"))
    client = api.AristonClient(session, "u", "p")
    client._token = "TEST_TOKEN"
    async def write_once():
        await client._request(
            "POST", "/api/v2/remote/dataItems/GW123/set?umsys=si",
            json_body={"items": []},
        )
    with pytest.raises(api.AristonConnectionError, match="HTTP 429"):
        asyncio.run(write_once())
    with pytest.raises(api.AristonConnectionError, match="429 cooldown"):
        asyncio.run(write_once())
    assert [method for method, *_ in session.calls] == ["POST"]


def test_other_temporary_errors_do_not_trigger_429_backoff():
    session = Session(
        Reply(status=503, path="/api/v2/accounts/login"),
        Reply({"token": "ok"}, path="/api/v2/accounts/login"),
    )
    client = api.AristonClient(session, "u", "p")
    with pytest.raises(api.AristonConnectionError, match="503"):
        asyncio.run(client.async_login())
    assert client.rate_limit.remaining_seconds() == 0
    asyncio.run(client.async_login())
    assert len(session.calls) == 2
