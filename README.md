> **NEW EXPERIMENTAL 1.1.0-rc.6:** Adding a Cube S Comfort/Economy time band now requires **both start and end**, so it restores the previous preset at the specified end rather than lasting to the next arbitrary boundary. New times use selectable **15-minute slots**, enforced by backend validation. Deleting the newly inserted band can also remove its redundant return boundary. See [rc.6 release notes](docs/releases/v1.1.0-rc.6.md).
> **Check the Ariston app before updating:** Any rc.5-added band may already have remained in effect beyond the intended ending time. Back up and verify the week. This release is SEPARATE from experimental gas-hour rc.2; do not swap away from gas rc.2 during its scheduled trial. Stable main stays unchanged.

> **FIXED IN EXPERIMENTAL 1.1.0-rc.6:** Adding/removing Cube S time bands now accepts extra zone-level metadata returned by Ariston, using the SAME POST envelope as the successful rc.3 time-moving test. An error like "Unknown zone metadata" in rc.4 was a PRE-POST validation refusal and did not change the boiler. After a confirmed write, the editor stays open and requires a fresh preview for each further edit. See [rc.5 notes](docs/releases/v1.1.0-rc.6.md).
> **CAUTION:** Add/remove have offline test coverage but require field verification on your real Cube S. Keep a screenshot of your original schedule and verify the Ariston app before leaving this branch. This build does NOT include the independent gas-hour correction rc.2; finish both experiments separately before combining them.

> **NEW experimental 1.1.0-rc.6 — Cube S weekly editor now supports MOVE, ADD and REMOVE of a single Comfort/Economy boundary.**
> Open the existing weekly card and choose an operation; always preview and confirm before one real cloud write.
> Add/remove are tested offline but have **not yet been verified on the live boiler**; only boundary moving was validated in the Ariston app in rc.3.
> **Do not install this version while testing gas-hour alignment rc.2:** these are separate experimental branches, not a combined release.
> Stable 1.0.1 and all existing release tags remain untouched.
> Details: [RC4 release notes](docs/releases/v1.1.0-rc.6.md).

> **EXPERIMENTAL TEST BUILD 1.1.0-rc.6 — NOT the stable 1.0.1.**
> This branch contains an unsupported, user-triggered Cube S weekly schedule
> write experiment. The endpoint advertises POST, but its JSON body is still
> unverified. If the server accepts an unexpected format, saved timings may
> change. Switching back to stable software **will not revert boiler timings**.
>
> **New weekly Lovelace card editor:** tap any weekday or **Modifica fasce**, select the existing start time and a new time, then use **Anteprima** and **Salva sul Cube S**. Save requires a fresh backend preview and explicit on-screen confirmation. One POST only, followed by full-week readback. The editor is offered only when the experiment's actions are registered.
>
> **Developer Tools → Actions:** alternatively, first execute
> `ariston_cube.preview_weekly_slice` and keep its
> `source_fingerprint`. Then, only if you deliberately accept a real
> device write, execute `ariston_cube.test_write_weekly_slice` using the
> same day and before/after times and the fingerprint.
>
> Example with a real Monday boundary, subject to a matching fresh read:
>
> ```yaml
> action: ariston_cube.test_write_weekly_slice
> data:
>   day: 1
>   from_time: "05:45"
>   to_time: "06:00"
>   expected_fingerprint: "PASTE_THE_64_CHARACTER_FINGERPRINT_FROM_PREVIEW"
>   confirm: true
> ```
>
> The test performs **one POST only**, followed by one GET. It is not an automatic rollback. It does not
> retry or roll back. If confirmation fails, use the official Ariston app
> to inspect the actual programme before trying anything else.
>
# Ariston Cube for Home Assistant

**Stable base: version 1.0.1** — A custom HACS integration developed and field-tested with an **Ariston CLAS ONE 30L boiler and Cube S thermostat**, using **Home Assistant Container / Core 2026.10.4**.

Ariston Cube provides boiler and heating-zone controls, domestic hot water (DHW) temperature control, read-only Cube S schedules, and persistent gas consumption totals for the Home Assistant Energy dashboard.

> **Disclaimer:** This is an independent community project, not an official Ariston integration. The Ariston cloud endpoints used here are not guaranteed to remain stable. The hardware and Home Assistant version above are the verified reference setup, not a claim of compatibility with every model or release.

## Highlights

- **Cube S climate entity:** room temperature, heating target, OFF, HEAT (manual), and AUTO (existing weekly program).
- **Separate AUTO / Manuale selector:** operates on the same Cube S zone mode as the climate entity. No independent scheduler is created.
- **Boiler operating mode selector:** winter, summer, and off, separate from the zone's AUTO/manual setting.
- **DHW water heater entity:** temperature setpoint control from **36 to 60 °C**, in **1 °C** increments, with a separate DHW Comfort switch.
- **Heating presets:** dedicated number entities for Comfort and Economy temperatures.
- **Telemetry:** heating request, boiler flame, heating flow and target temperatures, optional outdoor temperature, heating pressure, and other available readings.
- **Two persistent gas totals:** one for central heating and one for DHW, based on the cloud's physical **standard cubic meter (Smc)** readings.
- **Read-only weekly schedule:** a sensor, calendar view, and optional Lovelace timeline card.
- **Native DHW controls:** use the Home Assistant water heater entity and the independent Comfort switch.

### Home Assistant entities

| Domain | Purpose |
| --- | --- |
| `climate` | Cube S thermostat, temperature and OFF/HEAT/AUTO |
| `water_heater` | DHW temperature target only |
| `select` | Boiler winter/summer/off and Cube S AUTO/Manuale |
| `switch` | DHW Comfort and automatic thermoregulation |
| `number` | Heating Comfort/Economy setpoints |
| `binary_sensor` | Heating request and boiler flame |
| `sensor` | Temperatures, pressure, read-only weekly program and two cumulative Smc totals |
| `calendar` | Read-only Cube S weekly heating schedule |

Version 1.0.0 removed the former daily and two-hour Smc diagnostic sensors and the obsolete DHW number control. The cumulative gas entities retain their existing unique IDs; the cleanup targets only obsolete **Ariston Cube** entity registry entries belonging to the configured installation. It does not delete Recorder history or long-term statistics.

## Installation with HACS

1. In HACS, add `https://github.com/paolofaz/ha-ariston-cube` as a **custom repository** of type **Integration**, if it is not already installed.
2. Install or update **Ariston Cube**. For a future 1.0.1 release, select `v1.0.1` once it is published.
3. Restart Home Assistant and use **Settings → Devices & services** to add or review the Ariston Cube integration.
4. Select your boiler through the integration's configuration flow.

This maintenance branch is based on stable 1.0.0. **No 1.0.1 release has been published yet; `main` stays on 1.0.0.** Do not retarget the existing stable tag.

**When updating an existing installation, preserve the Ariston Cube config entry, the Home Assistant Recorder database and all integration files under `.storage`.** They include persistent gas-meter checkpoints and historical Energy data. Keep any pre-migration database backup.

## Heating controls: AUTO, Manuale and OFF

The Cube S `climate` entity exposes three familiar heating modes:

| Climate mode | Cube S zone mode | Meaning |
| --- | --- | --- |
| OFF | `ZoneMode=0` | Heating zone disabled |
| HEAT | `ZoneMode=2` | Manual heating |
| AUTO | `ZoneMode=3` | Follow the Cube S's stored weekly schedule |

The additional **“Modalità riscaldamento”** select offers **AUTO** and **Manuale** only. It calls the same verified zone-mode command and read-back mechanism as the climate entity, so both reflect the cloud-reported setting. It is intentionally unavailable when the plant is in summer/off mode, the zone is disabled/in an unsupported mode, or Ariston does not report both options.

The **“Modalità caldaia”** select controls the whole boiler's winter/summer/off mode independently. The **automatic thermoregulation** switch is a different feature; it does not switch between the Cube S weekly program and manual heating.

Heating setpoint changes through the climate entity use the existing guarded manual-mode command. Changes to the stored Comfort and Economy presets are available through their separate number entities.

### What does the flame sensor measure?

`IsFlameOn` is reported at **plant level** (zone 0): it means that the boiler burner is active, **not necessarily that space heating is active**. The burner may also be operating for DHW.

The separate `ZoneHeatRequest` signal refers to heating zone 1. Home Assistant's `climate.hvac_action` reports `heating` when the zone requests heat **and** the burner reports a flame. This is a useful heating status, but is not an independent measurement of which circuit receives the flame. There is no inferred “DHW flame” sensor.

## Domestic hot water

The `water_heater` entity supports **target temperature only**: it does not expose an operation-mode selector or artificial on/off commands. The temperature control writes `DhwTemp`, respecting both local and cloud-supplied limits; it uses a fresh read and confirms the result after the command.

Actual stored-water temperature is displayed only if `DhwStorageTemperature` is available from the boiler.

**DHW Comfort remains a separate switch.** It is not equivalent to switching the boiler on or off. If the cloud reports a timed Comfort state that cannot be safely mapped to a simple boolean, the integration does not invent an on/off value.

Automations previously using the removed DHW number entity should instead call `water_heater.set_temperature`.

### Native DHW controls

The custom `ariston-cube-acs-card` was retired in the **1.0.1 maintenance branch**.
Use the native `water_heater` entity and the separate DHW Comfort switch.
The standard Home Assistant device page may display **"Off"** from the
read-only cloud `DhwMode`; the underlying DHW setpoint is still configurable.
We intentionally do not fake an operating mode to suppress that label.

**Upgrading from 1.0.0:** remove existing manual `custom:ariston-cube-acs-card`
cards from your dashboards. If the old ACS script remains registered in
Settings → Dashboards → Resources, remove that entry manually. Only the
Cube S weekly card is served and registered in 1.0.1. Existing dashboard
layouts and resources are not deleted by the integration.

### Cube S weekly Lovelace card

The bundled `ariston-cube-weekly-card` remains available and is currently
read-only. It can be adapted for verified editing in a future release.

In **Storage** dashboard mode, its module resource is registered automatically.
For manual **YAML** resources, add:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.0.1
    type: module
```

Update any older resource URL query version and reload your dashboard.

## Gas consumption and Energy dashboard

The two cumulative gas sensors use the **physical Smc** values in Ariston's `asPhysicalUnit.histogramData`, **not an estimated conversion from kWh**.

In Home Assistant, the sensors use:

- `device_class: gas`
- `state_class: total`
- `unit_of_measurement: m³` (representing standard cubic meters, Smc)

The initial cumulative reading may include part of the previous day and the current day. **It is the initial point of this integration's series, not a lifetime meter reading for the boiler.**

To prevent double counting, the integration stores a checkpoint for each **local calendar day + heating/DHW category + two-hour interval** in Home Assistant's `.storage`. Re-reading the same interval does not add it twice, while reported corrections change the cumulative total by the difference. The recorded behavior across midnight has been verified against Ariston's `CurrentDay` and `PreviousDay` reports.

Cloud reads are scheduled at **:10 and :40 after each even-numbered hour**, with an initial refresh and a six-hour fallback. The two-hour data is still used internally even though the former standalone two-hour sensors have been removed.

If the cloud data is incomplete or a checkpoint becomes unreliable, a sensor may become unavailable rather than report invented usage. **Do not delete the gas checkpoint files under `.storage`.** Recovery from downtime exceeding the cloud's available history remains a future hardening task.

### Existing Energy history

The reference installation migrated its prior **m³** Energy statistics into the new cumulative sensor histories using a separately backed-up, manually verified SQLite procedure. **Ariston Cube does not migrate, reset or rewrite Recorder, `statistics_meta` or Energy dashboards.**

Do not repeat a database migration on an installation that has already been migrated. Before removing any older integration on other installations, check all dashboards, automations, templates and historical statistics. Keep database backups.

## Cloud architecture and diagnostics

Ariston Cube uses two independent authenticated cloud sessions:

- **Mobile `/api/v2` interface:** boiler/zone values, controls and Cube S schedule readings.
- **Web `/R2` interface:** physical Smc reports and DHW Comfort controls.

Mobile bearer-token authentication cannot be reused as web-portal cookie/CSRF authentication. The sessions are deliberately isolated. Diagnostics report safe schema information rather than credentials or full cloud responses.

## Scope and roadmap

**Included since 1.0.0:** monitoring, verified heating/DHW controls, persistent gas totals, and reading the real Cube S weekly timetable.

**Not included:** editing or saving Cube S weekly time bands. That work is isolated in the experimental `feat/cube-s-weekly-schedule-editor` branch. Any future write operation requires an independently verified endpoint/payload, a fresh-source comparison, explicit confirmation, a read-back check and a recovery strategy. Experimental code must not be installed as the stable 1.0.0.

Additional hardening is planned for prolonged cloud or Home Assistant outages affecting gas-meter history.

## Development

```bash
python -m pip install pytest aiohttp
python -m compileall -q custom_components/ariston_cube tests
python -m pytest -q
```

Offline tests check data parsing, safety checks and entity contracts; they do **not** replace testing against a real boiler.

Issues and source code: https://github.com/paolofaz/ha-ariston-cube


### Testing the experimental Lovelace editor

The bundled `custom:ariston-cube-weekly-card` is the **same card** as before.
Tap **Modifica fasce** or an individual weekday to reveal an inline editor.
Only moving an *existing, non-midnight start boundary* is supported in this
first UI version; adding/removing periods and changing presets are deliberately
out of scope until separately tested. One edit is attempted at a time.

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.YOUR_ACTUAL_WEEKLY_PROGRAM_ENTITY
title: Fasce riscaldamento Cube S
```

With a Storage dashboard, the integration upgrades the registered weekly
resource to `/ariston_cube/ariston-cube-weekly-card.js?v=1.1.0-rc.6`.
If the browser still renders the old card, hard-refresh the dashboard.
YAML resource mode requires updating the resource URL manually. If reverting
to stable **1.0.1**, also revert the weekly resource URL to `?v=1.0.1` in
Settings → Dashboards → Resources if the old editor stays cached.

Reinstalling a stable release does **not** restore any Cube S programme
modified during experiments: review the actual Ariston schedule separately.
