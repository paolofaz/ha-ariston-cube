# Scheda settimanale Ariston Cube S · Home Assistant

La scheda Lovelace `custom:ariston-cube-weekly-card` è inclusa
nell'integrazione **Ariston Cube 1.3.0 stabile**. Mostra il programma reale
settimanale del Cube S e permette di modificarlo con conferma esplicita.

## Funzioni della scheda

- **Sposta orario**: sposta un cambio Comfort/Economy esistente su uno
  degli orari di 15 minuti.
- **Aggiungi fascia**: scegli ora iniziale, ora finale e preset
  Comfort/Economy; il programma precedente riprende all'ora finale.
- **Elimina fascia**: rimuovi un cambio orario; viene eliminata anche
  l'eventuale fascia di ripristino diventata ridondante.
- **Clona giorno**: scegli un giorno sorgente e uno o più giorni
  destinatari. La scheda confronta gli orari **prima/dopo** per ciascuno.

Ogni operazione segue **Anteprima → approvazione → un singolo POST cloud**
con validazione del fingerprint e lettura dei programmi di tutti
sette i giorni. Se una scrittura ha esito incerto, consulta l'app
Ariston prima di tentare un'altra modifica.

## Installazione automatica e manuale

Con dashboard **Storage**, la risorsa JS è registrata automaticamente.
Con dashboard **YAML**, aggiungi una risorsa di tipo modulo:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.3.0
    type: module
```

Per usare la scheda, aggiungi manualmente (sostituendo l'ID
con quello reale del sensore settimanale):

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.TUO_SENSORE_SETTIMANALE
title: Programma riscaldamento Cube S
```

Se visualizzi una vecchia versione, aggiorna l'URL della risorsa e
svuota la cache del browser.

## Azioni sottostanti

Le operazioni usano **soltanto** le quattro azioni ufficiali:
`ariston_cube.preview_weekly_change`,
`ariston_cube.write_weekly_change`,
`ariston_cube.preview_weekly_clone` e
`ariston_cube.clone_weekly_days`.

Non richiedono più azioni `TEST` o API sperimentali. Il salvataggio
non viene mai ritentato automaticamente dopo una risposta ambigua.

Per il gas restano due azioni diagnostiche in sola lettura;
l'automatismo gas della stabile 1.2.0 è invariato.

[README principale](../README.md) ·
[Note della stabile 1.3.0](../docs/releases/v1.3.0.md)
