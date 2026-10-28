# Ariston Cube per Home Assistant

> **Versione sperimentale 1.3.0-rc.1**, basata direttamente sulla
> **stabile v1.2.0**. Rende i comandi Lovelace subito reattivi e riduce
> le Azioni a sei servizi essenziali. Tutto l'editor Cube S e
> l'allineamento automatico gas restano inclusi e invariati.
> La nuova reattività è stata simulata nei test; richiede ancora una
> prova reale prima della promozione a stabile 1.3.0.
> [Novità e istruzioni di prova](docs/releases/v1.3.0-rc.1.md).

Integrazione indipendente per caldaie **Ariston CLAS ONE 30L**
e termostato **Cube S**. Collaudata con Home Assistant Container / Core
2026.10.4. **Non è un progetto ufficiale Ariston** e usa API cloud
che possono variare.

## Funzionalità

- Termostato `climate`: temperatura ambiente, setpoint, OFF,
  HEAT (Manuale) e AUTO (programmazione settimanale del Cube S).
- Selettore separato **AUTO / Manuale**, oltre alla modalità generale
  della caldaia (inverno, estate, spenta).
- Riscaldamento Comfort/Economy con due entità `number`.
- Acqua calda sanitaria con entità `water_heater` per il setpoint
  (36–60 °C, passi da 1 °C), più switch Comfort ACS separato.
- Switch termoregolazione automatica, temperature, stato bruciatore,
  richiesta riscaldamento, pressione e altre letture disponibili.
- Programma settimanale reale Cube S: `sensor`, `calendar` e
  scheda Lovelace modificabile con **Sposta orario**, **Aggiungi fascia**,
  **Elimina fascia** e **Clona giorno** su più destinazioni.
- Due sensori cumulativi Smc distinti per riscaldamento e ACS, con
  attribuzione automatica corretta delle ore nella dashboard Energia.

## Installazione con HACS

1. Aggiungi `https://github.com/paolofaz/ha-ariston-cube` come
   repository personalizzato di tipo **Integrazione**, se non già presente.
2. Installa la stabile **1.2.0** oppure seleziona espressamente
   **1.3.0-rc.1** per provare la nuova reattività.
3. **Riavvia Home Assistant** e verifica la configurazione in
   Impostazioni → Dispositivi e servizi → Ariston Cube.
4. Mantieni la voce di configurazione già esistente, i checkpoint
   in `.storage` e le statistiche Recorder: **non serve azzerare
   sensori, creare nuove entità o modificare Energia**.

La risorsa JS settimanale viene registrata automaticamente nelle
dashboard Lovelace in modalità storage. Per dashboard YAML:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.3.0-rc.1
    type: module
```

La card si usa così (sostituisci l'ID con quello del tuo sensore reale):

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.TUO_SENSORE_PROGRAMMA_SETTIMANALE
title: Fasce riscaldamento Cube S
```

Il browser potrebbe richiedere un refresh per caricare la nuova versione.

## Reattività Lovelace in 1.3.0-rc.1

Quando cambi una temperatura o la modalità AUTO/Manuale, il nuovo
valore appare **immediatamente nella UI**, con l'attributo
`ariston_comando_in_corso: true` e
`ariston_comando_esito: in_attesa`.

Il cloud riceve **lo stesso comando verificato di prima**: lettura
fresca, singolo POST, rilettura e confronto. Durante l'attesa,
il sensore mostra una **previsione temporanea**, ma lo stato cloud
verificato non viene alterato:

- se il cloud conferma, la UI mostra `confermato`;
- se il cloud rifiuta, torna il valore precedente e mostra `rifiutato`;
- se la risposta è incerta o va in timeout, torna l'ultimo valore
  verificato e mostra `non_confermato`; **nessuna ritrasmissione
  automatica**.

Finché un comando è in corso, un secondo comando sovrapposto
viene rifiutato. L'effetto fisico sul Cube S può richiedere
qualche secondo in più: vedere il valore in Lovelace **non significa**
che la caldaia abbia già applicato la modifica.

## Editor settimanale Cube S

Apri la scheda e premi **Modifica fasce**: i cambi di orario sono
a intervalli di **15 minuti**. Per aggiungere una fascia devi indicare
inizio, fine e preset Comfort/Economy; per eliminarla scegli
il punto da rimuovere. Con **Clona giorno** selezioni il giorno sorgente
e uno o più giorni destinazione.

Ogni scrittura richiede **Anteprima**, verifica fingerprint cloud
dell'intera settimana, conferma esplicita, **un solo POST** e
controllo dei sette giorni. Se un salvataggio restituisce un esito
incerto, verifica prima il programma nell'app Ariston e **non
ritentare alla cieca**.

La card usa le due azioni definitive per sposta/aggiungi/elimina;
le vecchie azioni sperimentali non servono più.

## Azioni Home Assistant disponibili (1.3)

| Azione | Funzione |
| --- | --- |
| `ariston_cube.preview_weekly_change` | Anteprima di spostamento, aggiunta o eliminazione |
| `ariston_cube.write_weekly_change` | Salva una modifica dopo conferma |
| `ariston_cube.preview_weekly_clone` | Anteprima clonazione di un giorno |
| `ariston_cube.clone_weekly_days` | Clona su più giorni dopo conferma |
| `ariston_cube.inspect_automatic_energy_hour_alignment` | Stato ultime correzioni gas, **sola lettura** |
| `ariston_cube.inspect_energy_hour_alignment` | Statistiche gas di un'ora, **sola lettura** |

Non sono più registrati gli endpoint di prova né i servizi per
scrivere **manualmente** statistiche gas. L'automatismo continua a
funzionare internamente. Dopo un aggiornamento, **riavvia Home Assistant**
per far sparire le vecchie azioni dalla lista.

## Gas ed Energia

Ariston invia i consumi fisici in **Smc**, divisi per intervalli di
due ore. L'integrazione acquisisce i dati intorno alle **:10 e :40
di ogni ora pari** e conserva i checkpoint nella directory `.storage`.

L'incremento che Home Assistant attribuirebbe inizialmente
all'ora successiva viene corretto **alle :15 dell'ora dispari
successiva**, usando le statistiche Recorder già compilate.
Esempio: consumo Ariston **14–16**, rilevato nella fascia HA
**16–17**, automaticamente attribuito alla fascia **15–16**
alle 17:15.

La procedura controlla le quantità, l'esatta finestra Ariston,
le differenze di stato/somma e le identità dei due sensori.
Se dati mancanti, consumo zero, valori già allineati, incongruenze
o passaggio d'ora non supportato: **nessuna correzione forzata**.
Non ci sono ritentativi automatici né recuperi di fasce perse
durante un'interruzione.

I due sensori cumulativi (`device_class: gas`,
`state_class: total`, m³ = Smc) mantengono **gli stessi entity ID,
unique ID, ledger e offset**. Non cancellare Recorder né i
checkpoint sotto `.storage`. I dati della vecchia integrazione
non vengono riscritti retroattivamente.

Per verificare gli ultimi otto cicli senza scrivere:

```yaml
action: ariston_cube.inspect_automatic_energy_hour_alignment
```

Per ispezionare un'ora UTC specifica (ad esempio 15–16 italiane
del 28 ottobre 2026):

```yaml
action: ariston_cube.inspect_energy_hour_alignment
data:
  target_start: "2026-10-28T14:00:00+00:00"
```

## Architettura e limiti

Le due sessioni cloud rimangono separate: API mobile `/api/v2`
per stato e comandi, portale `/R2` per consumo Smc e Comfort ACS.
Il token della API mobile non viene riutilizzato per la sessione web.

Il segnale bruciatore `IsFlameOn` è dell'intera caldaia;
la richiesta di riscaldamento `ZoneHeatRequest` riguarda la zona.
La scheda ACS espone soltanto il target temperatura, senza
inventare modalità non supportate.

Le nuove funzionalità 1.3.0-rc.1 sono testate offline ma richiedono
una verifica sul dispositivo reale prima di raggiungere `main`.

## Sviluppo e test

```bash
python -m pip install pytest aiohttp
python -m compileall -q custom_components/ariston_cube tests
python -m pytest -q
node --test tests/test_weekly_editor.mjs
```

Sorgenti e segnalazioni: https://github.com/paolofaz/ha-ariston-cube
