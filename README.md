> **EXPERIMENTAL v1.1.1-rc.2 — correzione gas automatica ogni due ore.**
> Mantiene tutte le funzioni della stabile 1.1.0 (incluso **Clona giorno**)
> e automatizza la stessa correzione delle statistiche Energia già verificata
> sul Cube S. Alle **:15 delle ore dispari locali** controlla i consumi
> Ariston e, solo se tutti i dati coincidono, corregge una volta la statistica
> oraria. **Nessun retry**, nessun recupero di orari persi, nessuna modifica
> ai sensori cumulativi, agli ID o al ledger gas. Dopo ogni ciclo verifica con
> `ariston_cube.inspect_automatic_energy_hour_alignment` (sola lettura).
> [Istruzioni per 2–3 fasce e note RC2](docs/releases/v1.1.1-rc.2.md).

> **Stable v1.1.0 — Cube S weekly schedule editor.** On the Lovelace timetable, choose **Modifica fasce** to move an existing time, add a finite Comfort/Economy band with explicit start/end, remove a band, or **Clona giorno** onto multiple selected weekdays in one confirmed save. New times are selected in 15-minute increments. All writes require a fresh cloud preview, full-week fingerprint validation, explicit confirmation, a single POST and seven-day readback. [Release notes](docs/releases/v1.1.0.md).
>
> **Gas-hour alignment is still experimental and separate:** v1.0.2-rc.2 is not included in stable 1.1.0. Switching versions does not erase the existing gas cumulative sensor history or revert hourly Energy corrections, but it removes that RC's manual hour-alignment actions. Original stable v1.0.1 remains available by its tag.
>
> Cloud schedules persist on the boiler even after a software downgrade. Keep an official Ariston app screenshot of the current week and inspect the entire preview before saving.

# Ariston Cube for Home Assistant

**Stable version 1.1.0** — A custom HACS integration developed and field-tested with an **Ariston CLAS ONE 30L boiler and Cube S thermostat**, using **Home Assistant Container / Core 2026.10.4**.

Ariston Cube provides boiler and heating-zone controls, domestic hot water (DHW) temperature control, editable Cube S schedules, and persistent gas consumption totals for the Home Assistant Energy dashboard.

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
