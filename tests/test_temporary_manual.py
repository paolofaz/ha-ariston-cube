"""Offline contract tests: timer, persistence, real boundaries and no retry."""

import asyncio
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ariston_cube"
UTC = timezone.utc


def load(monkeypatch):
    name = "_ariston_temporary_test"
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT)]
    now = [datetime(2026, 11, 18, 10, 30, tzinfo=UTC)]
    timers = []

    class Store:
        memory = {}

        def __init__(self, hass, version, key):
            self.key = key

        async def async_load(self):
            return self.memory.get(self.key)

        async def async_save(self, value):
            self.memory[self.key] = dict(value)

    class HAError(Exception):
        pass

    def timer(hass, callback, when):
        item = {"when": when, "cancelled": False}
        timers.append(item)

        def cancel():
            item["cancelled"] = True

        return cancel

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    exc = types.ModuleType("homeassistant.exceptions")
    exc.HomeAssistantError = HAError
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    event = types.ModuleType("homeassistant.helpers.event")
    event.async_track_point_in_utc_time = timer
    storage = types.ModuleType("homeassistant.helpers.storage")
    storage.Store = Store
    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    dt = types.ModuleType("homeassistant.util.dt")
    dt.utcnow = lambda: now[0]
    dt.get_time_zone = ZoneInfo
    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    notifications = types.ModuleType("homeassistant.components.persistent_notification")
    notifications.async_create = lambda *args, **kwargs: None
    components.persistent_notification = notifications
    api = types.ModuleType(name + ".api")
    class AristonZoneModeNotSent(Exception):
        pass
    api.AristonZoneModeNotSent = AristonZoneModeNotSent
    const = types.ModuleType(name + ".const")
    const.DOMAIN = "ariston_cube"
    states = types.ModuleType(name + ".states")
    states.enum_code = lambda value: (value or {}).get("value")
    weekly = types.ModuleType(name + ".weekly_program")
    weekly.DAYS_IT = ("Domenica", "Lunedì", "Martedì", "Mercoledì",
                      "Giovedì", "Venerdì", "Sabato")
    for path, module in {
        name: package, "homeassistant": ha, "homeassistant.exceptions": exc,
        "homeassistant.components": components,
        "homeassistant.components.persistent_notification": notifications,
        name + ".api": api,
        "homeassistant.helpers": helpers, "homeassistant.helpers.event": event,
        "homeassistant.helpers.storage": storage,
        "homeassistant.util": util, "homeassistant.util.dt": dt,
        name + ".const": const, name + ".states": states,
        name + ".weekly_program": weekly,
    }.items():
        monkeypatch.setitem(sys.modules, path, module)
    util.dt = dt
    path = name + ".temporary_manual"
    spec = importlib.util.spec_from_file_location(path, ROOT / "temporary_manual.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, path, module)
    spec.loader.exec_module(module)
    return module, Store, now, timers


def schedule():
    slices = [
        {"minute": 0, "preset": "Comfort"},
        {"minute": 480, "preset": "Economy"},
        {"minute": 600, "preset": "Economy"},  # redundant
        {"minute": 780, "preset": "Comfort"},
    ]
    return {"days": {day: [dict(item) for item in slices] for day in
        ("Domenica", "Lunedì", "Martedì", "Mercoledì",
         "Giovedì", "Venerdì", "Sabato")}}


class Main:
    def __init__(self):
        self.data = {"ZoneMode": {"value": 3}}
        self.listeners = []
        self.calls = []
        self.fail = False

    def async_add_listener(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback)

    def async_update_listeners(self):
        for callback in tuple(self.listeners):
            callback()

    async def async_set_zone_mode(self, mode):
        self.calls.append(mode)
        if self.fail:
            raise RuntimeError("uncertain cloud response")
        self.data["ZoneMode"]["value"] = mode
        self.async_update_listeners()


class Weekly:
    def __init__(self):
        self.data = schedule()
        self.last_update_success = True
        self.listeners = []

    def async_add_listener(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback)

    async def async_refresh(self):
        for callback in tuple(self.listeners):
            callback()


class Entry:
    entry_id = "test-plant"

    def __init__(self):
        self.tasks = []

    def async_create_background_task(self, hass, coro, name):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task


def setup(module):
    return (types.SimpleNamespace(config=types.SimpleNamespace(time_zone="Europe/Rome")),
            Entry(), Main(), Weekly())


def test_transition_skips_redundant_and_handles_week_boundary(monkeypatch):
    mod, _, _, _ = load(monkeypatch)
    result = mod.next_preset_transition(
        schedule(), datetime(2026, 11, 18, 8, 30, tzinfo=UTC),
        ZoneInfo("Europe/Rome"))
    assert result == datetime(2026, 11, 18, 12, tzinfo=UTC)
    data = schedule()
    for day in data["days"]:
        data["days"][day] = [{"minute": 0, "preset": "Economy"}]
    data["days"]["Lunedì"] = [{"minute": 0, "preset": "Comfort"}]
    result = mod.next_preset_transition(
        data, datetime(2026, 11, 22, 12, tzinfo=UTC),
        ZoneInfo("Europe/Rome"))
    assert result == datetime(2026, 11, 22, 23, tzinfo=UTC)


def test_incomplete_week_is_rejected(monkeypatch):
    mod, _, _, _ = load(monkeypatch)
    data = schedule()
    data["days"]["Lunedì"] = None
    with pytest.raises(ValueError):
        mod.next_preset_transition(
            data, datetime(2026, 11, 18, 10, tzinfo=UTC),
            ZoneInfo("Europe/Rome"))


def test_temporary_activation_expires_once_and_clears_storage(monkeypatch):
    mod, Store, now, timers = load(monkeypatch)
    hass, entry, main, weekly = setup(mod)

    async def run():
        controller = mod.TemporaryManualController(hass, entry, main, weekly)
        await controller.async_initialize()
        await controller.async_activate()
        assert main.calls == [2]
        assert controller.deadline == datetime(2026, 11, 18, 12, tzinfo=UTC)
        assert timers[-1]["when"] == controller.deadline
        assert Store.memory[controller._store.key]["attempted"] is False
        now[0] = controller.deadline
        await controller.async_expire()
        await controller.async_expire()
        assert main.calls == [2, 3]
        assert not controller.active
        assert Store.memory[controller._store.key] == {}
        controller.stop()

    asyncio.run(run())


def test_manual_cancels_pending_auto(monkeypatch):
    mod, _, _, timers = load(monkeypatch)
    hass, entry, main, weekly = setup(mod)

    async def run():
        controller = mod.TemporaryManualController(hass, entry, main, weekly)
        await controller.async_initialize()
        await controller.async_activate()
        await controller.async_select_permanent(2)
        assert main.calls == [2, 2]
        assert not controller.active
        assert timers[-1]["cancelled"]
        controller.stop()

    asyncio.run(run())


def test_failed_return_is_never_retried_after_restart(monkeypatch):
    mod, _, now, _ = load(monkeypatch)
    hass, entry, main, weekly = setup(mod)

    async def run():
        controller = mod.TemporaryManualController(hass, entry, main, weekly)
        await controller.async_initialize()
        await controller.async_activate()
        now[0] = controller.deadline
        main.fail = True
        await controller.async_expire()
        assert main.calls == [2, 3]
        assert controller.attempted
        assert controller.error == "non_confermato"
        controller.stop()
        restored = mod.TemporaryManualController(hass, entry, main, weekly)
        await restored.async_initialize()
        assert restored.attempted
        assert main.calls == [2, 3]
        restored.stop()

    asyncio.run(run())


def test_proven_unsent_auto_waits_for_cooldown_and_survives_restart(monkeypatch):
    mod, Store, now, timers = load(monkeypatch)
    hass, entry, main, weekly = setup(mod)
    main.client = types.SimpleNamespace(rate_limit=types.SimpleNamespace(remaining_seconds=lambda: 600))
    async def run():
        controller = mod.TemporaryManualController(hass, entry, main, weekly)
        await controller.async_initialize()
        await controller.async_activate()
        now[0] = controller.deadline
        original = main.async_set_zone_mode
        async def unsent(mode):
            main.calls.append(mode)
            raise mod.AristonZoneModeNotSent("not transmitted")
        main.async_set_zone_mode = unsent
        await controller.async_expire()
        assert controller.retry_count == 1 and not controller.attempted
        assert (controller.retry_at - now[0]).total_seconds() == 600
        assert Store.memory[controller._store.key]["retry_count"] == 1
        controller.stop()
        restored = mod.TemporaryManualController(hass, entry, main, weekly)
        await restored.async_initialize()
        assert timers[-1]["when"] == restored.retry_at
        await restored.async_expire()
        assert main.calls == [2, 3]
        now[0] = restored.retry_at
        main.async_set_zone_mode = original
        await restored.async_expire()
        assert main.calls == [2, 3, 3]
        assert not restored.active
        restored.stop()
    asyncio.run(run())


def test_weekly_change_updates_deadline(monkeypatch):
    mod, _, _, _ = load(monkeypatch)
    hass, entry, main, weekly = setup(mod)

    async def run():
        controller = mod.TemporaryManualController(hass, entry, main, weekly)
        await controller.async_initialize()
        await controller.async_activate()
        for slices in weekly.data["days"].values():
            slices[3]["minute"] = 840  # 14:00 instead of 13:00 local
        await weekly.async_refresh()
        await asyncio.gather(*entry.tasks)
        assert controller.deadline == datetime(2026, 11, 18, 13, tzinfo=UTC)
        controller.stop()

    asyncio.run(run())
