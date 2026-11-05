# Ariston Cube for Home Assistant (Unofficial)

> **UNOFFICIAL COMMUNITY PROJECT — NOT AFFILIATED WITH ARISTON**
>
> This integration is independently developed and maintained by the community. It is **not created, approved, endorsed, sponsored, certified, or supported by Ariston Group**. Do not mistake it for an official Ariston integration or contact Ariston customer support for issues with this project.
>
> **Ariston**, **Ariston NET**, **Cube S**, and other product names are used solely to identify compatible devices and services. Trademarks belong to their respective owners. This project uses independent, neutral branding and does not use the official Ariston logo.
>
> The integration depends on **unofficial Ariston NET cloud interfaces**, which may change, become unavailable, or be subject to service restrictions without notice. Functionality is not guaranteed. Use at your own risk and review any applicable service terms. This notice is not a guarantee against trademark or service-related claims.

[![Release](https://img.shields.io/github/v/release/paolofaz/ha-ariston-cube?label=stable%20release)](https://github.com/paolofaz/ha-ariston-cube/releases/latest)
[![CI](https://github.com/paolofaz/ha-ariston-cube/actions/workflows/ci.yml/badge.svg)](https://github.com/paolofaz/ha-ariston-cube/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/github/license/paolofaz/ha-ariston-cube)](LICENSE)

**Home Assistant integration for the Ariston Cube S thermostat, weekly heating schedules, and gas consumption.** Developed and tested with an **Ariston CLAS ONE 30L boiler + Cube S thermostat** connected to Ariston NET.

> **Stable release:** see the [latest GitHub release](https://github.com/paolofaz/ha-ariston-cube/releases/latest). Responsive Lovelace controls, a full weekly schedule editor, cloning days, and guarded automatic alignment of gas Energy statistics. Verified on a physical Cube S; other devices and cloud versions may behave differently.
>
> **Cloud confirmation matters.** Home Assistant may temporarily display a requested control value before the boiler confirms it. See [Responsive controls](#responsive-lovelace-controls-with-cloud-confirmation).

## Features

| Area | Capabilities |
| --- | --- |
| **Cube S climate** | Room temperature, target temperature, OFF / HEAT (manual) / AUTO (original weekly schedule) |
| **Responsive controls** | Immediate UI feedback, cloud readback confirmation, and rollback on failure |
| **Heating** | Comfort / Economy temperatures, AUTO / Manual selection, boiler operating mode, thermoregulation |
| **Domestic hot water (DHW)** | `water_heater` target temperature and a separate DHW Comfort switch |
| **Cube S weekly schedule** | Sensor, calendar, custom weekly card: move, add, delete time blocks, and **Clone day** |
| **Gas and Energy** | Separate cumulative standard-cubic-metre (Smc) sensors for heating / DHW, guarded automatic attribution of two-hour consumption buckets |
| **Diagnostics** | Last automatic alignment cycles and **read-only** inspection of a particular statistical hour |

The integration does **not** replace the thermostat's built-in weekly schedule: **AUTO continues to use the actual Cube S schedule**.

### Domestic hot water

The `water_heater` entity controls the **DHW target temperature**. When available, it reports the informational state `on` independently of `DhwMode` and the **DHW Comfort** switch. This does **not** mean the boiler or burner is physically running.

The `water_heater` entity does not provide DHW on/off or mode commands; the DHW Comfort switch remains independent. Temperature limits, values, and cloud confirmation behavior are unchanged.

## Compatibility and requirements

- **Tested hardware:** Ariston CLAS ONE 30L with Cube S thermostat, zone 1.
- **Home Assistant:** minimum version advertised to HACS **2026.10.0**; tested with **Home Assistant Core / Container 2026.10.4**.
- **HACS** for installation and upgrades, or manual installation.
- A working **Ariston NET account** and Internet connectivity for the cloud API.

Other boiler models and multi-zone systems are **not guaranteed** to work. Gas totals come from physical consumption readings exposed by the cloud, not a kWh-to-m³ conversion.

## Installation

### Via HACS

1. In **HACS → ⋮ → Custom repositories**, add `https://github.com/paolofaz/ha-ariston-cube` with category **Integration**. Until accepted into the default HACS catalog, use this custom repository.
2. Install **Ariston Cube**, selecting the latest stable release.
3. **Restart Home Assistant.**
4. Go to **Settings → Devices & services → Add integration**, search for **Ariston Cube**, enter your Ariston NET credentials, and select your boiler.

**Upgrading:** update the integration and restart Home Assistant. **Do not delete the integration configuration, the `.storage` directory, or the Recorder database.** There is no need to reset gas sensors. Saved Cube S schedule changes remain in the cloud.

### Manual installation

Copy the complete `custom_components/ariston_cube/` directory into `<config>/custom_components/ariston_cube/` in your Home Assistant configuration, restart Home Assistant, and configure the integration. Keep `www/`, `strings.json`, and `translations/` inside the integration directory.

## Cloud rate limiting (v1.3.3)

Under normal conditions, the main cloud polling interval stays at **60 seconds**. If Ariston NET responds with **HTTP 429 (Too Many Requests)**, the integration pauses **all new requests** from both its mobile API and R2 web portal clients for an adaptive cooldown: **5, 10, 20, 40, then up to 60 minutes** after repeated throttling. If Ariston provides a longer valid `Retry-After` header, that delay takes precedence. A successful cloud response after the cooldown resets the escalation.

During a cooldown, Home Assistant may show temporarily unavailable or stale cloud data, and cloud commands cannot be sent. **No writes are queued or automatically retried.** The boiler's local controls and thermostat schedule continue operating independently. Regular scheduled polling resumes after the cooldown; interrupted gas/energy windows are **not automatically backfilled**.

## Responsive Lovelace controls with cloud confirmation

When you change **AUTO ↔ Manual**, a target temperature, or the boiler operating mode, Lovelace immediately displays the requested value while the command is submitted through Ariston NET.

While waiting, control entities expose these attributes (the attribute names and values are intentionally not translated):

```yaml
ariston_comando_in_corso: true
ariston_comando_esito: in_attesa
```

The underlying command sequence is **fresh cloud read → one POST → confirmation readback**. The provisional value does not modify the original device snapshot, measurement sensors, or gas totals.

| `ariston_comando_esito` | What happens |
| --- | --- |
| `confermato` | The server confirmed the value; the UI shows the verified state. |
| `rifiutato` | The UI rolls back to the last verified value because the command was rejected. |
| `non_confermato` | Timeout or uncertain outcome; the UI rolls back to the last verified state. **No automatic retry.** |

A second concurrent control command is rejected to avoid overlapping writes. The physical Cube S may change state later than the Lovelace display.

## Cube S weekly schedule editor

The included `ariston-cube-weekly-card` edits the **real weekly heating schedule** stored in the Ariston cloud:

- **Move time:** move an existing Comfort/Economy transition in 15-minute steps.
- **Add time block:** select a start time, end time, and preset; the previous preset resumes at the end.
- **Delete time block:** remove an existing transition and handle redundant boundaries.
- **Clone day:** copy a source day to one or more selected destination days.

Every edit requires **Preview → review before/after → explicit confirmation**. The integration compares a fingerprint of the full schedule, performs at most **one POST**, and reads back **all seven days**. After an ambiguous result, inspect the official Ariston app before trying another edit.

### Add the card to a dashboard

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.YOUR_ACTUAL_WEEKLY_SCHEDULE_ENTITY_ID
title: Cube S weekly heating
```

Replace the placeholder with the real weekly schedule sensor ID from **Developer tools → States**. The same fixed entity ID is not created on every installation.

The JavaScript resource is registered automatically for **Storage-mode** dashboards. For **YAML-mode** dashboards, also add:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.3.0
    type: module
```

After upgrading, hard-refresh the browser if an old card remains cached. See the [weekly card guide](frontend/README.md).

## Gas (Smc) and the Energy dashboard

Ariston NET exposes heating and DHW consumption as two separate **cumulative physical Smc** readings (standard cubic metres). Their entities have `device_class: gas`, `state_class: total`, and `m³` as their unit.

The cloud publishes gas consumption in **two-hour buckets**. The integration retrieves readings at approximately **:10**, with a second attempt at **:40**, during even-numbered local hours. If Home Assistant initially assigns an increment to the wrong hour, automatic alignment runs at **:15 during the following odd-numbered hour**, correcting only the statistics' time attribution.

| Example (Italian local time) | Period |
| --- | --- |
| Consumption period published by the cloud | **14:00–16:00** |
| Hour initially attributed by Home Assistant | 16:00–17:00 |
| Hour corrected by the integration at 17:15 | **15:00–16:00** |

Field validation observed **0.50 Smc heating + 0.03 Smc DHW** correctly assigned to 15:00–16:00, with zero assigned to 16:00–17:00, as well as confirmation across consecutive periods.

**Safety checks:** bucket validation, fingerprints, Recorder state and sum checks, a single save per sensor, write verification, and no automatic retry on an uncertain outcome. When source data is missing or consumption is zero or already aligned, no correction is forced. Missed buckets are not automatically backfilled after downtime.

**Do not rename the two cumulative gas sensors, delete stored offsets or the ledger, or reset Recorder.** Version 1.3.1 preserves gas history and Energy statistics state from previous versions.

## Developer tools actions

The integration exposes **only six actions**: four for Cube S weekly editing and two read-only gas diagnostics.

| Action (`ariston_cube.*`) | Purpose |
| --- | --- |
| `preview_weekly_change` | Preview a move, addition, or deletion |
| `write_weekly_change` | Save an explicitly confirmed change |
| `preview_weekly_clone` | Preview cloning a day |
| `clone_weekly_days` | Confirm a day clone |
| `inspect_automatic_energy_hour_alignment` | Read the latest automatic gas alignment cycles |
| `inspect_energy_hour_alignment` | Read statistics for a specific hour |

Previous `TEST` actions, probes, and manual gas-statistics writes are no longer exposed. Automatic gas processing remains internal.

To inspect recent automatic cycles **without writing anything**:

```yaml
action: ariston_cube.inspect_automatic_energy_hour_alignment
```

To inspect a particular statistics hour, use its **UTC timestamp** (convert the Italian local hour to UTC):

```yaml
action: ariston_cube.inspect_energy_hour_alignment
data:
  target_start: "2026-10-28T14:00:00+00:00"
```

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Integration does not appear | Restart Home Assistant after installing; check `custom_components/ariston_cube` |
| A command rolls back | Check `ariston_comando_esito`; for `non_confermato`, verify the actual value in the Ariston app before retrying |
| Weekly card looks outdated or cannot edit | Update the JS resource to `?v=1.3.0`, reload the dashboard, and check that the actions are registered |
| An automatic gas cycle is skipped | Inspect `inspect_automatic_energy_hour_alignment`; missing source data, unavailable Recorder, or zero consumption must not trigger forced writes |
| Historical gas totals look wrong | Preserve Recorder and `.storage` checkpoints; do not reinstall from scratch to alter statistics |

If you encounter a problem, [open a GitHub issue](https://github.com/paolofaz/ha-ariston-cube/issues) with your Home Assistant version, integration version, boiler model, and relevant logs. **Never include passwords, access tokens, or private information.** Project support is community-provided, not Ariston support.

# 🍺 Support the Project

If you found this project useful and want to support my work, you can offer me a beer:

[![Buy Me a Beer](https://img.shields.io/badge/Buy%20Me%20a%20Beer-0070ba?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/PaoloFazari)



## Development and contributing

The Python and JavaScript code is distributed under the [MIT License](LICENSE). GitHub Actions checks Python tests, Lovelace card tests (Node), [HACS validation](https://github.com/hacs/action), and [hassfest](https://github.com/home-assistant/actions/tree/master/hassfest).

```bash
python -m pip install pytest aiohttp
python -m compileall -q custom_components/ariston_cube tests
python -m pytest -q
node --test tests/test_weekly_editor.mjs
```

- [v1.3.3 release notes](docs/releases/v1.3.3.md)
- [v1.3.1 release notes](docs/releases/v1.3.1.md)
- [v1.3.0 release notes](docs/releases/v1.3.0.md)
- [HACS catalog submission notes](docs/HACS_PUBLICATION.md)
- [English quick guide](docs/README.en.md)
- [Issue tracker](https://github.com/paolofaz/ha-ariston-cube/issues)
- [Releases](https://github.com/paolofaz/ha-ariston-cube/releases)
