# Ariston Cube for Home Assistant

A new, minimal custom integration for the **Ariston CLAS ONE 30L + Cube S** via the legacy Ariston NET cloud API.

> **Development status: experimental / first writable build (0.3.0).**
> Login and the original five read-only sensors were successfully tested on a
> real CLAS ONE/Cube S on 26 October 2026. The additional climate and water
> heater entities have **not yet** been validated on the live boiler. Do not
> replace the existing Ariston integration or remove its Recorder history.
> The only write services enabled are manual heating comfort temperature and
> ACS setpoint. **Those writes have not been verified on a real boiler yet.**

## Milestone 1 and 2 status

- Configuration from **Settings > Devices & services > Add integration** (no YAML).
- Token-based Ariston mobile API authentication and plant selection.
- Token-authenticated asynchronous HTTP calls and 60-second coordinator polling.
- Five read-only temperature/status sensors, plus writable Cube S `climate`
  and ACS `water_heater` entities (temperature setpoints only).
- No automated writes, scheduling changes, mode changes, gas conversions or automations.
  Temperature changes are sent only after an explicit Home Assistant service call.

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

## Milestone 2: thermostat and hot water entities

This branch displays two new Home Assistant entity types:

- `climate.ariston_cube_cube_s`: room and target temperature, plant-aware
  heating mode, burner/request-based HVAC action, and raw Comfort/Economy
  values as attributes.
- `water_heater.ariston_cube_acqua_calda_sanitaria`: ACS setpoint,
  available storage reading (if supported) and Ariston DHW mode; Comfort
  and Economy ACS settings are attributes.

**As of 0.3.0, both expose setpoint services**. Mode changes are still unavailable.
The thermostat write requires the Cube S to be in manual heating mode and does
not change the weekly schedule. Avoid parallel automatic control loops with the
older integration.

The cloud plant's summer mode takes precedence over any zone setting.
Unknown status is not silently presented as a valid operating state.

## Write safety

`commands.py` validates each explicitly requested setpoint operation
against the established `dataItems/<plant>/set` JSON contract. It checks a
fresh previous value, cloud minimum/maximum and temperature step, local hard
bounds, fixed zone and active manual heating mode. It does not auto-retry
writes or alter the Cube S scheduler.

The real command path is enabled from 0.3.0 but has not yet been confirmed on
a live Cube S. Do not use the experimental entities in production automations.

## Home Assistant 2026.10 compatibility / troubleshooting

The 2026.10 Home Assistant platform APIs still use `temperature_unit`,
`current_temperature`, and `target_temperature` for `climate` and
`water_heater`. The `native_*` replacements are scheduled for 2026.11,
so this milestone deliberately uses the older, compatible names.

To verify the new entities, open **Settings > Devices & services > Entities**
or **Developer tools > States** and filter by `ariston_cube`, `climate.`
and `water_heater.`. The physical device page is not guaranteed to show
a **Controls** section because the entity platforms failed to load or the installed version is stale.
With 0.3.0 both new entities advertise a temperature setpoint feature, so a
control panel should appear if they register successfully.

Updating custom-component code requires a **full Home Assistant restart**,
not just reload of the integration. The domain-specific logs must not show
`async_setup_entry did not return boolean` or `already been setup!`.

The legacy `ariston` component is separate from `ariston_cube`. A
`500 InternalError` received by the old component is a different cloud
request and can reflect gateway or rate issues. Avoid sustained parallel
high-frequency polling against the same plant.

## Verifying HA platform loading

Enable `logger.logs.custom_components.ariston_cube: debug` and do a full
Home Assistant restart. Logs now show whether the installed `__init__.py`
actually uses all four platforms and whether Home Assistant invokes and
accepts the `climate` and `water_heater` entities:

- `Ariston Cube 0.3.0 starting; platforms=sensor, binary_sensor, climate, water_heater`
- `Ariston Cube climate platform setup invoked`
- `Ariston Cube climate entity added to Home Assistant`
- `Ariston Cube water_heater platform setup invoked`
- `Ariston Cube water_heater entity added to Home Assistant`

The absence of the first line means the old `__init__.py` may still be
running. The absence of a platform or entity line distinguishes a platform
loading failure from entity registration trouble. Check the
`/config/custom_components/ariston_cube/manifest.json` version is 0.3.0.
The five previous sensors remain unchanged.

## Milestone 3: write test for temperature setpoints

**This experimental build enables user-triggered setpoint changes.** The
`climate` entity exposes `TARGET_TEMPERATURE` and sends updates to
`ZoneComfortTemp` for heating zone 1 **only when both the plant and the Cube
S are in manual heating mode**. It deliberately does not force a mode change
or change the time programme. If the Cube S is running its weekly programme,
Home Assistant returns an explanatory error instead of altering the schedule.

The `water_heater` entity exposes `TARGET_TEMPERATURE` and updates only
`DhwTemp`. DHW mode controls remain disabled.

Before any write, the client reads the current cloud snapshot and validates
the device-supplied min/max, step, and previous value. It sends a single
`dataItems/set` request with the documented `prevValue`, `zone` and
`features` fields, then performs one fresh read. It **never retries** a
write automatically. If cloud confirmation is delayed, the UI reports that
the write was submitted but not confirmed, and recommends not repeating it.

For the first on-device test, change ACS by only 1°C within permitted values
and check the Cube S/Ariston NET app shows the same result. The old integration
may see temporary gateway HTTP 500 errors during simultaneous polling. Avoid
continuous stress testing, and leave the old entity history intact.
