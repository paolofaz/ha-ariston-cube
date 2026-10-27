# Cube S weekly timetable Lovelace card

The card keeps the original **seven-day Comfort/Economy timeline**.
In experimental Ariston Cube **1.1.0-rc.3**, tap a weekday or
**Modifica fasce** to open an editor directly inside the same card.

You can currently **move one existing start time per save**.
Choose a weekday, select an existing boundary and a new time,
then click **Anteprima** to read the actual cloud timetable.
After reviewing the old/new schedule, click **Salva sul Cube S**
and accept the confirmation dialogue. The backend checks the fresh
source fingerprint, sends at most **one POST**, reads back all seven
days, and rejects unconfirmed outcomes.

You cannot yet add/delete boundaries or edit the Comfort/Economy
preset of a slice through the card. Changing a midnight boundary is
intentionally excluded from this first editor. Changing these extra
properties requires separate field verification.

**Reinstalling stable software does not roll back schedule changes
persisted on the boiler.** If a write is rejected or unconfirmed,
inspect the official Ariston app before trying any further write.

## Installation using the bundled version

A Storage-mode dashboard automatically registers
`/ariston_cube/ariston-cube-weekly-card.js?v=1.1.0-rc.3`.
The integration updates an older resource URL on installation.
For YAML resource mode register the following module manually:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.1.0-rc.3
    type: module
```

Add a Manual card:

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.SOSTITUISCI_CON_IL_TUO_ID_REALE
title: Programmazione settimanale Cube S
```

Use your actual weekly-program sensor entity ID from Home Assistant.

## Alternate manual card installation

Copy `frontend/ariston-cube-weekly-card.js` to
`/config/www/ariston-cube-weekly-card.js`, register
`/local/ariston-cube-weekly-card.js?v=1.1.0-rc.3` as
a JavaScript module, and use the same card YAML.

**Don't register both module URLs at once.** If you return to stable
1.0.1, restore the module version to `?v=1.0.1` in the Lovelace
resource settings if necessary, then reload the dashboard.
