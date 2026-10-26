# Ariston Cube for Home Assistant

A new, minimal custom integration for the **Ariston CLAS ONE 30L + Cube S** via the legacy Ariston NET cloud API.

> **Development status: experimental / read-only prototype.**
> Login and the original five read-only sensors were successfully tested on a
> real CLAS ONE/Cube S on 26 October 2026. The additional climate and water
> heater entities have **not yet** been validated on the live boiler. Do not
> replace the existing Ariston integration or remove its Recorder history.
> No boiler control is implemented in this branch.

## Milestone 1 and 2 status

- Configuration from **Settings > Devices & services > Add integration** (no YAML).
- Token-based Ariston mobile API authentication and plant selection.
- Token-authenticated asynchronous HTTP calls and 60-second coordinator polling.
- Seven **read-only** entities: the original five sensors plus Cube S `climate`
  and domestic-hot-water `water_heater` entities.
- No writes, scheduling changes, gas conversions or automations. The climate and
  water-heater controls in the Home Assistant UI are informational for now.

## Installation for a separate test Home Assistant instance

1. Back up your Home Assistant configuration.
2. Copy the **custom_components/ariston_cube** directory into your Home Assistant
   configuration directory, usually mounted as **/config** inside its Docker container.
3. Restart Home Assistant.
4. Navigate to **Settings > Devices & services > Add integration > Ariston Cube**.
5. Enter your Ariston NET account credentials and select the boiler, if prompted.

The old **ariston** integration uses a different domain and is not modified. For
tests, avoid running two integrations aggressively against the same cloud account.
Use a disposable HA instance or an isolated configuration where possible.

## Intended next milestones

1. Validate expanded thermostat/DHW mode readings against **sanitized** CLAS ONE/Cube S fixtures.
2. Support Climate, comfort/economy setpoints, and DHW preheating with safe
   command acknowledgements and retry behaviour.
3. Replace dozens of legacy energy entities with **at most three energy totals**:
   heating, hot water, and boiler electricity (only if independently validated).
   Use persistent, de-duplicated interval records and Home Assistant long-term
   statistics. Do not assume the legacy energy2 series is electrical consumption.
4. Add read-only weekly scheduling, and investigate server-side program editing
   without introducing a second competing scheduler.
5. Migrate Recorder statistics separately and deliberately, not by renaming
   existing entities.

**Energy accounting is deliberately not enabled in milestone 1**: it requires
real raw data to establish the semantics of series IDs, timestamps, delayed
midnight resets and corrections.

## Data and privacy

Credentials remain in Home Assistant's config entry storage; they are not
embedded in source code or printed in logs. Use TLS verification and never expose bearer tokens or credentials in logs. Never attach live credentials, session cookies or unredacted
plant/gateway IDs to issues or test fixtures.

## Development

Run the parser and HTTP-contract tests without a Home Assistant installation:

    python -m pip install pytest aiohttp
    python -m compileall -q custom_components/ariston_cube
    pytest -q

The tests do not access the real cloud. Full HA integration tests and real device
verification are still required before calling this project production ready.

## Acknowledgements

The historical [Ariston NET remotethermo v2 integration](https://github.com/chomupashchuk/ariston-remotethermo-home-assistant-v2)
was consulted to understand observed API identifiers and request patterns.
The new implementation is independently structured and intentionally limited
in scope. The cloud endpoints are unofficial and subject to change.

## Milestone 2: read-only thermostat and hot water

This branch displays two new Home Assistant entity types:

- `climate.ariston_cube_cube_s`: room and target temperature, plant-aware
  heating mode, burner/request-based HVAC action, and raw Comfort/Economy
  values as attributes.
- `water_heater.ariston_cube_acqua_calda_sanitaria`: ACS setpoint,
  available storage reading (if supported) and Ariston DHW mode; Comfort
  and Economy ACS settings are attributes.

**They do not yet implement service calls to change temperature or mode.**
Avoid controlling them through Home Assistant automations; continue to use the
Cube S itself or the proven Ariston integration. No integration should impose
a second schedule while the Cube S is managing its own time program.

The cloud plant's summer mode takes precedence over any zone setting.
Unknown status is not silently presented as a valid operating state.

## Future write safety (not activated)

`commands.py` now contains a pure, offline-tested builder for the established
`dataItems/<plant>/set` JSON contract. It is **not imported or called by any
entity or the HTTP client**. It checks a current server-side previous value,
explicit server-provided minimum/maximum and temperature steps, local hard
bounds, the fixed zone and active manual heating mode. It does not auto-retry
writes or alter the Cube S scheduler.

Real writes require an intentionally separate, opt-in implementation and
careful validation on the specific boiler; installing this branch still
performs **read requests only**.
