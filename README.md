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


## Experimental next controls in 0.6.0
Manual SELECT for whole-plant PlantMode: Modalità inverno=1,
Modalità estate=0 and Spenta=5. This is distinct from the climate ZoneMode.
A control is rejected if cloud-reported supported modes are absent.
Manual SWITCH for AutomaticThermoregulation=0/1 controls automatic heating
flow-temperature regulation; it is independent from the Cube S weekly AUTO.
Each manual action reads its current value, performs one write, then checks
readback without retrying or making automatic changes on startup.

PENDING: the legacy DHW comfort/preheat function is web-menu parameter
U6_9_2 via /R2/PlantMenu/Submit, NOT the mobile API's DhwMode. Because
web login previously returned 403, no potentially misleading switch has
been created to toggle DhwMode in its place. Read-only investigation first.


## 0.6.1 — Cube S weekly programme (read-only)

A new sensor, **Programma settimanale Cube S**, shows the actual Ariston
weekly programme in Italian weekday attributes. Each daily attribute lists
start times and Comfort/Economy presets. Missing weekdays remain unknown;
unrecognised schedules are rejected rather than misrepresented.

The sensor uses a **separate coordinator refreshing every three hours**.
Its first refresh runs as a config-entry-scoped background task, so a slow
schedule query or a cloud 500 cannot block the original temperature, number,
switch, select or climate platforms. It does not send scheduling commands or
replace the Cube S timetable.

The 0.6.0 diagnostic export demonstrated 3 real weekly plans with daily
`days` and `slices` structures. The source's weekday numbering is
Sunday=0, Monday=1 ... Saturday=6, as the original Ariston integration
defines. These readings have not yet been on-device validated in 0.6.1.

The energy inventory reports 6 usage-code families each across 4 period
categories, but without actual units or persisted meter semantics we still
do not expose lifetime counters or create Energy Dashboard entities.


## Additional on-demand energy-units diagnostic in 0.6.1

The Ariston mobile API exposes `getConsumptionsSettings` as a read-only
`POST {}` (unlike its setter). Only **manual Download Diagnostics** calls
this endpoint. We export its schema and a strict recognized label for
`gasEnergyUnit`: kWh, GJ, therm, MBtu, Smc or m³. Tariffs and personal
consumption readings are not exported. The unit label alone does **not**
prove individual report codes are billed gas or a lifetime meter. The
electricity unit and origin still need independent confirmation.


## Additional optional boiler measurements (0.7.0)
Added device-data requests for **ChFlowTemp** (actual heating flow),
**ChFlowSetpointTemp** (heating flow target — the old integration's
`ch_flow_temperature`), **OutsideTemp** (outside probe), and
**HeatingCircuitPressure** (reported pressure in bar only).

Each sensor is unavailable if the cloud omits its item. Outdoor values equal
to the provided maximum are treated as an unconnected-sensor sentinel, as
in the upstream GALEVO client. Pressure values without an explicit 'bar'
unit are not represented as bar. These additions are read-only and do not
alter the existing five sensor IDs. No guessed DHW flame is exposed.


## Weekly schedule in Home Assistant Calendar (0.7.0)
The original Cube S seven-day Comfort/Economy timetable now appears in a
read-only Home Assistant **calendar** entity, separate from the existing
schedule sensor and its per-day attributes. It displays real start/end
intervals using Home Assistant's local timezone. The sensor and calendar
share exactly one cloud poller (every 3 hours). Neither entity alters the
weekly plan. Event editing is deliberately unavailable: no verified mobile
API write endpoint/payload for ChZn1 has been established.


## Previous-month heating and DHW gas reports (0.7.0)
The same integration includes two new independent **period-specific** sensors:
`Gas riscaldamento mese scorso` and `Gas ACS mese scorso`. The upstream
GALEVO client maps the first/second entries in
`energyAccount.LastMonth` to heating/DHW gas and describes that account
report as **kWh**. They are fetched with one read-only request every 6 hours
and the sensors are unavailable when no valid report exists.

They are informational and **NOT cumulative meters**: neither has
`TOTAL_INCREASING` or `TOTAL` state class, and neither is automatically
added to Home Assistant's Energy Dashboard. Verify their numeric values
against the existing Ariston integration before treating them as finalized.
The existing Recorder entity IDs/statistics are not changed or migrated.
Gas volume (Smc/m³) requires separate unit validation and conversion, so
this release does not pretend these are cubic meters.


## Remaining integration work

- ACS **Comfort preheat** OFF / Sempre attivo needs mobile access to the
  *actual* `U6_9_2` parameter, not guessed `DhwMode` commands. The
  previously rejected web login does not establish a supported mobile
  setter.
- Editing and saving the **original Cube S weekly plans** is pending a
  confirmed `ChZn1` write contract. The Home Assistant calendar introduced
  in 0.7.0 is expressly read-only; adding an event does not change the boiler.
- Only **last month's** two separate gas reports are exposed, in kWh, for
  comparison with the legacy entities. These values are **not** lifetime
  meters and must not be renamed to replace long-term Recorder statistics.
  No change to the existing Recorder database has been attempted.


## 0.7.1 — current-day and two-hour gas use (replaces monthly entities)

The user's existing integration previously used `consSequencesApi8` for
gas consumption in 2-hour buckets, reporting independent heating (k=7)
and domestic hot-water (k=10) values with period p=1. Its raw sequence
contains 24 two-hour values, oldest first: the latest corresponds to
the current two-hour local-time slot (which may still be in progress).
We follow the original slot alignment to derive `oggi` totals using only
bins assigned to the **current local calendar date**, and the latest
individual two-hour bin. The cloud is polled **every 2 hours** and once
on startup; all four values are published as kWh.

Sensors: Gas riscaldamento oggi, Gas ACS oggi, Gas riscaldamento fascia
bioraria, Gas ACS fascia bioraria. The previous-month entities introduced
in 0.7.0 are no longer loaded. Their orphaned entity-registry entries may
be removed manually; this does NOT rename or overwrite old recorder history.
The original integration remains completely untouched.

These are estimates of cloud reporting periods, not real-time gas meter
readings. Ariston may update its latest bucket with delay; values should
be compared against the previous integration before energy accounting.
The current-day total resets at midnight and the two-hour bucket resets
when its timeslot changes. Both deliberately lack a TOTAL_INCREASING state
class and MUST NOT be added as lifetime consumption sensors to the Energy
Dashboard. Existing Recorder and statistics are unchanged.

The Home Assistant Calendar remains read-only as a representation of the
stored Cube S weekly programme. The Schedule integration is a user-managed
helper and cannot itself push edits back to the Cube S, so we do not create
a competing schedule helper. Editable weekly programmes require a verified
Ariston cloud write endpoint.

## Vista settimanale compatta (facoltativa)

La normale entità calendario non è adatta a visualizzare programmi ricorrenti.
È disponibile una scheda Lovelace autonoma, soltanto grafica, nel file
`frontend/ariston-cube-weekly-card.js`, con guida in `frontend/README.md`.
Non invia comandi e non crea uno schedule locale alternativo.


## Auto-installed Cube S weekly card (0.7.2)

The tested weekly Lovelace card is bundled as
`custom_components/ariston_cube/www/ariston-cube-weekly-card.js`, so installing
the integration brings the file along. In Lovelace resource **storage** mode,
it is registered automatically as a JS module. No extra downloads or manual
resource registration are required for a fresh installation.

Your previously manual `/local/ariston-cube-weekly-card.js?v=1` resource
may still exist. To use the updated automatically bundled card, remove
that old resource from the dashboard resources; leave the existing Lovelace
card YAML configuration unchanged (`type: custom:ariston-cube-weekly-card`).
The card continues to be a **read-only** representation of the Cube S's
existing timetable.

With Lovelace YAML resource mode, the resource has to be declared explicitly
as `/ariston_cube/ariston-cube-weekly-card.js?v=0.7.2`.


## Version 0.7.3: cautious Comfort ACS discovery

An extra **read-only**, on-demand diagnostic now probes the two documented
legacy web menu refresh routes for **U6_9_2** (ACS Comfort function).
The diagnostic adds `comfort_acs_menu_probe` with one of:
`spenta`, `temporizzata`, `sempre_attiva`, or a sanitized error type.
It never includes passwords, tokens, cookie values, gateway IDs or raw
menu responses, and **never submits a Comfort command**. It does not poll
these endpoints periodically.

A usable Comfort OFF/Sempre attivo switch requires that one of the routes
supports authenticated readback on this actual boiler. Historical
`/R2/Account/Login` failures mean working mobile authentication is not
yet proof of web-menu access. Do not equate mobile `DhwMode` with this
web-menu parameter. Do not fabricate an optimistic switch.


## Experimental 0.8.0 — real physical Smc and ACS Comfort

A separate authenticated R2 web session now uses the portal anti-forgery
token and session cookie, never the mobile ar.authToken. This protocol
was independently documented in HAL9000RELOADED/elco-remocon-net.
It has **not yet been field-tested on this particular Ariston account**.

Four new Smc observational entities read the server's original
`asPhysicalUnit.histogramData` CurrentDay 2-hour slots (CH and DHW)
from /R2/PlantMetering/GetData. No guessed gas calorific factor is used.
They become unavailable if the web portal cannot be reached. The existing
kWh gas entities are untouched. Smc series are not cumulative gas meters
and have no TOTAL_INCREASING state class.

The new Comfort ACS switch reads the real U6_9_2 web menu parameter
and sends only 0 (OFF) or 2 (Always active) to /R2/PlantMenu/Submit.
A timed state 1 leaves the switch unavailable. A single explicit
command must be permitted by the menu options and its readback must match.
No automatic writes or write retries. The control is not yet confirmed
on this physical boiler.

Previously working mobile controls, Recorder data and old Ariston
integration remain independent and unchanged.


## 0.8.1 — R2 login correction from field diagnostics

Home Assistant 2026.10.4 field diagnostics showed web authorization failing
already on the first **GET /R2/Account/Login**, before reading the Smc report
or the U6_9_2 ACS Comfort switch. The original 0.8.0 web client disabled
redirects, rejecting common login-form redirects before receiving HTML.

Version 0.8.1 follows bounded login-form redirects, verifies the final
host belongs to the original official Ariston domain, accepts the
antiforgery hidden input regardless of attribute ordering, and uses its
own Home Assistant managed cookie session, separate from mobile API calls.
A failed form GET/POST now exposes only its numeric HTTP status in
`comfort_acs_menu_probe` within on-demand diagnostics.

The two features still depend on the live R2 web endpoint accepting this
specific account; tests alone cannot establish that. In case of a continuing
403/404/5xx, do not repeatedly retry the Comfort switch or invent Smc from
the kWh series. Old mobile sensors/controls and Recorder are left intact.


## 0.8.2 — server-side 403 handling

Real Home Assistant 0.8.1 logs showed the R2 **GET login form returns HTTP
403**, while the mobile v2 API and the already working kWh gas sensors
continue to respond successfully. The 0.8.2 R2 login sends a browser-style
`User-Agent` and HTML Accept headers on the login page, keeping JSON/XHR
headers on JSON web requests.

HTTP 403 and 429 cause a two-hour local retry cooldown (without network
traffic) so the optional web Smc and ACS Comfort components do not hammer
a rejecting server every 30 minutes. A login session is only considered
successful after the authenticated form response. This is a compatibility
attempt, **not proof** that the remote web portal is available to the
specific account. If the web server continues returning 403, both web
dependent features correctly remain unavailable. The mobile API, existing
entity IDs, legacy Ariston integration and Recorder remain untouched.


## 0.8.3 — Comfort ACS: same dropdown semantics as the legacy select

The working R2 login and direct physical Smc readings are retained unchanged.
Field logs for 0.8.2 show **only** the ACS Comfort web menu parser failing
with `Unexpected ACS Comfort value`. The previous integration mapped
`U6_9_2` through `dropDownOptions` (numeric value + localized text).
0.8.3 accepts strictly recognized integer/decimal/decimal-string values,
or an exact unique match of the web response to a declared option label.
No arbitrary value guesses, and no reuse of unrelated mobile `DhwMode`.

The binary Comfort ACS switch still writes **only** 0 OFF and 2 Always,
with one verified write and no retry; a current timed mode (1) intentionally
keeps the switch unavailable. If the server returns a different structure,
an additional redacted `comfort_acs_menu_probe` reports only scalar kind
and option-value types, not credentials or menu values. A select with all
three modes may later be offered if the real valve is configured to TIME.

The cloud weekly schedule continues to be readable but **not editable**:
the historical custom integration only implements the ChZn1 GET route;
there is no verified boiler-specific schedule write contract yet. Preserve
the original Cube S plan and never send an experimental setter.


## 0.8.4 — Smc-only gas entities and clock-aligned refresh

On-device tests confirmed the four `asPhysicalUnit` Smc readings and real
ACS Comfort switch. The four redundant mobile **kWh gas entities are no
longer created**, and the mobile gas-sequence coordinator is no longer
started. Source code for reading mobile diagnostic sequences remains
available for comparisons, but those values are not exposed as sensors.
Home Assistant can retain obsolete kWh *entity registry* entries from
past installations; remove only those optional old Ariston Cube entries
manually after verifying 0.8.4. No entity IDs, Recorder rows or the separate
legacy `ariston` integration are altered by the update.

Comfort ACS polls U6_9_2 every **5 minutes**, down from 30 minutes, while
a user-originated ON/OFF command still includes immediate readback.
Changes through the phone app can take up to about five minutes plus
cloud propagation to appear in Home Assistant.

Smc reads no longer depend on the most recent Home Assistant restart time.
The integration reads once at startup, then at local even hours
**02:10, 02:40, 04:10, 04:40, …, 22:10, 22:40**, capturing completed
2h cloud slots with one confirmation poll if Ariston uploads late.
A six-hour fallback remains for abnormal missed clock callbacks. All
scheduled event listeners are unsubscribed when the integration is unloaded.
The existing Smc sensor unique IDs stay unchanged; this release still does
**not** register a lifetime gas meter with Home Assistant Energy.

Editing Cube S timeProgs ChZn1 is separate unfinished work requiring
a verified cloud schedule-write contract and safe readback.

## 0.8.5 — experimental persistent, Energy-compatible gas statistics

Web ACS Comfort now polls every **15 minutes**, a compromise between
cloud load and external changes; user actions perform immediate verified
readback. Mobile and web login remain separate because the mobile v2
bearer token and R2 cookie/anti-CSRF login are different protocols.

### New two gas totals (different from raw Smc period reports)

- Gas riscaldamento cumulativo (Smc)
- Gas ACS cumulativo (Smc)

The raw period-report sensors retain their Smc units, names and IDs.
The two NEW totals are expressed as **m³ at standard conditions**: each
cloud Smc corresponds numerically to exactly one standard cubic metre.
This is volume, not a kWh conversion. Home Assistant requires its canonical
m³ unit to accept device_class GAS statistics. An attribute explicitly
records that these are standard, not uncorrected line-volume cubic metres.

The totals have state_class TOTAL (without last_reset), because the
server can correct historical bucket readings up or down. The Recorder
then records the difference instead of interpreting a correction as a reset.

A private HA Store holds cumulative values and the exact date/2h-slot
amounts for the past three days. We persist the updated checkpoint
before publishing sensor states, so restarts do not replay a bucket.

**Fail-closed limitation:** CurrentDay does not provide the previous day's
22:00-00:00 interval after the reset. The integration will not publish
an incomplete lifetime total unless the web histogram also exposes a
verifiable PreviousDay series containing the final bucket for both
heating and ACS. This capability is UNVERIFIED on the live account.
When missing, the two new cumulative sensors are unavailable while
the four tested raw Smc sensors remain fully functional.
Safe period names CurrentDay/PreviousDay are exposed for diagnostics.
A multi-day unfilled gap permanently suspends publication.

**Historical Home Assistant statistics are not migrated.** They remain
in Recorder under their prior statistic IDs and units. Before any migration
we need the exact IDs, compatible units and a backup. No automatic
database rewrite or unsafe ID reassignment is done.

No merge to main or release candidate while this accounting path remains
untested on the boiler. Cube S timetable writes also remain unverified.

## 0.8.6 — midnight gas-report day identity corrected

Field observation: the original Ariston 'CurrentDay' total still belongs
to the previous calendar day from 00:00 until the daily report switches
at **02:00**. The 22:00-00:00 Smc bucket is published at midnight.
The integration now polls Smc at 00:10 and 00:40, too. During 00:00-02:00
it attributes CurrentDay's final 12 buckets to **yesterday**.
At 02:10 it resumes CurrentDay as today's 00:00-02:00 interval; the
persistent totals NEVER reset when the vendor's daily report resets.

A slot is keyed by exact calendar date + usage (heating/DHW) + 0..11
two-hour bucket index: adjacent slots can hold identical values and
both contribute, whereas rereading the same slot adds nothing.
Cloud corrections within a bucket apply only the signed difference.

Persistence and outage limits: the ledger stores each observed slot before
publishing the Energy-compatible state. If HA is offline across the 00-02
window, the final 22-00 bucket can only be reconstructed if the gateway
also provides a real PreviousDay report. Otherwise the lifetime total
is withheld instead of silently missing gas volume. This has NOT yet
been field-tested across midnight on this particular installation.

Raw Smc report entities remain independent and carry a `giorno_riferimento`
attribute showing the vendor's actual report date. Cumulative entities
start their own new history; old Recorder Energy statistics are not
automatically transferred. Main branch and legacy integration untouched.
