# Ariston Cube per Home Assistant

**Versione 1.0.0** — Ariston CLAS ONE 30L + Cube S.
Verificata con Home Assistant Container / Core 2026.10.4.
Le API Ariston utilizzate non sono pubblicamente garantite dal produttore.
La versione 1.0.0 consolida il conteggio Smc cumulativo, i controlli
riscaldamento/ACS e il selettore AUTO/Manuale. La scrittura della
programmazione Cube S resta volutamente esclusa.

## Installazione / HACS

Il codice della 1.0.0 è destinato a **main**.
Per distribuire tramite HACS serve una release GitHub che punti al commit
della 1.0.0 e abbia tag **v1.0.0** (non riutilizzare i tag RC precedenti).
Selezionare la release in HACS e riavviare Home Assistant.
Non cancellare la configurazione Ariston Cube, il database Recorder
né i file `.storage` del registro gas: contengono dati persistenti.
Conservare il backup pre-migrazione delle statistiche Energia.

## Entità della versione 1.0.0

| Tipo | Scopo |
|---|---|
| climate | Cube S, riscaldamento e setpoint ambiente |
| water_heater | **Solo setpoint ACS**, 36–60 °C, passi di 1 °C |
| switch | Comfort ACS separato; termoregolazione automatica |
| number | Preset Comfort ed Economy del riscaldamento |
| select | Modalità caldaia (estate/inverno/spenta) e modalità riscaldamento Cube S (AUTO/Manuale) |
| binary_sensor | Richiesta riscaldamento e fiamma |
| sensor | Temperature, pressione, programma settimanale e **due cumulativi Smc** |
| calendar | Programma settimanale Cube S in **sola lettura** |

Rimossi: i due **sensori gas giornalieri Smc**, i due sensori delle
**fasce biorarie Smc**, il vecchio **number ACS** e il sensore di
debug notturno. Solo le loro voci nel registro entità Ariston Cube
vengono rimosse in modo mirato; nessun dato Recorder viene cancellato. Il sensore storico di sola lettura DhwTemp rimane
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
  - url: /ariston_cube/ariston-cube-acs-card.js?v=1.0.0
    type: module
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.0.0
    type: module
~~~

### Nascondere «Spento» senza falsificare lo stato ACS

Home Assistant visualizza lo stato `current_operation` del dominio
`water_heater`. Il dato `DhwMode` può essere `off` e viene tradotto
come «Spento», anche se il setpoint è configurabile. Non falsifichiamo
questo dato cloud e non aggiungiamo modalità fittizie solo per la UI.

Se in una **dashboard modificabile** interessa mostrare soltanto
la temperatura impostata, utilizzare una scheda Tile:

~~~yaml
type: tile
entity: water_heater.SOSTITUISCI_CON_ID_REALE
name: Acqua calda sanitaria
state_content: temperature
features:
  - type: target-temperature
~~~

In alternativa, la scheda `custom:ariston-cube-acs-card` già inclusa
mostra il valore e il cursore con il controllo Comfort separato,
senza riportare «Spento». La schermata «Controlli» generata
automaticamente nella pagina del dispositivo usa il rendering standard
di Home Assistant e non è personalizzabile da questa integrazione.

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
più lettura iniziale e fallback a sei ore. La rimozione dei sensori
biorari riguarda solo le entità: il registro persistente continua a
utilizzare le 12 fasce del report web per comporre i cumulativi.
Il giornaliero può essere consultato dalle statistiche Energia.

In caso di schema cloud non valido, discontinuità o perdita di
checkpoint il cumulativo può risultare unavailable anziché
registrare Smc fittizi. **Non azzerare .storage senza prima
valutare le conseguenze.** I test verificano riavvii, correzioni,
fasce uguali e rollover, ma resta da verificare un incremento
live positivo della RC.

## Continuità dello storico Energia

Le vecchie statistiche Energia erano **già in m³**, derivate da una
conversione dei consumi kWh nella precedente installazione.
L'installazione di riferimento ha migrato manualmente lo storico SQLite
sugli statistic_id dei due cumulativi Ariston Cube dopo backup e
verifica dei raccordi. **Questa integrazione non esegue migrazioni DB**
e non modifica `statistics_meta`, Recorder o la dashboard Energia.
Non ripetere la migrazione SQL su un impianto già migrato.
Conservare il backup pre-migrazione. Sull'impianto di riferimento la
vecchia integrazione Ariston è stata dismessa e i cumulativi continuano
a crescere; prima di una dismissione su altri impianti verificare sempre
template, automazioni, dashboard e statistiche.

## Modalità riscaldamento e sensore fiamma

Il selettore **Modalità riscaldamento** usa lo stesso `ZoneMode` del
`climate` Cube S: AUTO=3 (programma settimanale esistente) e Manuale=2.
Il cambio di opzione chiama lo stesso comando verificato, con lettura fresca
e readback. Le due entità restano sincronizzate senza comandi automatici
aggiuntivi. La selezione è indisponibile con impianto in estate/off, zona
spenta/Economy o se il cloud non dichiara entrambe le opzioni.
La modalità globale estate/inverno resta nel selettore **Modalità caldaia**.
Nessuna scrittura della programmazione settimanale è introdotta.

Il sensore **Fiamma** legge `IsFlameOn` a livello impianto (zona 0),
quindi rileva il bruciatore generale e **non distingue ACS da riscaldamento**.
Il sensore `ZoneHeatRequest` è invece riferito alla zona 1:
`climate.hvac_action = heating` richiede sia la richiesta zona sia
la fiamma, ma non costituisce una misura indipendente della ripartizione
della fiamma. Non viene creato un sensore ACS dedotto da questi soli segnali.

## Due sessioni, stesse credenziali

- API mobile /api/v2: token ar.authToken, temperatura, impianto,
  Cube S e programma settimanale.
- Portale web /R2: cookie e CSRF, letture Smc fisiche e Comfort ACS.

Un token mobile NON autentica /R2. Le sessioni sono isolate per
evitare di mescolare cookie/token e vengono rinnovate separatamente.
Le diagnostiche non espongono credenziali o risposte cloud integrali.

## Roadmap dopo la 1.0.0

- Consolidare il recupero dei cumulativi dopo interruzioni di HA superiori
  all'orizzonte disponibile dal cloud, senza alterare silenziosamente Energia.
- In un branch **separato e non destinato alla 1.0.0**, studiare la modifica
  delle fasce settimanali Cube S. Prima di qualsiasi comando reale occorre
  verificare endpoint, payload, lettura immediatamente precedente, readback,
  confronto con la programmazione originale e piano di recupero.
  Nessuna scrittura delle fasce orarie è presente nella 1.0.0.

## Sviluppo

~~~bash
python -m pip install pytest aiohttp
python -m compileall -q custom_components/ariston_cube tests
pytest -q
~~~

I test automatici non sostituiscono le prove sul dispositivo.
