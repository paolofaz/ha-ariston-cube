# Ariston Cube per Home Assistant

**Release candidate: 0.9.0-rc.1** — Ariston CLAS ONE 30L + Cube S.
Testata con Home Assistant Container / Core 2026.10.4. Le API Ariston
utilizzate non sono pubblicamente garantite dal produttore.

## Pre-release / HACS

Il codice RC è su **main**. Per installarlo tramite HACS, crea una
**GitHub pre-release** dal commit attuale di main con il tag esatto
**v0.9.0-rc.1**. Seleziona poi la pre-release in HACS (attiva la
visualizzazione beta se necessario) e riavvia completamente HA.
**Non cancellare la configurazione Ariston Cube né la vecchia integrazione
ariston.** Conserva i file .storage.

## Entità della RC

| Tipo | Scopo |
|---|---|
| climate | Cube S, riscaldamento e setpoint ambiente |
| water_heater | **Solo setpoint ACS**, 36–60 °C, passi di 1 °C |
| switch | Comfort ACS separato; termoregolazione automatica |
| number | Preset Comfort ed Economy del riscaldamento |
| select | Modalità caldaia |
| binary_sensor | Richiesta riscaldamento e fiamma |
| sensor | Temperature, pressione, programma settimanale e **due cumulativi Smc più due ultime fasce biorarie Smc** |
| calendar | Programma settimanale Cube S in **sola lettura** |

Rimossi: i due **sensori gas giornalieri Smc**, il vecchio **number
ACS**, il sensore di debug notturno. Solo le loro voci nel registro
entità Ariston Cube vengono rimosse in modo mirato; nessun dato Recorder
viene cancellato. Il sensore storico di sola lettura DhwTemp rimane
per retrocompatibilità con dashboard e automazioni.

## ACS: water_heater con solo controllo temperatura

Il water_heater supporta esclusivamente **TARGET_TEMPERATURE**,
senza menu per modalità operative, ECO, on/off o fasce.
Scrive il campo DhwTemp usando il vecchio comando già verificato,
con limiti locali/cloud, lettura prima della scrittura e
verifica dopo un solo POST. La temperatura effettiva
dell'accumulo viene mostrata solo se DhwStorageTemperature è disponibile.
DhwMode rimane informativo, non modificabile.

**Comfort ACS resta uno switch indipendente**: non equivale a
spegnere o accendere l'intero riscaldatore. Se il portale web riporta
Comfort temporizzato (codice 1), lo switch non inventa un valore ON/OFF.
Aggiorna eventuali automazioni del vecchio number ACS per usare
il servizio water_heater.set_temperature.

### Scheda ACS opzionale: cursore + pulsante Comfort

La release comprende la scheda custom **ariston-cube-acs-card**.
Mostra i due controlli nello stesso pannello, ma continua a comandare
le due entità distinte. Non modifica automaticamente alcuna dashboard.

Dopo aver cercato gli ID effettivi in Strumenti per sviluppatori > Stati:

~~~yaml
type: custom:ariston-cube-acs-card
title: Acqua calda sanitaria
entity: water_heater.SOSTITUISCI_CON_ID_REALE
comfort_entity: switch.SOSTITUISCI_CON_ID_REALE_COMFORT
~~~

La risorsa viene registrata automaticamente nelle dashboard in
modalità Storage. Se Lovelace usa risorse YAML, aggiungi:

~~~yaml
resources:
  - url: /ariston_cube/ariston-cube-acs-card.js?v=0.9.0-rc.1
    type: module
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=0.9.0-rc.1
    type: module
~~~

La scheda ariston-cube-weekly-card rimane una timeline **sola lettura**.
Se la risorsa era già registrata con un vecchio numero di versione,
aggiorna la query della risorsa e ricarica la dashboard.

## Gas: Smc cumulativi, senza consumi giornalieri duplicati

I due cumulativi usano esclusivamente i valori Smc fisici
di asPhysicalUnit.histogramData, **senza conversioni stimate da kWh**.
In Home Assistant: device_class GAS, state_class TOTAL,
unità numerica m³ riferita a metri cubi **standard** (Smc).
La lettura iniziale può includere ieri e oggi; è solo il punto iniziale
di una nuova serie, non il volume dall'installazione della caldaia.

Il registro salva in Home Assistant .storage ogni chiave
**giorno civile locale + riscaldamento/ACS + fascia di due ore**,
prima di pubblicare il totale. Fasce uguali si sommano, riletture
della stessa fascia no; correzioni applicano solo il delta.
Il comportamento del report web è stato verificato a cavallo della
mezzanotte 26–27 ottobre 2026: CurrentDay si azzera alle 00,
PreviousDay contiene anche la fascia finale 22–00.
Questo differisce dal vecchio giornaliero kWh calcolato da un'altra API.

Refresh Smc programmato alle **:10 e :40 di ogni ora pari**,
più lettura iniziale e fallback a sei ore. I due sensori delle
ultime fasce biorarie rimangono utili per controllare i cumulativi.
Il giornaliero potrà essere consultato dalle statistiche Energia.

In caso di schema cloud non valido, discontinuità o perdita di
checkpoint il cumulativo può risultare unavailable anziché
registrare Smc fittizi. **Non azzerare .storage senza prima
valutare le conseguenze.** I test verificano riavvii, correzioni,
fasce uguali e rollover, ma resta da verificare un incremento
live positivo della RC.

## Storico m³ da migrare in una fase separata

**Le vecchie statistiche Energia sono già in m³:** i vecchi sensori
erano stati convertiti dall'utente PRIMA di collegarli a Energia.
La nuova integrazione riceve direttamente Smc da Ariston.
Prima di unire le serie bisogna verificare i due vecchi
statistic_id, ultimo stato, unità, somma e continuità di lettura,
poi fare backup e decidere il passaggio senza salti o duplicazioni.

**Questa RC non modifica Recorder, statistics_meta, la dashboard
Energia né gli ID dei cumulativi della 0.8.9.**
Non disinstallare ancora la vecchia integrazione.

## Due sessioni, stesse credenziali

- API mobile /api/v2: token ar.authToken, temperatura, impianto,
  Cube S e programma settimanale.
- Portale web /R2: cookie e CSRF, letture Smc fisiche e Comfort ACS.

Un token mobile NON autentica /R2. Le sessioni sono isolate per
evitare di mescolare cookie/token e vengono rinnovate separatamente.
Le diagnostiche non espongono credenziali o risposte cloud integrali.

## Roadmap dopo questa pre-release

1. Validazione live dei cumulativi con fascia non nulla, riavvio e statistiche.
2. Migrazione guidata dello **storico Energia in m³**, con backup e veri ID.
3. **Per ultima**: scrittura delle fasce orarie Cube S, previa verifica
   dell'endpoint, readback e gestione degli errori. La RC non
   modifica la programmazione della caldaia.

## Sviluppo

~~~bash
python -m pip install pytest aiohttp
python -m compileall -q custom_components/ariston_cube tests
pytest -q
~~~

I test automatici non sostituiscono le prove sul dispositivo.
