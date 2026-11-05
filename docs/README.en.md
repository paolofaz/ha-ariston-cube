# Ariston Cube · English quick guide (unofficial)

**Community Home Assistant integration**, independently developed for the
**Ariston CLAS ONE 30L boiler and Cube S thermostat**, using Ariston NET.
This is **not affiliated with, endorsed by, or supported by Ariston Group**. Ariston product names are used only to identify compatibility. The integration relies on unofficial cloud interfaces which can change without notice. See the prominent [independence and cloud API disclaimer](../README.md).

Stable release: see the [latest GitHub release](https://github.com/paolofaz/ha-ariston-cube/releases/latest). Verified on a Cube S and Home Assistant Core /
Container 2026.10.4. Minimum version advertised to HACS: 2026.10.0.
Other Ariston models and multi-zone installations are not guaranteed.

## Main features

- Responsive heating controls (OFF / HEAT / AUTO, setpoints, presets, boiler mode).
  The desired value appears immediately in Home Assistant, but a real cloud
  GET → single POST → readback sequence still validates every write.
  Pending values are labelled; failures roll back without blind automatic retry.
- The **real Cube S weekly schedule editor**, with 15-minute boundary moves,
  bounded Comfort/Economy additions, removals and **Clone day** to multiple
  destinations. Every change requires preview, explicit confirmation,
  fingerprint validation and exact seven-day readback.
- DHW target temperature via Home Assistant `water_heater` and a separate
  ACS Comfort switch. When available, the water heater reports the display-only
  state `on` independently of `DhwMode` and ACS Comfort; this does not
  indicate that the burner is physically on.
- Two long-lived cumulative heating/DHW gas meters using physical **Smc**
  measurements, plus guarded automatic two-hour bucket alignment for the
  Energy dashboard, at :15 past odd local hours.
- Six essential actions: four for weekly editing, two for read-only gas
  diagnostics. The automatic gas corrections run internally.

## Install

Use HACS → **Custom repositories** → paste
`https://github.com/paolofaz/ha-ariston-cube` and select **Integration**.
Install the latest stable release, restart Home Assistant, then add **Ariston Cube**
under **Settings → Devices & services**, with your Ariston NET login.

While this integration is not yet admitted to HACS's default repository
catalog, installation as a **custom repository** remains supported.

For a manual install, copy the complete
`custom_components/ariston_cube/` directory under your Home Assistant
configuration's `custom_components/` folder, restart, and configure.

The built-in Lovelace weekly card is registered automatically in
Storage dashboard mode. For YAML dashboards, register the module resource:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.3.0
    type: module
```

Then add a manual card using the *actual* weekly sensor entity ID:

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.YOUR_WEEKLY_PROGRAM_ENTITY_ID
title: Cube S weekly heating
```

## Safe operation

- The gas sensors, entity/unique IDs, stored ledger offsets and Recorder
  history are preserved during upgrades. **Never reset gas counters or
  delete Recorder to fix an hour.**
- Automatic Energy attribution never repeats an ambiguous statistics import,
  and does not backfill missed periods.
- A temporary Lovelace value is not proof that the Cube S applied it.
  Monitor the state attributes `ariston_comando_in_corso` and
  `ariston_comando_esito`.
- Do not blindly repeat weekly programme cloud writes after an ambiguous
  response: inspect the official Ariston app first.

### Read-only gas actions

```yaml
action: ariston_cube.inspect_automatic_energy_hour_alignment
```

For a specific hour (UTC):

```yaml
action: ariston_cube.inspect_energy_hour_alignment
data:
  target_start: "2026-10-28T14:00:00+00:00"
```

For full English documentation, installation instructions, controls, and
troubleshooting, see the [main README](../README.md).

[Latest releases](https://github.com/paolofaz/ha-ariston-cube/releases) ·
[Report an issue](https://github.com/paolofaz/ha-ariston-cube/issues) ·
[License](../LICENSE)
