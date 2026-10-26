# Vista settimanale Cube S

Il calendario mensile mostra troppi eventi ricorrenti. Questa **scheda Lovelace opzionale**
mostra invece sette barre orizzontali Comfort/Economy, con l'orario di ogni cambio.
Legge solo il sensore già disponibile **Programma settimanale Cube S** e non
effettua richieste cloud aggiuntive. Non modifica la programmazione.

## Installazione manuale

1. Copia `frontend/ariston-cube-weekly-card.js` dal repository in
   `/config/www/ariston-cube-weekly-card.js` (crea la cartella `www` se necessario).
2. Nelle risorse della dashboard, registra `/local/ariston-cube-weekly-card.js?v=1`
   come **Modulo JavaScript**. Per trovare il menu: dashboard → tre puntini →
   Gestisci risorse (oppure Impostazioni → Dashboard → Risorse).
3. Aggiungi una scheda manuale e incolla:

```yaml
type: custom:ariston-cube-weekly-card
entity: sensor.SOSTITUISCI_CON_IL_TUO_ID_REALE
title: Programmazione settimanale Cube S
```

Per `entity` usa l'ID reale visibile in Strumenti per sviluppatori → Stati.
La scheda evidenzia il giorno corrente e mostra l'intera settimana in un colpo solo.
Puoi nascondere la vecchia entità calendario dalla dashboard se non ti interessa.

## Modificare le fasce

Questa versione è di sola lettura: una helper `schedule` di Home Assistant
creerebbe un secondo programma, non sincronizzato automaticamente con Cube S.
Per la modifica serve prima convalidare il salvataggio di `ChZn1.plans` attraverso
l'API Ariston. Non introdurremo scritture non verificate.
