"""Offline behavioral tests for immediate Lovelace response and safe cloud sync.

No real boiler, HTTP, HA installation, gas statistics or entity registry.
The fake coordinator captures the exact states published to its listeners.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"


def load(monkeypatch):
    pkg_name = "_ariston_cube_optimistic_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]

    class HAError(Exception):
        pass

    class AuthError(Exception):
        pass

    class CloudError(Exception):
        pass

    class CommandRejected(ValueError):
        pass

    class FakeUpdateCoordinator:
        # Production DataUpdateCoordinator is generic at class creation time.
        __class_getitem__ = classmethod(lambda cls, typ: cls)

        def __init__(self, hass, logger, *, name, update_interval):
            self.data = None
            self.published = []

        def async_update_listeners(self):
            self.published.append((
                {k: dict(v) for k, v in self.display_data.items()},
                self.command_feedback("ZoneMode", "ZoneComfortTemp",
                                      "DhwTemp", "PlantMode"),
            ))

        def async_set_updated_data(self, data):
            self.data = data
            self.async_update_listeners()

    h = types.ModuleType("homeassistant")
    h.__path__ = []
    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = HAError
    exceptions.ConfigEntryAuthFailed = AuthError
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    update = types.ModuleType("homeassistant.helpers.update_coordinator")
    update.DataUpdateCoordinator = FakeUpdateCoordinator
    update.UpdateFailed = type("UpdateFailed", (Exception,), {})
    api = types.ModuleType(pkg_name + ".api")
    api.AristonClient = type("AristonClient", (), {})
    api.AristonAuthError = AuthError
    api.AristonError = CloudError
    api.AristonResponseError = type("AristonResponseError", (CloudError,), {})
    commands = types.ModuleType(pkg_name + ".commands")
    commands.CommandRejected = CommandRejected
    const = types.ModuleType(pkg_name + ".const")
    const.CONF_PLANT_ID = "plant_id"
    const.DOMAIN = "ariston_cube"
    const.SCAN_INTERVAL_SECONDS = 60
    model = types.ModuleType(pkg_name + ".model")
    model.parse_main_data = lambda x: x

    for key, item in {
        pkg_name: pkg,
        "homeassistant": h,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update,
        pkg_name + ".api": api,
        pkg_name + ".commands": commands,
        pkg_name + ".const": const,
        pkg_name + ".model": model,
    }.items():
        monkeypatch.setitem(sys.modules, key, item)
    spec = importlib.util.spec_from_file_location(
        pkg_name + ".coordinator", ROOT / "coordinator.py"
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)
    return mod, HAError, CloudError, CommandRejected


def initial():
    return {
        "PlantMode": {"value": 1, "options": [0, 1, 5]},
        "ZoneMode": {"value": 3, "options": [0, 2, 3]},
        "ZoneDesiredTemp": {"value": 20.0},
        "ZoneComfortTemp": {"value": 21.0, "min": 10, "max": 30},
        "DhwTemp": {"value": 49.0, "min": 36, "max": 60},
    }


def make_coordinator(mod, client):
    coord = mod.AristonCoordinator(
        None, SimpleNamespace(data={"plant_id": "plant-test"}), client
    )
    coord.data = initial()
    return coord


def test_manual_auto_immediately_previews_without_mutating_verified_cloud(monkeypatch):
    mod, _, _, _ = load(monkeypatch)
    event = asyncio.Event()

    class Client:
        calls = []

        async def async_set_zone_mode(self, plant_id, value):
            self.calls.append((plant_id, value))
            await event.wait()
            return {**initial(), "ZoneMode": {"value": 2, "options": [0, 2, 3]}}

    coord = make_coordinator(mod, Client())
    before = coord.data

    async def scenario():
        task = asyncio.create_task(coord.async_set_zone_mode(2))
        await asyncio.sleep(0)
        assert coord.display_data["ZoneMode"]["value"] == 2
        assert coord.data["ZoneMode"]["value"] == 3
        assert coord.data is before
        assert coord.published[0][0]["ZoneMode"]["value"] == 2
        assert coord.published[0][1]["ariston_comando_in_corso"] is True
        assert coord.command_feedback("ZoneMode")["ariston_comando_esito"] == "in_attesa"
        event.set()
        await task
        assert coord.data["ZoneMode"]["value"] == 2
        assert coord.display_data["ZoneMode"]["value"] == 2
        assert coord.command_feedback("ZoneMode") == {
            "ariston_comando_in_corso": False,
            "ariston_comando_esito": "confermato",
        }
        assert len(coord.published) == 2
        assert coord.client.calls == [("plant-test", 2)]

    asyncio.run(scenario())


@pytest.mark.parametrize("operation,item,new", [
    ("mode", "ZoneMode", 2),
    ("setpoint", "ZoneComfortTemp", 21.5),
    ("water", "DhwTemp", 50),
    ("plant", "PlantMode", 0),
])
def test_each_command_type_publishes_pending_overlay_then_confirms(
        monkeypatch, operation, item, new):
    mod, _, _, _ = load(monkeypatch)
    gate = asyncio.Event()

    class Client:
        async def async_set_zone_mode(self, plant, value):
            await gate.wait()
            return {**initial(), "ZoneMode": {"value": value}}

        async def async_set_setpoint(self, plant, name, value, *, require_manual):
            await gate.wait()
            return {**initial(), name: {"value": value}}

        async def async_set_plant_control(self, plant, name, value):
            await gate.wait()
            return {**initial(), name: {"value": value}}

    coord = make_coordinator(mod, Client())

    async def scenario():
        if operation == "mode":
            op = coord.async_set_zone_mode(new)
        elif operation == "plant":
            op = coord.async_set_plant_control(item, new)
        else:
            op = coord.async_set_setpoint(
                item, new, require_manual=(operation == "setpoint")
            )
        job = asyncio.create_task(op)
        await asyncio.sleep(0)
        assert coord.display_data[item]["value"] == new
        assert coord.data[item]["value"] != new
        assert coord.command_feedback(item)["ariston_comando_in_corso"] is True
        gate.set()
        await job
        assert coord.data[item]["value"] == new
        assert coord.command_feedback(item)["ariston_comando_esito"] == "confermato"

    asyncio.run(scenario())


def test_rejected_command_rolls_back_and_does_not_leave_pending(monkeypatch):
    mod, HAError, _, CommandRejected = load(monkeypatch)

    class Client:
        calls = 0

        async def async_set_zone_mode(self, plant, mode):
            self.calls += 1
            raise CommandRejected("invalid mode from fresh cloud")

    coord = make_coordinator(mod, Client())

    async def scenario():
        with pytest.raises(HAError):
            await coord.async_set_zone_mode(2)
        assert coord.data["ZoneMode"]["value"] == 3
        assert coord.display_data["ZoneMode"]["value"] == 3
        assert coord.published[0][0]["ZoneMode"]["value"] == 2
        assert coord.published[-1][0]["ZoneMode"]["value"] == 3
        assert coord.command_feedback("ZoneMode")["ariston_comando_esito"] == "rifiutato"
        assert coord.client.calls == 1

    asyncio.run(scenario())


def test_uncertain_cloud_response_rolls_back_and_never_retries(monkeypatch):
    mod, HAError, CloudError, _ = load(monkeypatch)

    class Client:
        calls = 0

        async def async_set_setpoint(self, plant, name, value, *, require_manual):
            self.calls += 1
            raise CloudError("POST completed; readback not confirmed")

    coord = make_coordinator(mod, Client())

    async def scenario():
        with pytest.raises(HAError) as error:
            await coord.async_set_setpoint("ZoneComfortTemp", 21.5)
        assert isinstance(error.value.__cause__, CloudError)
        assert coord.display_data["ZoneComfortTemp"]["value"] == 21.0
        assert coord.published[0][0]["ZoneComfortTemp"]["value"] == 21.5
        assert coord.command_feedback("ZoneComfortTemp")["ariston_comando_esito"] == "non_confermato"
        assert coord.client.calls == 1

    asyncio.run(scenario())


def test_concurrent_different_controls_rejected_before_any_second_write(monkeypatch):
    mod, HAError, _, _ = load(monkeypatch)
    gate = asyncio.Event()

    class Client:
        mode_calls = 0
        point_calls = 0

        async def async_set_zone_mode(self, plant, mode):
            self.mode_calls += 1
            await gate.wait()
            return {**initial(), "ZoneMode": {"value": mode}}

        async def async_set_setpoint(self, plant, name, value, *, require_manual):
            self.point_calls += 1
            return {**initial(), name: {"value": value}}

    coord = make_coordinator(mod, Client())

    async def scenario():
        task = asyncio.create_task(coord.async_set_zone_mode(2))
        await asyncio.sleep(0)
        with pytest.raises(HAError, match="Un altro comando"):
            await coord.async_set_setpoint("DhwTemp", 50)
        assert coord.client.point_calls == 0
        assert coord.display_data["ZoneMode"]["value"] == 2
        gate.set()
        await task
        assert coord.client.mode_calls == 1

    asyncio.run(scenario())


def test_polling_during_pending_control_does_not_erase_requested_display(monkeypatch):
    mod, _, _, _ = load(monkeypatch)
    gate = asyncio.Event()

    class Client:
        async def async_set_zone_mode(self, plant, mode):
            await gate.wait()
            return {**initial(), "ZoneMode": {"value": mode}}

    coord = make_coordinator(mod, Client())

    async def scenario():
        job = asyncio.create_task(coord.async_set_zone_mode(2))
        await asyncio.sleep(0)
        # A concurrent 60s poll returns the OLD verified cloud state.
        coord.async_set_updated_data(initial())
        assert coord.data["ZoneMode"]["value"] == 3
        assert coord.display_data["ZoneMode"]["value"] == 2
        assert coord.published[-1][0]["ZoneMode"]["value"] == 2
        gate.set()
        await job
        assert coord.display_data["ZoneMode"]["value"] == 2

    asyncio.run(scenario())


def test_validation_before_preview_prevents_phantom_change(monkeypatch):
    mod, HAError, _, _ = load(monkeypatch)

    class Client:
        async def async_set_zone_mode(self, plant, mode):
            raise AssertionError("no write expected")

    coord = make_coordinator(mod, Client())
    coord.data.pop("ZoneMode")

    async def scenario():
        with pytest.raises(HAError, match="non disponibile"):
            await coord.async_set_zone_mode(2)
        assert coord.published == []
        assert coord._pending_command is None

    asyncio.run(scenario())


def test_pending_overlay_does_not_mutate_gas_or_acquired_snapshot(monkeypatch):
    mod, _, _, _ = load(monkeypatch)
    coord = make_coordinator(mod, object())
    ledger = {"total_heating_smc": 845.724986, "total_dhw_smc": 263.631005}
    before = initial()
    coord.data = before
    coord._pending_command = ("ZoneMode", 2)
    optimistic = coord.display_data
    assert optimistic is not before
    assert optimistic["ZoneMode"] is not before["ZoneMode"]
    assert before["ZoneMode"]["value"] == 3
    assert ledger == {"total_heating_smc": 845.724986, "total_dhw_smc": 263.631005}
    optimistic["ZoneMode"]["value"] = 99
    assert before["ZoneMode"]["value"] == 3


def test_explicit_cloud_rejection_rolls_back_with_refused_status(monkeypatch):
    mod, HAError, _, _ = load(monkeypatch)
    from sys import modules

    rejection = modules["_ariston_cube_optimistic_test.api"].AristonResponseError

    class Client:
        async def async_set_zone_mode(self, plant, mode):
            raise rejection("Ariston refused zone mode")

    coord = make_coordinator(mod, Client())

    async def scenario():
        with pytest.raises(HAError):
            await coord.async_set_zone_mode(2)
        assert coord.display_data["ZoneMode"]["value"] == 3
        assert coord.command_feedback("ZoneMode")["ariston_comando_esito"] == "rifiutato"

    asyncio.run(scenario())


def test_cancelled_request_clears_preview_and_prevents_retry(monkeypatch):
    mod, _, _, _ = load(monkeypatch)
    started = asyncio.Event()

    class Client:
        calls = 0

        async def async_set_zone_mode(self, plant, mode):
            self.calls += 1
            started.set()
            await asyncio.Future()

    coord = make_coordinator(mod, Client())

    async def scenario():
        job = asyncio.create_task(coord.async_set_zone_mode(2))
        await started.wait()
        assert coord.display_data["ZoneMode"]["value"] == 2
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert coord.display_data["ZoneMode"]["value"] == 3
        assert coord.command_feedback("ZoneMode")["ariston_comando_esito"] == "non_confermato"
        assert coord.client.calls == 1

    asyncio.run(scenario())
