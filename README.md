# Ariston Cube for Home Assistant

Experimental custom integration for **Ariston CLAS ONE 30L + Cube S** via the Ariston NET mobile API.

## Version 0.4.0 — practical controls

Login and the five original sensors were tested on the real boiler. The Cube S
`climate` temperature setting was also tested successfully on 2026-10-26.
This version changes the domestic hot water control to a **number**, not another
thermostat.

Entities:
- `climate` Cube S: current and target room temperature, heating state,
  and user-requested Comfort temperature with readback.
- `number` ACS temperature: 36–60 °C cap, 1 °C steps. Dynamic server
  minimum/maximum are intersected with these bounds.
- `number` heating Economy temperature: 10–30 °C cap, 0.5 °C steps,
  shown only when the cloud supplies a valid current value.
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
delete and re-add the Ariston Cube config entry. Verify manifest version 0.4.0.

## Safeguards for controls

The client performs one fresh authenticated read, validates both server-side
limits and local temperature caps, submits at most one
`/api/v2/remote/dataItems/{plant}/set` request using the previous value,
then reads back the cloud result. An uncertain write is **never retried
automatically**. The heating Comfort and Economy writes require manual
heating mode, so the Cube S weekly schedule is not silently overwritten.
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
