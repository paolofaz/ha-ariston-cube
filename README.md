# Ariston Cube for Home Assistant

Experimental custom integration for **Ariston CLAS ONE 30L + Cube S** via the Ariston NET mobile API.

## Version 0.5.0 — Comfort/Economy controls and local branding

Login and the five original sensors were tested on the real boiler. The Cube S
`climate` temperature setting was also tested successfully on 2026-10-26.
This version changes the domestic hot water control to a **number**, not another
thermostat.

Entities:
- `climate` Cube S: current and target room temperature, heating state,
  explicit OFF/HEAT/AUTO zone-mode selection (when supported by cloud),
  and user-requested Comfort temperature with readback.
- `number` ACS temperature: 36–60 °C cap, 1 °C steps. Dynamic server
  minimum/maximum are intersected with these bounds.
- `number` heating Economy temperature: 10–30 °C cap, 0.5 °C steps,
  with narrower cloud limits taking precedence.
- `number` heating Comfort temperature: 10–30 °C cap, 0.5 °C steps,
  reflecting the Cube S's `ZoneComfortTemp` preset.
- The original three temperature sensors and two binary sensors remain and
  keep their unique IDs.

**The existing `water_heater` entity is no longer loaded.** Its previous
entity registry entry may remain in Home Assistant as orphaned/unavailable.
You can remove that particular old `water_heater` entry manually from the
entity registry after verifying the new number; do not remove the five
original sensors or the old Ariston integration. This does not rename or
migrate Recorder history.

## Installing this branch

Download ZIP from `feat/initial-readonly-integration`. Copy
`custom_components/ariston_cube` over `/config/custom_components/ariston_cube`
and **restart the whole Home Assistant container**. There is no need to
delete and re-add the Ariston Cube config entry. Verify manifest version 0.5.0.

## Safeguards for controls

The client performs one fresh authenticated read, validates both server-side
limits and local temperature caps, submits at most one
`/api/v2/remote/dataItems/{plant}/set` request using the previous value,
then reads back the cloud result. An uncertain write is **never retried
automatically**. The Climate dial requires manual heating mode to change the **active** target.
The independent Comfort/Economy number entities edit stored presets even when
AUTO is running, without changing the Cube S weekly time programme.
AUTO selects the existing Cube S program rather than writing a new schedule.
The existing weekly program remains the sole scheduling authority.

ACS 36–60 °C is the preliminary tested user range; if Ariston reports more
restrictive limits they take priority. Device-specific range or ACS write
success has **not yet** been verified. Do not immediately repeat a command
after a slow cloud response.

## Roadmap and experimental status

- Read/display weekly time programming from
  `/api/v2/remote/timeProgs/{plant}/ChZn1?umsys=si` once real response
  shape is verified. Avoid imposing an additional Home Assistant schedule.
- Implement exactly **three or fewer** well-defined consumption totals:
  heating, DHW, and electricity **only when independently proven available**.
  Avoid treating legacy `energy2` as boiler electricity. Historical
  daily/interval reports must be de-duplicated and persisted before exposing
  long-term-statistics sensors; do not convert monthly figures into pretend
  lifetime totals.
- Validate optional domestic hot water preheating status and its write
  semantics before adding a switch. `DhwMode` is not automatically
  equivalent to preheating.

These endpoints are unofficial. Parallel polling with the old integration
may cause occasional cloud/gateway 500 errors; avoid high request frequency.
No changes are made to the old `ariston` domain or its Recorder history.

## Development

```bash
python -m pip install pytest aiohttp
python -m compileall -q custom_components/ariston_cube tests
pytest -q
```

Offline tests do not prove any new device control works on a live Cube S.

## Platform regression tests

The CI suite contains unit-level platform contract tests for `climate`,
`number`, and the Home Assistant setup return value. It also exercises
ACS number clamping, step size, unavailable fields and dispatched setpoint
calls without a network connection. Real Cube S behavior still requires
on-device verification.

## On-demand diagnostics for energy and weekly schedule

Once the integration is installed, use the integration's **Download
diagnostics** menu item in Home Assistant. This makes exactly three additional
read-only cloud requests, **only when you ask for diagnostics**, to:

1. Read the Cube S's weekly `ChZn1` program.
2. Read the energy-account report, where upstream has documented historical
   period-specific gas/electricity fields.
3. Read the `Ch,Dhw` consumption-sequence report.

The diagnostics JSON contains just limited, allowlisted **field names, data
types and list counts**. It does not contain actual measurements, dates,
timestamps, plant IDs, usernames, tokens or boiler serials. Unknown keys are
counted but never copied verbatim. You can share this JSON for analysis.

No fake totals are published. When the real response schemas are understood,
we can implement a persistent deduplicating accumulator for CH/DHW and a third
electricity sensor only if its actual semantics are verified. The same
diagnostics will let us read the exact weekly schedule without building a
competing clock in HA.

## Brand icon (Home Assistant 2026.3+)

`custom_components/ariston_cube/brand/icon.png` contains the supplied house
symbol (squared and optimized to 256×256 with transparency). Modern Home
Assistant instances show local custom-integration brand assets automatically.
The HACS catalog may still show its generic placeholder due to its own
image-loading limitations; the Home Assistant integration/device page should
pick up this local icon following a full restart.

## Clarification: Comfort vs the Climate temperature

The separate Comfort number is the `ZoneComfortTemp` setting, the **same field
written by the Cube S climate dial when manual heating is active**. The Climate
entity *reads* `ZoneDesiredTemp`, the effective target temperature. The two
can differ during AUTO because the Cube S time programme can select Economy.
The new Comfort number allows adjusting the preset without switching away
from AUTO. All numeric inputs are capped at 10–30 °C even if cloud metadata
announces a wider range.

## Diagnostics 0.5.0: what the previous export established

The first real schema export reported an `energy_account.LastMonth` array
containing two objects with `gas` and `elect` fields, and a
`consumption_sequences` array containing 24 entries. The programme payload
was an object with one unrecognized top-level field. The earlier schema-only
filter suppressed all three field names from consumption-sequence entries and
the top-level programme field, so this data **does not yet prove what each
series means or which units it uses**.

The next diagnostics export includes `unnamed_field_shapes` for up to four
previously hidden fields per object. It reports only their **types and nested
structure**—not the names or their contents—while leaving known safe field
names intact. This helps inspect these endpoints without exposing the gateway
ID, token, timestamps or actual gas readings. Do not create cumulative
statistic sensors from `LastMonth` values.


## Diagnostics refinement in 0.5.1

The real 0.5.0 report confirmed 24 consumption-series records with 24 values
each, but obscured the p/k classification codes. 0.5.1 reports a
**provisional** category label for each series using the community API's
consumption-type and reporting-period enumerations, plus sample counts;
measurements and account data are never copied to diagnostics.

For the weekly programme, the schema allowlist now recognizes ChZn1, plans,
days, slices, from and temp and displays their shapes more deeply, but not
any of the scheduled times or temperature readings.

This is still insufficient to calculate lifetime energy statistics; time
alignment, metering units, rollover and possible cloud corrections remain to
be validated. The original Recorder history is never modified.
