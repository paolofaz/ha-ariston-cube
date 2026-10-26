"""Fake-server contract tests for anti-CSRF R2 login and U6_9_2 writes."""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
PKG = "_ariston_cube_testpkg"
if PKG not in sys.modules:
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(ROOT)]
    sys.modules[PKG] = pkg
web = importlib.import_module(PKG + ".web_portal")


class Reply:
    def __init__(self, value, status=200):
        self.value = value
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def text(self):
        return self.value

    async def json(self, **_):
        return self.value


class CookieJar:
    def __init__(self):
        self.cookies = []

    def update_cookies(self, cookies, **_):
        self.cookies.append(cookies)


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.cookie_jar = CookieJar()

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


FORM = '<input type="hidden" name="__RequestVerificationToken" value="abc&amp;123">'
OPTIONS = [{"value": 0, "text": "Off"}, {"value": 1, "text": "Timed"},
           {"value": 2, "text": "Always"}]


def menu(value):
    return {"data": [{"id": "U6_9_2", "value": value, "dropDownOptions": OPTIONS}]}


def test_csrf_cookie_login_and_read_menu():
    session = Session(Reply(FORM), Reply({"ok": True}), Reply(menu(2)))
    client = web.AristonWebPortal(session, "user@example.invalid", "password")
    result = asyncio.run(client.async_read_comfort("GW123"))
    assert result["value"] == 2
    assert session.cookie_jar.cookies == [{
        "__formRequestVerificationToken": "abc&123"
    }]
    assert session.calls[1][2]["json"]["email"] == "user@example.invalid"
    assert session.calls[1][2]["json"]["password"] == "password"
    assert "Ajax-Request" in session.calls[1][2]["headers"]
    assert not any("ar.authToken" in kw.get("headers", {}) for _, _, kw in session.calls)
    assert session.calls[-1][1].endswith(
        "/R2/PlantMenu/Refresh?id=GW123&paramIds=U6_9_2"
    )


def test_one_write_only_from_known_value_then_readback():
    session = Session(
        Reply(FORM), Reply({"ok": True}),
        Reply(menu(0)), Reply({"ok": True}), Reply(menu(2)),
    )
    result = asyncio.run(
        web.AristonWebPortal(session, "user", "pwd").async_set_comfort("GW123", 2)
    )
    assert result == 2
    writes = [(url, options["json"]) for method, url, options in session.calls
              if "/PlantMenu/Submit/" in url]
    assert len(writes) == 1
    assert writes[0][1] == [{"id": "U6_9_2", "value": 2, "prevValue": 0}]


def test_no_write_if_timed_or_target_is_not_declared():
    for before in [menu(1), {"data": [{"id": "U6_9_2", "value": 0}]}]:
        session = Session(Reply(FORM), Reply({"ok": True}), Reply(before))
        with pytest.raises(web.WebPortalError):
            asyncio.run(
                web.AristonWebPortal(session, "user", "pwd")
                .async_set_comfort("GW123", 2)
            )
        assert not any("/PlantMenu/Submit/" in url for _, url, _ in session.calls)


def test_no_retry_after_write_response_error_or_mismatch():
    for response, after in [
        (Reply({"ok": False}), None),
        (Reply({"ok": True}), Reply(menu(0))),
    ]:
        responses = [Reply(FORM), Reply({"ok": True}), Reply(menu(0)), response]
        if after:
            responses.append(after)
        session = Session(*responses)
        with pytest.raises(web.WebPortalError):
            asyncio.run(
                web.AristonWebPortal(session, "user", "pwd")
                .async_set_comfort("GW123", 2)
            )
        assert sum("/PlantMenu/Submit/" in url for _, url, _ in session.calls) == 1


def test_login_failure_never_submits_anything():
    session = Session(Reply("<html>no token</html>"))
    with pytest.raises(web.WebPortalAuthError):
        asyncio.run(
            web.AristonWebPortal(session, "secret", "password")
            .async_set_comfort("GW123", 2)
        )
    assert not any("/PlantMenu/Submit/" in url for _, url, _ in session.calls)


def test_web_metering_reads_actual_as_physical_unit():
    report = {"data": {"asPhysicalUnit": {"histogramData": []}}}
    session = Session(
        Reply(FORM), Reply({"ok": True}),
        Reply({"data": {"zones": [{"id": 1}]}}), Reply(report),
    )
    result = asyncio.run(
        web.AristonWebPortal(session, "u", "p").async_read_metering("GW123")
    )
    assert "asPhysicalUnit" in result
    assert session.calls[-1][2]["json"] == {
        "features": {"zones": [{"id": 1}]}, "hasCooling": False
    }
    assert "/R2/PlantMetering/GetData/GW123" in session.calls[-1][1]



def test_login_form_follows_safe_redirect_chain():
    session = Session(Reply(FORM), Reply({"ok": True}), Reply(menu(0)))
    client = web.AristonWebPortal(session, "user", "pwd")
    assert asyncio.run(client.async_read_comfort("GW123"))["value"] == 0
    assert session.calls[0][2]["allow_redirects"] is True
    assert session.calls[0][2]["max_redirects"] == 5
    assert session.calls[1][2]["allow_redirects"] is False


def test_web_form_http_error_provides_status_and_no_secret():
    session = Session(Reply("not available", status=403))
    with pytest.raises(web.WebPortalAuthError, match="Web login form HTTP 403") as exc:
        asyncio.run(web.AristonWebPortal(session, "MY_USERNAME", "MY_PASSWORD")
                    .async_read_comfort("GW123"))
    assert "MY_USERNAME" not in str(exc.value)
    assert "MY_PASSWORD" not in str(exc.value)
    assert len(session.calls) == 1



def test_web_antiforgery_input_attribute_order_independent():
    reversed_form = '<input value="abc123" type="hidden" name="__RequestVerificationToken">'
    session = Session(Reply(reversed_form), Reply({"ok": True}), Reply(menu(0)))
    assert asyncio.run(
        web.AristonWebPortal(session, "u", "p").async_read_comfort("GW123")
    )["value"] == 0
    assert session.cookie_jar.cookies[0]["__formRequestVerificationToken"] == "abc123"



def test_browser_headers_for_login_page_and_xhr():
    session = Session(Reply(FORM), Reply({"ok": True}), Reply(menu(0)))
    portal = web.AristonWebPortal(session, "u", "p")
    assert asyncio.run(portal.async_read_comfort("GW123"))["value"] == 0
    page_headers = session.calls[0][2]["headers"]
    assert "Mozilla/" in page_headers["User-Agent"]
    assert "text/html" in page_headers["Accept"]
    assert "Ajax-Request" not in page_headers
    xhr_headers = session.calls[1][2]["headers"]
    assert "Mozilla/" in xhr_headers["User-Agent"]
    assert xhr_headers["Ajax-Request"] == "json"


def test_web_403_is_cooldown_not_repeated_auth_requests():
    session = Session(Reply("forbidden", status=403))
    portal = web.AristonWebPortal(session, "u", "p")
    for _ in range(3):
        with pytest.raises(web.WebPortalAuthError, match="HTTP 403"):
            asyncio.run(portal.async_read_comfort("GW123"))
    assert len(session.calls) == 1


def test_web_429_is_cooldown_not_repeated_auth_requests():
    session = Session(Reply("rate limited", status=429))
    portal = web.AristonWebPortal(session, "u", "p")
    for _ in range(2):
        with pytest.raises(web.WebPortalAuthError, match="HTTP 429"):
            asyncio.run(portal.async_read_metering("GW123"))
    assert len(session.calls) == 1
