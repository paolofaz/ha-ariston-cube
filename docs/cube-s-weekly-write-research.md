# Cube S — scrittura della programmazione settimanale: branch sperimentale

**Stato: BOZZE LOCALI, NESSUN COMANDO DI SCRITTURA.**

Base: Ariston Cube 1.0.0. I cumulativi Smc, l'energia, il `climate`
e il calendario in sola lettura non sono modificati da questo esperimento.

## Cosa sappiamo dal dispositivo

- GET verificato in sola lettura: `/api/v2/remote/timeProgs/{gateway}/ChZn1?umsys=si`.
- La risposta comprende `ChZn1.plans`, ciascuno con `days` e `slices`.
- Giorni 0=domenica fino a 6=sabato; ogni `slice` è `from`
  (minuto del giorno) e `temp` (0 Economy / 1 Comfort).
- Diversi giorni possono condividere un piano; cambiare un solo giorno
  significa presumibilmente separarlo dal gruppo, operazione da
  **non** implementare finché il cloud non ne conferma le regole.
- Il parser attuale normalizza i dati per la vista, ma non conserva
  gli eventuali metadati necessari per una scrittura.
- Il `ZoneMode=3` attiva il programma già memorizzato; non equivale
  a scrivere nuove fasce settimanali.

## Evidenze NON sufficienti per effettuare un POST

Sono pubblici esempi per altri modelli (ad esempio Ariston Velis).
**Non dimostrano** endpoint, metodo o payload validi per CLAS ONE 30L
con Cube S. Non riutilizziamo per analogia percorsi o JSON.

## Lavoro già predisposto

`weekly_preview.py` offre un *editor di bozze* puramente offline:
valida intervalli e preset, non modifica l'input, conserva gli altri
giorni e calcola l'impronta SHA-256 completa della risposta originale.
L'impronta è necessaria per rilevare una modifica concorrente prima
di ogni futura operazione. Il risultato dichiara `can_submit=False`
ed è una vista, **non** un payload Ariston.

## Prima di abilitare la scrittura

1. Verificare per questo gateway il **contratto reale** di salvataggio
   mediante una fonte affidabile o una cattura *redatta* dell'azione
   eseguita dall'app ufficiale. Non condividere HAR completi, cookie,
   token, credenziali, seriali né identificativi dell'impianto.
2. Verificare struttura completa, limiti dei piani, comportamento
   dei giorni raggruppati, opzioni supportate e semantica temporale
   al cambio di ora legale.
3. Salvare una copia locale del programma originale, con conferma
   esplicita dell'utente prima dell'invio.
4. Leggere di nuovo l'originale immediatamente prima della scrittura;
   abortire se è cambiato. Verificare la risposta server.
5. Consentire **una sola scrittura richiesta dall'utente**, senza retry
   automatici in caso di timeout ambiguo, quindi GET di verifica e
   confronto completo del risultato. Non inviare in caso di schema
   incompleto o stato sconosciuto.
6. Definire una procedura di recupero da usare solo dopo verifica
   ulteriore e consenso, mai un secondo POST automatico.

**Non introdurre una UI con pulsante Salva finché queste verifiche
non sono superate.**
