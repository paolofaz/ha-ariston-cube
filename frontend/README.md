# Cube S weekly schedule card for Home Assistant

The `custom:ariston-cube-weekly-card` Lovelace card is bundled with the **Ariston Cube** community integration (available since v1.3.0). It displays the **real Cube S weekly schedule** and allows carefully confirmed edits.

> **Unofficial project.** This card is not affiliated with, endorsed by, or supported by Ariston Group. See the [independence and cloud API disclaimer](../README.md) before use.

## Card features

- **Move time:** move an existing Comfort/Economy transition in 15-minute increments.
- **Add time block:** choose start/end times and a Comfort/Economy preset; the previous preset resumes at the end.
- **Delete time block:** remove an existing transition, including any redundant return boundary.
- **Clone day:** choose a source day and one or more destination days. Review the **before/after** schedule for each destination.

Each operation follows **Preview → explicit confirmation → a single cloud POST**, with schedule fingerprint validation and readback of all seven days. If the write result is uncertain, inspect the official Ariston app before attempting another change.

## Automatic and manual installation

On **Storage-mode** dashboards, the JS resource is registered automatically.

For **YAML-mode** dashboards, register it as a module resource:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.3.0
    type: module
```

To add the card, use a manual card with your **actual** weekly schedule sensor entity ID:

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.YOUR_ACTUAL_WEEKLY_SCHEDULE_ENTITY_ID
title: Cube S weekly heating
```

If an old card version appears after an update, refresh the resource URL and clear the browser cache.

## Alternative: copy the JavaScript manually

If you do not use the resource served by the integration, you can copy
`frontend/ariston-cube-weekly-card.js` into
`<config>/www/ariston-cube-weekly-card.js` in Home Assistant.

Then register `/local/ariston-cube-weekly-card.js` as a module resource in the dashboard and keep this file up to date whenever you upgrade. The automatically served `/ariston_cube/...` resource is recommended.

## Actions used by the card

Editing uses **only** these four integration actions:

- `ariston_cube.preview_weekly_change`
- `ariston_cube.write_weekly_change`
- `ariston_cube.preview_weekly_clone`
- `ariston_cube.clone_weekly_days`

Legacy `TEST` actions or experimental APIs are not required. Cloud writes are **never retried automatically** after an ambiguous response.

Two additional **read-only** gas diagnostic actions remain available; automatic gas processing is unchanged.

[Main README](../README.md) · [v1.3.0 release notes](../docs/releases/v1.3.0.md)
