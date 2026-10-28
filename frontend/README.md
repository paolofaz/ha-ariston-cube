# Cube S weekly timetable Lovelace card (stable 1.1.0)

The integration bundles `ariston-cube-weekly-card.js`. For storage-mode
Lovelace dashboards Home Assistant registers the resource automatically;
for YAML dashboards register the JavaScript resource manually.

## Editing the real weekly Comfort/Economy schedule

Tap **Modifica fasce** or select a weekday. The **Operazione** menu offers:

- **Sposta orario**: choose an existing boundary and a new 15-minute time.
- **Aggiungi fascia**: choose *start*, *end* and Comfort/Economy; the prior
  preset resumes at the end. Overlapping programmed boundaries are refused.
- **Elimina fascia**: remove a boundary. If it was an inserted temporary
  band whose adjacent restoration is redundant, remove that restoration too.
- **Clona giorno**: choose **Giorno sorgente**, then check any number of
  other days (up to six). Example: Monday to Wednesday, Friday and Sunday.
  The editor shows the old and new programme for each destination.

Every operation requires **Anteprima** and **explicit confirmation** before
the integration sends **one cloud POST**. The backend reads the entire
current weekly schedule and fingerprints it to reject stale changes. It
then reads back and verifies **all seven weekdays** after the write.

The confirmation popup shows the affected day or days and before/after
values. It does not contain a sentence about reverting to stable software.

After a confirmed write the editor stays open for another independent
preview and confirmation. If cloud write confirmation is ambiguous, the
editor blocks another write: **inspect the official Ariston app** first.
Cloud programme changes persist across software version changes.

**The multi-target clone action is newly added to v1.1.0 and has passed
offline and simulated cloud tests; it requires a deliberate live Cube S
field check.** The earlier move/add/remove operations were field-tested.

## Developer Tools / Actions (optional)

Use `ariston_cube.preview_weekly_clone` read-only:

```yaml
action: ariston_cube.preview_weekly_clone
data:
  source_day: 1
  destinations: [3, 5, 0]
```

Only `ariston_cube.clone_weekly_days` with the **same source/destinations**,
the returned `source_fingerprint` as `expected_fingerprint`, and
`confirm: true` sends a real one-shot cloud POST. The Lovelace card
handles the entire preview/confirmation procedure for you.

See [stable release notes](../docs/releases/v1.1.0.md).


## Manual fallback for YAML-mode dashboards

Copy the checked-in `frontend/ariston-cube-weekly-card.js` file to
Home Assistant's `/config/www/ariston-cube-weekly-card.js`.
In dashboard resources add this module URL:

```text
/local/ariston-cube-weekly-card.js
```

Then add a manual Lovelace card, replacing the placeholder with your
actual weekly-programme sensor entity ID:

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.SOSTITUISCI_CON_IL_TUO_ID_REALE
title: Fasce riscaldamento Cube S
```

Storage-mode Lovelace dashboards normally do **not** need these manual steps;
the integration registers the versioned resource automatically. After any
update, refresh the Home Assistant browser cache if the old card remains
visible.
