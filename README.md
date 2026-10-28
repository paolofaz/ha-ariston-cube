# Ariston Cube · Home Assistant

[![Release](https://img.shields.io/github/v/release/paolofaz/ha-ariston-cube?label=versione%20stabile)](https://github.com/paolofaz/ha-ariston-cube/releases/latest)
[![CI](https://github.com/paolofaz/ha-ariston-cube/actions/workflows/ci.yml/badge.svg)](https://github.com/paolofaz/ha-ariston-cube/actions/workflows/ci.yml)
[![MIT License](https://img.shields.io/github/license/paolofaz/ha-ariston-cube)](LICENSE)

**Controllo del termostato Ariston Cube S, programmazione settimanale e consumi gas in Home Assistant.** Integrazione comunitaria per **Ariston CLAS ONE 30L + Cube S**, collegata ad Ariston NET.

> **Versione stabile: 1.3.0.** Comandi Lovelace reattivi, editor settimanale completo, clonazione dei giorni e allineamento automatico delle statistiche Energia del gas. Funzionalità verificate sul Cube S reale; il comportamento può variare con altri modelli o versioni cloud.
>
> **Progetto indipendente, non ufficiale Ariston.** Le API cloud potrebbero cambiare. L'interfaccia può mostrare temporaneamente un comando richiesto prima che la caldaia lo confermi.

**English:** Community Home Assistant integration for Ariston CLAS ONE 30L / Cube S. Includes responsive controls with cloud confirmation and rollback, a weekly schedule editor, multi-day cloning, separate heating/DHW gas totals, and guarded automatic Energy statistics alignment. See the [English quick guide](docs/README.en.md).

## Funzioni

| Area | Funzionalità |
| --- | --- |
| **Clima Cube S** | Temperatura ambiente, temperatura obiettivo, OFF / HEAT (Manuale) / AUTO (programma settimanale originale) |
| **Comandi reattivi** | Cambio immediato nella vista Lovelace, lettura cloud di conferma, ripristino in caso di errore |
| **Riscaldamento** | Temperature Comfort / Economy, selettore AUTO / Manuale, modalità generale della caldaia, termoregolazione |
| **Acqua calda** | Entità `water_heater` per target ACS, switch separato Comfort ACS |
| **Programma Cube S** | Sensore, calendario, scheda settimanale: sposta, aggiungi, elimina fasce e **Clona giorno** |
| **Gas ed Energia** | Due sensori cumulativi Smc (riscaldamento / ACS), attribuzione automatica corretta delle fasce biorarie |
| **Diagnostica** | Stato degli ultimi cicli automatici e ispezione in **sola lettura** delle statistiche di un'ora |

Non è necessario sostituire la programmazione interna del Cube S: **AUTO continua a seguire quella vera**.

## Compatibilità e prerequisiti

- **Hardware verificato:** Ariston CLAS ONE 30L con termostato Cube S, zona 1.
- **Home Assistant:** versione minima dichiarata a HACS **2026.10.0**; collaudata su **Home Assistant Core/Container 2026.10.4**.
- **HACS** per installazione e aggiornamenti (oppure installazione manuale).
- Account Ariston NET funzionante e accesso Internet per le API cloud.

Non viene garantito il supporto di altri modelli o installazioni multizona. Il gas è conteggiato dalle letture fisiche esposte dal cloud, non derivato da una conversione kWh → m³.

## Installazione

### Con HACS

1. In **HACS → menu ⋮ → Repository personalizzati**, aggiungi
   `https://github.com/paolofaz/ha-ariston-cube` come **Integrazione**. Finché HACS non approva l'inclusione nel catalogo predefinito, usa il repository personalizzato.
2. Installa **Ariston Cube**, scegliendo la release stabile più recente (**v1.3.0**).
3. **Riavvia Home Assistant**.
4. In **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**, cerca **Ariston Cube**; inserisci le credenziali Ariston NET e seleziona la caldaia.

**Aggiornamento dalla 1.2.0 o da una RC:** aggiorna e riavvia. **Non eliminare la configurazione**, la cartella `.storage` o il database Recorder; nessun reset dei sensori gas è necessario. I cambiamenti di programma salvati sul Cube S restano nel cloud.

### Installazione manuale

Copia l'intera directory `custom_components/ariston_cube/` sotto `<config>/custom_components/ariston_cube/` di Home Assistant, poi riavvia e configura l'integrazione. Mantieni `www/`, `strings.json` e `translations/` all'interno della cartella dell'integrazione.

## Comandi Lovelace: immediati ma verificati

Quando cambi **AUTO ↔ Manuale**, una temperatura o una modalità della caldaia, Lovelace mostra subito il valore richiesto, mentre il cloud Ariston riceve il comando.

Durante l'attesa le entità di controllo espongono:

```yaml
ariston_comando_in_corso: true
ariston_comando_esito: in_attesa
```

L'integrazione mantiene **lettura cloud fresca → un solo POST → rilettura di conferma**. Il dato provvisorio non altera lo snapshot originale, i sensori di misura o il gas.

| Esito | Cosa si vede |
| --- | --- |
| `confermato` | Il server ha confermato il valore: l'interfaccia mostra il dato verificato. |
| `rifiutato` | L'interfaccia ritorna al valore precedente verificato; il comando non è accettato. |
| `non_confermato` | Timeout o esito incerto: ritorna l'ultimo stato verificato. **Non ritenta automaticamente.** |

Un secondo comando contemporaneo viene rifiutato per prevenire sovrapposizioni. Il cambiamento fisico sul Cube S può essere ritardato rispetto alla visualizzazione in Lovelace.

## Editor settimanale Cube S

La scheda `ariston-cube-weekly-card` permette di modificare il **programma reale** memorizzato nel cloud Ariston:

- **Sposta orario:** sposta un cambio Comfort/Economy esistente con passi da 15 minuti.
- **Aggiungi fascia:** indica ora iniziale, ora finale e preset, con ripristino del preset precedente alla fine.
- **Elimina fascia:** rimuove un cambio esistente e gestisce i confini ridondanti.
- **Clona giorno:** copia un giorno sorgente su uno o più giorni destinatari scelti.

Ogni modifica richiede **Anteprima → verifica prima/dopo → conferma esplicita**. L'integrazione confronta il fingerprint dell'intero programma, esegue al massimo **un POST** e rilegge **tutti i sette giorni**. Se l'esito è ambiguo, verifica nell'app Ariston prima di ulteriori modifiche.

### Aggiungere la scheda alla dashboard

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.INSERISCI_IL_TUO_SENSORE_PROGRAMMA_SETTIMANALE
title: Fasce riscaldamento Cube S
```

Sostituisci l'ID nell'esempio con quello reale disponibile in **Strumenti per sviluppatori → Stati**. Non viene creato automaticamente un nome uguale per tutte le installazioni.

La risorsa JavaScript si registra automaticamente nelle dashboard **Storage**. Per dashboard YAML, aggiungi:

```yaml
resources:
  - url: /ariston_cube/ariston-cube-weekly-card.js?v=1.3.0
    type: module
```

Dopo un aggiornamento esegui un refresh completo della pagina se il browser conserva la vecchia scheda. [Guida alla scheda settimanale](frontend/README.md).

## Gas Smc e dashboard Energia

Ariston NET espone i consumi del riscaldamento e dell'ACS come due **cumulativi fisici Smc**. Sono sensori separati con `device_class: gas`, `state_class: total` e unità `m³` (metri cubi standard).

I dati Ariston arrivano in bucket **di due ore**. L'integrazione li acquisisce intorno ai minuti **:10**, con secondo tentativo alle **:40**, delle ore pari. Se Home Assistant registra l'incremento nell'ora sbagliata, alle **:15 dell'ora dispari successiva** l'automatismo corregge unicamente l'attribuzione statistica.

| Esempio (ora italiana) | Intervallo |
| --- | --- |
| Consumo pubblicato dal cloud | **14:00–16:00** |
| Ora inizialmente attribuita da HA | 16:00–17:00 |
| Ora corretta dall'integrazione alle 17:15 | **15:00–16:00** |

L'allineamento è stato verificato sul campo, con **0,50 Smc riscaldamento + 0,03 Smc ACS** correttamente nell'ora 15–16, zero in 16–17, e altri periodi consecutivi confermati.

**Protezioni:** verifica del bucket, fingerprint, stato e somme Recorder, salvataggio singolo per sensore, verifica della scrittura, nessun retry automatico dopo un esito incerto. Se mancano dati o il consumo è zero / già allineato, non forza alcuna correzione. Non recupera automaticamente le fasce perse durante un'interruzione.

**Non modificare gli ID dei due sensori cumulativi, non cancellare gli offset o il ledger e non azzerare Recorder.** La 1.3.0 conserva lo stato e la storia Energia delle versioni precedenti.

## Azioni in Strumenti per sviluppatori

Sono esposte **solo sei azioni**, quattro per il programma Cube S e due diagnostiche gas in sola lettura:

| Azione `ariston_cube.*` | Scopo |
| --- | --- |
| `preview_weekly_change` | Anteprima sposta / aggiungi / elimina |
| `write_weekly_change` | Salva la modifica confermata |
| `preview_weekly_clone` | Anteprima di clonazione |
| `clone_weekly_days` | Clonazione confermata |
| `inspect_automatic_energy_hour_alignment` | Ultimi cicli automatici del gas (lettura) |
| `inspect_energy_hour_alignment` | Statistiche di una singola ora (lettura) |

Le vecchie azioni `TEST`, i probe e le scritture manuali di statistiche gas non sono più pubblicati. Il gas continua a funzionare autonomamente.

Per controllare gli ultimi cicli, **senza scrivere nulla**:

```yaml
action: ariston_cube.inspect_automatic_energy_hour_alignment
```

Per ispezionare un'ora statistica, usa il **timestamp UTC** dell'ora italiana interessata:

```yaml
action: ariston_cube.inspect_energy_hour_alignment
data:
  target_start: "2026-10-28T14:00:00+00:00"
```

## Risoluzione problemi

| Sintomo | Verifica |
| --- | --- |
| L'integrazione non appare | Riavvia Home Assistant dopo l'installazione; verifica il percorso `custom_components/ariston_cube` |
| Un comando torna indietro | Controlla `ariston_comando_esito`; se `non_confermato`, verifica il valore nell'app Ariston prima di riprovare |
| La scheda è vecchia o non modifica | Aggiorna la risorsa JS a `?v=1.3.0`, ricarica la dashboard e verifica che le azioni siano registrate |
| Un ciclo gas viene saltato | Controlla `inspect_automatic_energy_hour_alignment`; assenza di dati, Recorder non pronto e bucket zero non devono generare scritture forzate |
| Consumi gas storici | Conserva Recorder e i checkpoint `.storage`; non reinstallare da zero per correggere le statistiche |

In caso di anomalia, apri una [segnalazione GitHub](https://github.com/paolofaz/ha-ariston-cube/issues) indicando versione di Home Assistant, versione dell'integrazione, modello della caldaia e log **senza password, token o dati privati**.

## 🍺 Supporta il progetto

Se hai trovato utile il mio progetto e vuoi supportare il mio lavoro, puoi offrirmi una birretta...

[![Buy Me a Beer](https://img.shields.io/badge/Buy%20Me%20a%20Beer-0070ba?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/PaoloFazari)

## Sviluppo e contributi

Codice Python e JavaScript, licenza [MIT](LICENSE). Le modifiche sono verificate in GitHub Actions con test Python, test della scheda Lovelace (Node), [HACS validation](https://github.com/hacs/action) e [hassfest](https://github.com/home-assistant/actions/tree/master/hassfest).

```bash
python -m pip install pytest aiohttp
python -m compileall -q custom_components/ariston_cube tests
python -m pytest -q
node --test tests/test_weekly_editor.mjs
```

- [Novità della 1.3.0](docs/releases/v1.3.0.md)
- [Documentazione installazione nel catalogo HACS](docs/HACS_PUBLICATION.md)
- [Issue tracker](https://github.com/paolofaz/ha-ariston-cube/issues)
- [Release](https://github.com/paolofaz/ha-ariston-cube/releases)
