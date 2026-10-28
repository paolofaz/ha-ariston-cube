"""Offline tests for the read-only Ariston mobile API client."""

import asyncio
import pytest
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
    def __init__(self, payload=None, status=200, path="/api/v2/remote/dataItems", headers=None):
        self.payload = payload
        self.status = status
        self.url = types.SimpleNamespace(path=path)
        self.headers = headers or {}

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
            await client.async_set_setpoint("GW123", "ZoneComfortTemp", 22, require_manual=True)
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



def _mode_items(zone_mode=2, options=None, plant=1):
    return {"items": [
        {"id": "PlantMode", "zone": 0, "value": plant},
        {"id": "ZoneMode", "zone": 1, "value": zone_mode,
         "options": [0, 2, 3] if options is None else options},
        {"id": "ZoneMeasuredTemp", "zone": 1, "value": 20},
    ]}


def test_mode_auto_uses_zone_only_once_and_readback():
    session = Session(
        Response({"token": "x"}),
        Response({"zones": [{"num": 1}]}),
        Response(_mode_items(zone_mode=2)),
        Response(None),
        Response(_mode_items(zone_mode=3)),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        result = await client.async_set_zone_mode("GW123", 3)
        assert result["ZoneMode"]["value"] == 3
    run(scenario())
    writes = [(url, opts["json"]) for method, url, opts in session.calls
              if "/dataItems/" in url and "/set?" in url]
    assert len(writes) == 1
    assert writes[0][1]["items"] == [
        {"id": "ZoneMode", "zone": 1, "prevValue": 2, "value": 3}
    ]


def test_mode_no_unsupported_transition_when_options_absent():
    session = Session(
        Response({"token": "x"}),
        Response({"zones": [{"num": 1}]}),
        Response({"items": [
            {"id": "PlantMode", "zone": 0, "value": 1},
            {"id": "ZoneMode", "zone": 1, "value": 2},
        ]}),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_set_zone_mode("GW123", 3)
        except api.CommandRejected:
            return
        assert False, "Expected fail-closed for absent mode options"
    run(scenario())
    assert not any("/set?" in url for _, url, _ in session.calls)


def test_comfort_preset_can_change_in_auto_without_overriding_zone_mode():
    readings = _readback_items(comfort=21.0)
    for item in readings["items"]:
        if item["id"] == "ZoneMode":
            item["value"] = 3
    after = _readback_items(comfort=21.5)
    for item in after["items"]:
        if item["id"] == "ZoneMode":
            item["value"] = 3
    session = Session(
        Response({"token": "TEST_TOKEN"}),
        Response({"zones": [{"num": 1}]}),
        Response(readings),
        Response(None),
        Response(after),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        result = await client.async_set_setpoint("GW123", "ZoneComfortTemp", 21.5)
        assert result["ZoneComfortTemp"]["value"] == 21.5
        assert result["ZoneMode"]["value"] == 3

    run(scenario())
    writes = [opts["json"] for _, url, opts in session.calls if "/set?" in url]
    assert len(writes) == 1
    assert writes[0]["items"][0]["id"] == "ZoneComfortTemp"



def _plant_control_items(mode=1, thermoreg=0):
    return {"items": [
        {"id": "PlantMode", "zone": 0, "value": mode, "options": [0, 1, 5]},
        {"id": "AutomaticThermoregulation", "zone": 0, "value": thermoreg},
    ]}


def test_plant_mode_write_once_and_readback():
    session = Session(
        Response({"token": "token"}),
        Response({"zones": [{"num": 1}]}),
        Response(_plant_control_items(mode=1)),
        Response(None),
        Response(_plant_control_items(mode=0)),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        updated = await client.async_set_plant_control("GW123", "PlantMode", 0)
        assert updated["PlantMode"]["value"] == 0
    run(scenario())
    writes = [opts["json"] for _, url, opts in session.calls if "/set?" in url]
    assert len(writes) == 1
    assert writes[0]["items"] == [{
        "id": "PlantMode", "zone": 0, "prevValue": 1, "value": 0
    }]


def test_thermoregulation_has_single_post_and_does_not_touch_zone():
    session = Session(
        Response({"token": "token"}),
        Response({"zones": [{"num": 1}]}),
        Response(_plant_control_items(thermoreg=0)),
        Response(None),
        Response(_plant_control_items(thermoreg=1)),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        result = await client.async_set_plant_control(
            "GW123", "AutomaticThermoregulation", 1
        )
        assert result["AutomaticThermoregulation"]["value"] == 1
    run(scenario())
    writes = [opts["json"] for _, url, opts in session.calls if "/set?" in url]
    assert len(writes) == 1
    assert writes[0]["items"][0]["id"] == "AutomaticThermoregulation"
    assert "ZoneMode" not in repr(writes[0])


def test_plant_write_readback_failure_is_not_retried():
    session = Session(
        Response({"token": "token"}),
        Response({"zones": [{"num": 1}]}),
        Response(_plant_control_items(mode=1)),
        Response(None),
        Response(_plant_control_items(mode=1)),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_set_plant_control("GW123", "PlantMode", 0)
        except api.AristonResponseError as exc:
            assert "unconfirmed" in str(exc)
            return
        assert False, "Expected unconfirmed write"
    run(scenario())
    assert sum("/set?" in url for _, url, _ in session.calls) == 1


def test_no_write_when_plant_options_missing():
    values = _plant_control_items(mode=1)
    del values["items"][0]["options"]
    session = Session(
        Response({"token": "token"}),
        Response({"zones": [{"num": 1}]}),
        Response(values),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        try:
            await client.async_set_plant_control("GW123", "PlantMode", 5)
        except api.CommandRejected:
            return
        assert False, "Missing modes must fail closed"
    run(scenario())
    assert not any("/set?" in url for _, url, _ in session.calls)



def test_weekly_program_is_get_only():
    weekly = {"ChZn1": {"plans": [{"days": [1], "slices": [
        {"from": 600, "temp": 1},
    ]}]}}
    session = Session(
        Response({"token": "example"}, path="/api/v2/accounts/login"),
        Response(weekly, path="/api/v2/remote/timeProgs"),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        assert await client.async_read_weekly_program("GW123") == weekly
    run(scenario())
    requests = [(method, url) for method, url, _ in session.calls]
    assert requests[-1] == (
        "GET",
        "https://www.ariston-net.remotethermo.com/api/v2/remote/timeProgs/GW123/ChZn1?umsys=si",
    )
    assert not any("/set?" in url for _, url in requests)


def test_weekly_read_reauthenticates_once_after_unauthorized_get():
    weekly = {"ChZn1": {"plans": []}}
    session = Session(
        Response({"token": "first"}, path="/api/v2/accounts/login"),
        Response(status=401),
        Response({"token": "second"}, path="/api/v2/accounts/login"),
        Response(weekly),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        assert await client.async_read_weekly_program("GW123") == weekly
    run(scenario())
    assert sum("/accounts/login" in url for _, url, _ in session.calls) == 2
    assert sum("/timeProgs/" in url for _, url, _ in session.calls) == 2



def test_last_month_energy_account_get_only():
    response = {"LastMonth": [{"gas": 123}, {"gas": 42}]}
    session = Session(
        Response({"token": "token"}),
        Response(response),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        assert await client.async_read_energy_account("GW123") == response
    run(scenario())
    assert session.calls[-1][0] == "GET"
    assert session.calls[-1][1].endswith("/reports/GW123/energyAccount")
    assert not any("/set?" in url for _, url, _ in session.calls)



def test_recent_gas_uses_cloud_two_hour_report_once():
    raw = [{"p": 1, "k": 7, "v": [0.0] * 24},
           {"p": 1, "k": 10, "v": [0.0] * 24}]
    session = Session(
        Response({"token": "token"}),
        Response(raw),
    )
    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        assert await client.async_read_gas_sequences("GW123") == raw
    run(scenario())
    reads = [(method, url) for method, url, opts in session.calls
             if "/consSequencesApi8" in url]
    assert len(reads) == 1
    assert reads[0][0] == "GET"
    assert reads[0][1].endswith(
        "/reports/GW123/consSequencesApi8?usages=Ch%2CDhw&hasSlp=False"
    )


def test_weekly_options_probe_is_read_only_and_exposes_no_credentials():
    session = Session(
        Response({"token": "TEST_TOKEN"}, path="/api/v2/accounts/login"),
        Response(status=204, headers={
            "Allow": "GET, OPTIONS, POST",
            "Set-Cookie": "PRIVATE_SECRET",
        }),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        result = await client.async_probe_weekly_methods("GW123")
        assert result["http_status"] == 204
        assert result["declared_methods"] == ["GET", "OPTIONS", "POST"]
        assert result["conclusive"] is False
        assert "PRIVATE_SECRET" not in repr(result)

    run(scenario())
    assert [method for method, _, _ in session.calls] == ["POST", "OPTIONS"]
    assert session.calls[1][1].endswith(
        "/timeProgs/GW123/ChZn1?umsys=si"
    )
    assert "json" not in session.calls[1][2]


def test_weekly_options_probe_405_is_not_assumed_to_support_writes():
    session = Session(
        Response({"token": "TEST_TOKEN"}),
        Response(status=405),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "secret")
        result = await client.async_probe_weekly_methods("GW123")
        assert result["http_status"] == 405
        assert result["declared_methods"] == []
        assert result["conclusive"] is False

    run(scenario())
    assert session.calls[1][0] == "OPTIONS"


def _weekly_write_fixture():
    return {"ChZn1": {"plans": [
        {"days": [0, 6], "slices": [
            {"from": 0, "temp": 0}, {"from": 420, "temp": 1},
            {"from": 1080, "temp": 0},
        ]},
        {"days": [1, 2, 3, 4, 5], "slices": [
            {"from": 0, "temp": 0}, {"from": 345, "temp": 1},
            {"from": 1290, "temp": 0},
        ]},
    ]}}


def test_weekly_experiment_sends_one_post_and_verifies_full_week():
    from _ariston_cube_testpkg.weekly_preview import weekly_read_fingerprint
    from _ariston_cube_testpkg.weekly_write import build_test_write
    source = _weekly_write_fixture()
    fingerprint = weekly_read_fingerprint(source)
    body, _, _ = build_test_write(source, 1, "05:45", "06:00", fingerprint)
    session = Session(
        Response({"token": "TOKEN"}),
        Response(source),
        Response(None),
        Response({"ChZn1": {"plans": body["plans"]}}),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        return await client.async_test_write_weekly_slice(
            "GW123", 1, "05:45", "06:00", fingerprint
        )

    result = run(scenario())
    assert result["status"] == "confirmed_by_fresh_cloud_read"
    assert [method for method, _, _ in session.calls] == [
        "POST", "GET", "POST", "GET"
    ]
    assert session.calls[2][2]["json"] == body
    assert all("/timeProgs/" in url for _, url, _ in session.calls[1:])


def test_weekly_experiment_stale_fingerprint_never_posts():
    session = Session(
        Response({"token": "TOKEN"}),
        Response(_weekly_write_fixture()),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        try:
            await client.async_test_write_weekly_slice(
                "GW123", 1, "05:45", "06:00", "0" * 64
            )
        except api.CommandRejected:
            return
        assert False, "Stale preview must abort"

    run(scenario())
    assert [method for method, _, _ in session.calls] == ["POST", "GET"]


def test_weekly_experiment_post_rejection_never_retries():
    from _ariston_cube_testpkg.weekly_preview import weekly_read_fingerprint
    raw = _weekly_write_fixture()
    session = Session(
        Response({"token": "TOKEN"}),
        Response(raw),
        Response(status=400),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        try:
            await client.async_test_write_weekly_slice(
                "GW123", 1, "05:45", "06:00",
                weekly_read_fingerprint(raw)
            )
        except api.AristonResponseError as exc:
            assert "HTTP 400" in str(exc)
            return
        assert False, "HTTP 400 must be reported"

    run(scenario())
    assert [method for method, _, _ in session.calls] == [
        "POST", "GET", "POST"
    ]


def test_weekly_experiment_unconfirmed_write_never_retries():
    from _ariston_cube_testpkg.weekly_preview import weekly_read_fingerprint
    raw = _weekly_write_fixture()
    session = Session(
        Response({"token": "TOKEN"}),
        Response(raw),
        Response(None),
        Response(raw),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        try:
            await client.async_test_write_weekly_slice(
                "GW123", 1, "05:45", "06:00",
                weekly_read_fingerprint(raw)
            )
        except api.AristonResponseError as exc:
            assert "NOT CONFIRMED" in str(exc)
            return
        assert False, "Expected readback failure"

    run(scenario())
    assert [method for method, _, _ in session.calls] == [
        "POST", "GET", "POST", "GET"
    ]


@pytest.mark.parametrize("operation,parameters", [
    ("add", {"to_time": "12:00", "preset": "Economy"}),
    ("remove", {"from_time": "05:45"}),
])
def test_cube_s_add_remove_writes_exactly_once_and_reads_back_every_day(
        operation, parameters):
    from _ariston_cube_testpkg.weekly_preview import weekly_read_fingerprint
    from _ariston_cube_testpkg.weekly_changes import build_weekly_change
    raw = _weekly_write_fixture()
    # A real Cube S GET has additional zone metadata. The successful rc.3
    # moving-boundary write sends only {"plans": ...} in its POST.
    raw["ChZn1"]["live_zone_metadata"] = {"opaque_revision": 7}
    fingerprint = weekly_read_fingerprint(raw)
    body, _, _ = build_weekly_change(
        raw, 1, operation, expected_fingerprint=fingerprint, **parameters
    )
    session = Session(
        Response({"token": "TOKEN"}),
        Response(raw),
        Response(None),
        Response({"ChZn1": {"plans": body["plans"]}}),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        return await client.async_write_weekly_change(
            "GW123", 1, operation,
            expected_fingerprint=fingerprint, **parameters
        )

    result = run(scenario())
    assert result["status"] == "confirmed_by_fresh_cloud_read"
    assert result["operation"] == operation
    assert [method for method, _, _ in session.calls] == [
        "POST", "GET", "POST", "GET",
    ]
    assert session.calls[2][2]["json"] == body
    assert sum(method == "POST" and "/timeProgs/" in url
               for method, url, _ in session.calls) == 1


def test_cube_s_add_remove_rejects_stale_fingerprint_without_post():
    session = Session(
        Response({"token": "TOKEN"}),
        Response(_weekly_write_fixture()),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        with pytest.raises(api.CommandRejected, match="changed since preview"):
            await client.async_write_weekly_change(
                "GW123", 1, "add", to_time="12:00",
                preset="Economy", expected_fingerprint="0" * 64
            )

    run(scenario())
    assert [method for method, _, _ in session.calls] == ["POST", "GET"]


def test_cube_s_add_remove_post_failure_does_not_retry():
    from _ariston_cube_testpkg.weekly_preview import weekly_read_fingerprint
    raw = _weekly_write_fixture()
    session = Session(
        Response({"token": "TOKEN"}),
        Response(raw),
        Response(status=400),
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        with pytest.raises(api.AristonError):
            await client.async_write_weekly_change(
                "GW123", 1, "remove", from_time="05:45",
                expected_fingerprint=weekly_read_fingerprint(raw),
            )

    run(scenario())
    assert [method for method, _, _ in session.calls] == [
        "POST", "GET", "POST"
    ]


def test_cube_s_add_remove_full_week_mismatch_does_not_retry():
    from _ariston_cube_testpkg.weekly_preview import weekly_read_fingerprint
    raw = _weekly_write_fixture()
    session = Session(
        Response({"token": "TOKEN"}),
        Response(raw),
        Response({"ok": True}),
        Response(raw),  # cloud still shows the old schedule
    )

    async def scenario():
        client = api.AristonClient(session, "user", "pass")
        with pytest.raises(api.AristonResponseError, match="NOT CONFIRMED"):
            await client.async_write_weekly_change(
                "GW123", 1, "add", to_time="12:00", preset="Economy",
                expected_fingerprint=weekly_read_fingerprint(raw),
            )

    run(scenario())
    assert [method for method, _, _ in session.calls] == [
        "POST", "GET", "POST", "GET"
    ]
