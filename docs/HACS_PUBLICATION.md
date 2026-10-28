# Preparazione della candidatura al catalogo HACS

Questa integrazione è già installabile tramite HACS come **repository
personalizzato**: `https://github.com/paolofaz/ha-ariston-cube`.

L'inclusione nel **catalogo predefinito** non è automatica. La richiesta
è una pull request verso `hacs/default` e la presenta **il proprietario
del repository o un contributore principale**. L'approvazione resta a
discrezione dei manutentori HACS.

## Requisiti del progetto

- [x] Repository pubblico GitHub, una integrazione in
  `custom_components/ariston_cube/`.
- [x] Manifest HA, `hacs.json`, README, traduzioni, issue tracker,
  licenza MIT.
- [x] Release stabile con tag immutabile e note ufficiali.
- [x] Job GitHub Actions: test Python + JavaScript, validazione HACS,
  validazione hassfest. **Controllare che siano tutti verdi sulla
  versione finale e senza ignore**.
- [ ] GitHub repository: verificare che la descrizione sia informativa
  e configurare alcuni *topics* (es. `home-assistant`, `hacs`,
  `ariston`, `cube-s`, `heating`) nelle impostazioni GitHub.
- [ ] Branding: aggiungere una icona quadrata 256×256 compatibile
  in `custom_components/ariston_cube/brand/icon.png`, oppure
  verificare il brand dedicato nel repository home-assistant/brands.
  Usare artwork originale o autorizzato, non simboli ufficiali
  Home Assistant.
- [ ] Dopo le verifiche precedenti, il proprietario deve creare
  un fork personale di `hacs/default`, un branch da `master` e
  inserire **`paolofaz/ha-ariston-cube`** nel file `integration`,
  nell'ordine corretto. La PR deve essere modificabile.

## Riferimenti

- [Istruzioni ufficiali di inclusione](https://hacs.dev/docs/publish/include/)
- [Requisiti integrazioni](https://hacs.dev/docs/publish/integration/)
- [Azione HACS](https://hacs.dev/docs/publish/action/)
- [Hassfest](https://github.com/home-assistant/actions#hassfest)
- [Marchi e icone per integrazioni custom](https://contributors.home-assistant.io/blog/2026/02/24/brands-proxy-api/)

Non dichiarare che il progetto sia già nel catalogo HACS prima
dell'accettazione effettiva della PR e della sincronizzazione del
catalogo. Nel frattempo si usa il repository personalizzato.
