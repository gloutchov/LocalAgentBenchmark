# Startup Preferences per nuovi progetti

Questo file raccoglie le preferenze operative da applicare come standard iniziale ai nuovi progetti software. Deriva da convenzioni maturate in precedenti progetti software.

## Principi generali

- Il progetto deve nascere con una struttura modulare, leggibile e mantenibile.
- Evitare file monolitici: ogni funzionalita' rilevante deve avere moduli, componenti, servizi, hook o helper dedicati.
- Preferire interventi piccoli, coerenti con l'architettura esistente e verificabili con test.
- Evitare refactor non richiesti durante milestone funzionali, salvo quando sono necessari per completare in modo sicuro la milestone.
- Non introdurre dipendenze senza una ragione concreta, documentata e coerente con il valore della funzionalita'.
- Tenere sempre separati dominio, accesso ai dati, UI, configurazione, sicurezza, integrazioni esterne e test.
- Ogni comportamento visibile all'utente deve essere documentato.
- Ogni comportamento security-relevant deve essere documentato in `SECURITY_MODEL.md`.

## Documenti obbligatori

Ogni nuovo progetto deve contenere almeno:

- `README.md`: pagina principale in stile GitHub, bilingue italiano/inglese, con descrizione, funzionalita', installazione, sviluppo, distribuzione, licenza e link ai documenti.
- `ISTRUZIONI.md`: manuale utente completo in italiano.
- `INSTRUCTIONS.md`: traduzione inglese completa del manuale utente.
- `SECURITY_MODEL.md`: modello di sicurezza bilingue, con controlli implementati, limiti residui, rischi noti e raccomandazioni.
- `PLAN.md`: piano di sviluppo per milestone funzionali, versioni, branch, criteri di accettazione e checklist di chiusura.
- `MAP.md`: mappa ASCII della struttura del repository, con breve descrizione di cartelle, file principali, test, workflow e documentazione.
- `AGENTS.md`: istruzioni operative per agenti e maintainer che lavorano sul repository.
- `LICENSE`: licenza Apache License 2.0.

Se il progetto espone superfici operative diverse, aggiungere quick start dedicati, per esempio:

- `QUICK-START_CommandLine.md`
- `QUICK-START_Chat.md`
- `QUICK-START_Telegram.md`
- `QUICK-START_Desktop.md`

## Piano milestone

`PLAN.md` deve essere scritto all'inizio del progetto e mantenuto aggiornato.

Ogni milestone deve essere funzionale, non solo tecnica: deve consegnare un comportamento verificabile dall'utente o una base tecnica chiaramente necessaria per una funzionalita' successiva.

Per ogni milestone indicare:

- numero e titolo;
- obiettivo;
- branch previsto;
- tipo incremento versione;
- attivita' principali;
- criteri di accettazione;
- test richiesti;
- documentazione da aggiornare;
- stato.

La checklist minima di chiusura milestone deve includere:

- branch milestone creato;
- implementazione completata;
- test automatici eseguiti;
- smoke test o verifica manuale eseguiti;
- versione aggiornata quando previsto;
- `README.md` aggiornato;
- `ISTRUZIONI.md` aggiornato;
- `INSTRUCTIONS.md` aggiornato;
- `SECURITY_MODEL.md` aggiornato se cambia sicurezza, rete, segreti, storage, IPC, permessi, logging o distribuzione;
- `MAP.md` aggiornato se cambia struttura, moduli, comandi, workflow, test o documentazione;
- `AGENTS.md` aggiornato se cambiano regole operative;
- `PLAN.md` aggiornato;
- approvazione esplicita del progettista prima di merge, salvo istruzioni specifiche del progetto;
- commit finale;
- PR o merge verso `main`;
- CI verificata su branch/PR e su `main`;
- tag versione creato quando previsto;
- release pubblicata solo quando prevista;
- artifact e checksum verificati quando esiste una release;
- branch obsoleto eliminato solo dopo merge e verifiche.

## Branch, commit e merge

- Sviluppare ogni milestone su un branch dedicato, per esempio `milestone/<numero>-<slug>`.
- Per patch mirate usare un branch dedicato, per esempio `patch/<versione>-<slug>`.
- Non fare merge su `main` finche' implementazione, test, documentazione e CI non sono verificati.
- Fermarsi prima del merge se il progettista deve dare avallo.
- Non cancellare il branch milestone prima che merge, tag, CI e release prevista siano verificati.
- Non spostare tag gia' pubblicati salvo richiesta esplicita.
- Dopo il merge, creare e pushare il tag coerente con la versione se la milestone produce una versione rilasciabile.

## Versioning

Usare versionamento semantico, adattato alla scala reale del progetto:

- `+0.0.1`: patch piccola, bugfix, correzione documentale con impatto minimo o hardening circoscritto.
- `+0.1.0`: nuova funzionalita' minore o miglioramento funzionale rilevante.
- `+1.0.0`: milestone importante, cambio architetturale, nuova superficie principale o rilascio stabile.

Quando la versione cambia, sincronizzarla in tutti i punti canonici del progetto, per esempio:

- file `VERSION`, se presente;
- `package.json`, `pyproject.toml` o equivalente;
- modulo `__version__`, se presente;
- README e manuali;
- `PLAN.md`, `AGENTS.md`, `MAP.md`;
- note release.

Il tag Git deve seguire il formato `vX.Y.Z`.

## Release

- Le release automatiche o GitHub Actions di release devono essere attivate solo quando il programma raggiunge una versione funzionale.
- Durante le prime milestone di sviluppo, evitare release inutili: CI, test e build sono sufficienti.
- Generare una GitHub release solo quando le modifiche introducono nuove funzionalita' o milestone rilasciabili (`+0.1.0` o `+1.0.0`), oppure quando correggono falle di sicurezza gravi.
- Per patch piccole, bugfix ordinari, correzioni documentali o hardening circoscritti (`+0.0.1`), chiedere sempre al progettista se creare o meno una GitHub release.
- Quando una release e' prevista, generare artifact per Windows e macOS se applicabile.
- Ogni release deve includere checksum SHA-256 degli artifact.
- Se non sono disponibili certificati o credenziali di firma, distribuire artifact non firmati e documentare chiaramente avvisi SmartScreen/Gatekeeper.
- Non configurare firma codice, notarizzazione o auto-update firmato senza credenziali esplicite e processo documentato.
- Le note release devono indicare versione, cambi principali, limiti noti, piattaforme e checksum.

## Architettura e struttura

Il progetto non deve diventare monolitico. La struttura iniziale deve essere razionale e crescere per responsabilita'.

Separare, quando applicabile:

- entry point applicativo;
- configurazione;
- dominio;
- servizi applicativi;
- UI;
- stato UI;
- accesso filesystem;
- persistenza/database;
- integrazioni esterne;
- client HTTP/API;
- gestione segreti;
- sicurezza;
- i18n;
- tema;
- logging;
- packaging;
- test unitari;
- test end-to-end;
- script operativi;
- workflow CI/release.

Le dipendenze tra moduli devono essere esplicite e direzionate. Evitare import circolari.

La logica riutilizzabile deve stare in moduli testabili, non sepolta nei componenti UI o negli entry point.

## Configurazione

Ogni progetto deve avere un file di configurazione centrale per parametri modificabili da utente esperto o sviluppatore.

Esempi:

- `config/app.config.json`
- `app.config.json`
- `myproject.toml`
- `.env.example` solo come template, mai con segreti reali.

Non hardcodare nei moduli funzionali parametri come:

- provider API;
- URL base;
- modelli AI;
- timeout;
- limiti dimensione payload;
- percorsi default;
- nomi file generati;
- intervalli autosave;
- dimensioni canvas/finestra;
- qualita' export;
- lingua default;
- tema default;
- limiti history;
- limiti concorrenza;
- policy rete;
- policy logging;
- valori UI modificabili dall'utente.

La configurazione deve essere validata all'avvio. I fallback sono ammessi solo per proteggere da configurazioni mancanti o corrotte, e devono essere documentati.

I segreti non devono mai stare nella configurazione del repository.

## Lingua e tema

Se il progetto ha UI o testi utente, deve essere bilingue italiano/inglese.

Regole:

- rilevare automaticamente la lingua di sistema;
- se la lingua di sistema non e' italiano, usare inglese;
- permettere override manuale della lingua;
- mantenere dizionari italiano e inglese sincronizzati;
- evitare stringhe user-facing hardcoded fuori dai dizionari;
- non tradurre automaticamente i contenuti creati dall'utente.

Se il progetto ha UI grafica, deve supportare tema chiaro/scuro:

- rilevare automaticamente il tema di sistema;
- default automatico chiaro/scuro basato sul sistema operativo;
- override manuale dell'utente;
- persistenza della preferenza sia per la lingua sia per il tema;
- verifica di leggibilita' di modali, checkbox, campi, dropdown, tooltip e stati disabilitati in entrambi i temi.

## Sicurezza

`SECURITY_MODEL.md` deve descrivere:

- modello operativo;
- superfici locali e remote;
- gestione segreti;
- configurazione;
- rete;
- logging;
- persistenza;
- permessi filesystem;
- IPC o bridge privilegiati, se presenti;
- validazione input;
- limiti payload;
- test di sicurezza;
- limiti residui;
- miglioramenti pianificati.

Regole minime:

- Non salvare API key, token, password o PIN in chiaro nel repository, nei file progetto, nei log, nei crash report o negli esempi.
- Usare il keychain del sistema operativo o uno storage protetto quando disponibile.
- Il renderer o la UI non devono accedere direttamente a segreti, filesystem privilegiato o API native: usare canali controllati.
- Validare input e output sui confini: IPC, CLI, HTTP, plugin, MCP, Telegram, file importati, scheduler.
- Sanitizzare errori e log prima di mostrarli o salvarli.
- Non stampare mai segreti in output.
- Limitare dati inviati a servizi remoti al minimo necessario.
- Chiedere consenso esplicito prima di inviare contenuti utente o memoria locale a provider esterni.
- Usare timeout espliciti per rete e task.
- Preferire HTTPS e non disabilitare TLS; supportare CA bundle o trust store di sistema quando serve.
- Bloccare path traversal e scritture fuori workspace.
- Le operazioni distruttive devono richiedere conferma esplicita.
- Log e audit log devono salvare metadata utili, non contenuti sensibili completi quando non necessario.
- Gli strumenti agentici, plugin, skill o server MCP sono da trattare come istruzioni/processi non fidati: non possono concedere permessi o bypassare conferme.

Per app Electron:

- `contextIsolation: true`;
- `nodeIntegration: false`;
- `sandbox: true` quando possibile;
- preload minimale;
- IPC centralizzato e validato;
- Content Security Policy esplicita;
- blocco di navigazioni inattese e popup;
- filesystem e segreti gestiti nel main process.

Per CLI o agenti locali:

- permessi workspace espliciti, per esempio `denied`, `read-only`, `confirm`, `full-auto`;
- default conservativo;
- diff o riepilogo prima delle scritture in modalita' `confirm`;
- cancellazioni sempre confermate;
- test per path traversal, permessi e assenza leak segreti.

Per Telegram o altri controlli remoti:

- token fuori repository;
- allowlist obbligatoria di chat/user;
- autenticazione o PIN quando opportuno;
- rate limit;
- conferma separata per operazioni sensibili;
- redazione output;
- log accessi senza token e senza testo completo quando non necessario;
- blocco di modalita' pericolose da remoto salvo consenso progettuale esplicito.

## Test e qualita'

Ogni funzionalita' deve avere test ad hoc proporzionati al rischio.

Tipi di test da considerare:

- unit test per logica pura;
- integration test per servizi, storage, configurazione e adapter;
- test CLI per comandi;
- test UI per flussi principali;
- e2e Playwright o equivalente per app web/desktop;
- smoke test su build pacchettizzata quando applicabile;
- test sicurezza per segreti, permessi, IPC, path traversal, CSP, TLS e logging;
- test packaging/distribuzione;
- test negativi per input corrotti, payload troppo grandi e configurazioni invalide.

I test devono essere isolati da:

- credenziali reali;
- keychain reale, salvo test manuali espliciti;
- rete reale, salvo smoke test documentati;
- dati privati dell'utente.

La checklist di verifica va adattata allo stack. Esempi:

```powershell
npm run lint
npm run typecheck
npm run test
npm run test:e2e
npm run test:e2e:electron
npm run build
```

```powershell
python -B -m pytest -p no:cacheprovider
python -m pip_audit . --progress-spinner off
python -m bandit -q -c pyproject.toml -r src
python -m myproject security audit .
```

Riportare sempre eventuali test non eseguiti e il motivo.

## CI

GitHub Actions deve coprire almeno:

- installazione dipendenze;
- controllo documenti obbligatori;
- lint/typecheck;
- test automatici;
- build;
- controlli sicurezza leggeri;
- packaging smoke quando applicabile.

Per progetti multipiattaforma, testare almeno Windows e macOS; aggiungere Linux se supportato.

Dopo ogni push rilevante:

- verificare la CI;
- se fallisce, leggere i log;
- correggere il problema se in scope;
- pushare il fix;
- ricontrollare la CI.

## Packaging multipiattaforma

Se il progetto e' distribuibile come app o tool:

- supportare Windows e macOS quando applicabile;
- documentare prerequisiti;
- documentare installazione, aggiornamento e rimozione;
- evitare artefatti locali privati nei pacchetti;
- verificare che l'app funzioni fuori dal checkout sorgente;
- generare checksum SHA-256;
- documentare chiaramente se gli artifact non sono firmati.

Se il progetto e' Python-only, preferire installazione isolata con `pipx`, `uv tool` o wheel.

Se il progetto e' Electron, gestire con attenzione moduli nativi, rebuild per target Electron/Node e smoke test del pacchetto reale.

## Documentazione utente

Il README deve contenere:

- nome progetto;
- descrizione breve;
- stato del progetto;
- versione;
- piattaforme;
- licenza;
- funzionalita' principali;
- installazione;
- uso rapido;
- configurazione;
- sicurezza e privacy in forma sintetica;
- sviluppo locale;
- test;
- packaging/release;
- link a `ISTRUZIONI.md`, `INSTRUCTIONS.md`, `SECURITY_MODEL.md`, `MAP.md`.

`ISTRUZIONI.md` e `INSTRUCTIONS.md` devono contenere:

- requisiti;
- installazione;
- primo avvio;
- flussi principali;
- configurazione;
- comandi o controlli UI;
- esempi pratici;
- troubleshooting;
- note sicurezza;
- limiti noti.

La documentazione deve evitare esempi con segreti reali.

## Mappa repository

`MAP.md` deve contenere una mappa ASCII aggiornata della struttura del repository.

La mappa deve includere:

- cartelle principali;
- file sorgente principali;
- configurazione;
- script;
- test;
- workflow GitHub;
- documentazione;
- file generati o locali da non modificare manualmente.

Ogni voce rilevante deve avere una breve descrizione.

Aggiornare `MAP.md` nella stessa milestone che aggiunge, rimuove, rinomina o sposta file/moduli rilevanti.

## UI e UX

Se il progetto ha UI:

- aprire direttamente sull'esperienza utile, non su una landing page, salvo progetti esplicitamente web/marketing;
- usare pattern coerenti con il framework e il design esistente;
- evitare card annidate e decorazioni inutili;
- garantire leggibilita' desktop e mobile;
- verificare overflow, modali, pulsanti, tooltip e testi lunghi;
- usare controlli appropriati: toggle per booleani, slider/input per numeri, menu per opzioni, tab per viste, icone per azioni comuni;
- rendere visibili stati di caricamento, errore, vuoto e successo;
- non inserire testi in-app che descrivono ovvieta' tecniche o istruzioni che appartengono al manuale.

## AI, provider esterni e privacy

Se il progetto usa AI:

- AI disattivata per default quando tratta contenuti utente sensibili, salvo scelta progettuale esplicita;
- provider e modelli configurabili;
- separare provider remoti da provider locali;
- salvare API key nel keychain;
- esporre alla UI solo stato della chiave, mai il valore;
- richiedere consenso per chiamate API esterne;
- richiedere consenso separato per inviare memoria locale o contenuti progetto a provider esterni;
- documentare quali dati vengono inviati, a chi, quando e con quale logica;
- gestire timeout, cancellazione e fallback;
- sanitizzare errori provider;
- testare assenza di segreti in prompt, log, config e fixture.

## Memoria wiki e knowledge base LLM

Se viene richiesto un sistema di "memoria wiki", knowledge base personale, wiki mantenuta da LLM o archivio incrementale di conoscenza, usare queste direttive come standard iniziale. Le direttive derivano da `llm-wiki.md` e devono essere adattate al dominio specifico del progetto.

L'idea centrale e' costruire una wiki persistente e cumulativa, non un semplice sistema RAG che recupera chunk grezzi a ogni domanda. L'LLM deve leggere le fonti, estrarre conoscenza, integrarla in pagine markdown strutturate, aggiornare collegamenti e sintesi esistenti, segnalare contraddizioni e mantenere il patrimonio informativo nel tempo.

La struttura deve distinguere tre livelli:

- fonti raw: documenti, articoli, paper, immagini, dati e note originali; sono immutabili e restano la fonte di verita';
- wiki: directory di file markdown generati e mantenuti dall'LLM, con pagine di sintesi, entita', concetti, confronti, overview e analisi;
- schema operativo: documento di regole, per esempio `AGENTS.md` o un file dedicato, che descrive struttura, convenzioni, workflow, formati pagina e criteri di manutenzione.

Le fonti raw non devono essere modificate dall'LLM. La wiki e' invece un artefatto mantenuto dall'LLM: l'utente cura le fonti, guida l'analisi e fa domande; l'LLM esegue sintesi, cross-reference, aggiornamenti, filing e bookkeeping.

Workflow minimi:

- ingest: quando arriva una nuova fonte, leggerla, discuterne i punti chiave se utile, creare o aggiornare una pagina di sintesi, aggiornare indice, pagine entita'/concetto correlate, collegamenti incrociati e log;
- query: per rispondere a domande, leggere prima l'indice, poi le pagine rilevanti, sintetizzare con citazioni verso fonti o pagine wiki; quando una risposta produce valore duraturo, salvarla come nuova pagina o aggiornare pagine esistenti;
- lint: periodicamente controllare contraddizioni, claim obsoleti, pagine orfane, concetti importanti senza pagina dedicata, cross-reference mancanti, lacune informative e possibili nuove fonti da cercare.

La wiki deve includere almeno:

- `index.md`: catalogo orientato al contenuto, con link a ogni pagina, riassunto di una riga, categoria e metadati utili come data o numero fonti;
- `log.md`: registro cronologico append-only di ingest, query, lint e manutenzioni, con prefissi coerenti e parseabili, per esempio `## [2026-04-02] ingest | Titolo fonte`;
- directory o convenzioni chiare per fonti, entita', concetti, sintesi, confronti, asset e output derivati.

Regole operative:

- preferire ingest una fonte alla volta quando serve supervisione qualitativa;
- consentire batch ingest solo se il workflow e i controlli sono documentati;
- mantenere citazioni e provenienza delle affermazioni importanti;
- segnalare esplicitamente contraddizioni tra fonti o tra nuove fonti e pagine esistenti;
- aggiornare pagine esistenti invece di duplicare conoscenza;
- usare link markdown/Obsidian coerenti e mantenere pagine collegate;
- usare YAML frontmatter solo se utile per tag, date, conteggi fonte o viste dinamiche;
- trattare immagini e asset come fonti locali quando disponibili, scaricandoli in una cartella stabile se il progetto lo prevede;
- documentare nel modello di sicurezza cosa viene letto, salvato, indicizzato o inviato a provider AI esterni.

Strumenti opzionali:

- Obsidian puo' essere usato come interfaccia di lettura, navigazione, graph view e revisione;
- Obsidian Web Clipper puo' essere usato per acquisire articoli in markdown;
- Marp puo' essere usato per generare presentazioni markdown dalla wiki;
- Dataview puo' essere usato se le pagine hanno frontmatter strutturato;
- strumenti locali come `qmd` o una ricerca markdown dedicata possono essere aggiunti quando `index.md` non basta piu'.

La wiki deve essere trattata come un repository markdown versionabile: usare Git quando possibile, conservare cronologia, evitare riscritture distruttive non richieste e aggiornare schema, indice e log insieme alle pagine modificate.

## File locali e workspace

Se il progetto opera su file dell'utente:

- definire una root workspace;
- risolvere tutti i path rispetto alla root;
- rifiutare path assoluti non autorizzati e segmenti `..`;
- distinguere lettura, scrittura, cancellazione e operazioni distruttive;
- usare conferme per scritture rischiose;
- usare salvataggi atomici quando possibile;
- mantenere audit log minimale per operazioni rilevanti;
- documentare cosa viene salvato localmente e cosa puo' contenere dati sensibili.

## Checklist iniziale per nuovo progetto

Prima di iniziare lo sviluppo effettivo:

- creare repository con licenza Apache 2.0;
- scegliere stack e piattaforme target;
- creare struttura modulare iniziale;
- creare file configurazione centrale senza segreti;
- creare `README.md` bilingue;
- creare `ISTRUZIONI.md` e `INSTRUCTIONS.md`;
- creare `SECURITY_MODEL.md`;
- creare `MAP.md`;
- creare `AGENTS.md`;
- creare `PLAN.md` con milestone funzionali;
- configurare test minimi;
- configurare CI minima;
- definire strategia versioning;
- definire quando attivare release;
- verificare che `.gitignore` escluda segreti, log, build output, cache e stato locale.

## Checklist prima di chiudere una milestone

- Worktree controllato.
- Modifiche proprie comprese e isolate.
- Nessuna modifica utente revertita.
- Funzionalita' completata.
- Test mirati aggiunti o aggiornati.
- Test automatici eseguiti.
- Verifica manuale eseguita se necessaria.
- Configurazione aggiornata e validata.
- Nessun parametro utile lasciato hardcoded senza motivo.
- Nessun segreto tracciato.
- Documentazione aggiornata.
- `MAP.md` aggiornato se cambia struttura.
- `SECURITY_MODEL.md` aggiornato se cambia superficie di rischio.
- Versione aggiornata se previsto.
- CI verificata.
- Avallo del progettista ottenuto prima del merge, salvo istruzioni contrarie.
- Merge, tag, push e release completati solo quando previsti.

## Preferenze operative per agenti

- Leggere prima `AGENTS.md`, `PLAN.md`, `README.md`, `MAP.md` e `SECURITY_MODEL.md`.
- Controllare lo stato del worktree prima di modificare.
- Non revertire modifiche non proprie.
- Usare strumenti di ricerca rapidi come `rg`.
- Usare patch piccole e leggibili.
- Aggiornare documentazione insieme al codice.
- Non aggiungere dipendenze o workflow senza motivazione.
- Quando un task tocca UI, verificare layout e tema.
- Quando un task tocca sicurezza, aggiornare test e `SECURITY_MODEL.md`.
- Quando un task chiude una milestone, seguire la checklist completa e chiedere avallo prima di merge.

## Note specifiche per LocalAgent Benchmark

- Il comando di verifica locale è `python3 -m unittest discover -s tests -v`; eseguire anche `python3 -m compileall -q benchmark.py dashboard.py guided_benchmark.py src cases tests` quando cambia codice Python.
- Mantenere il runtime Python privo di dipendenze esterne finché non esiste una motivazione documentata.
- Non modificare fixture o grader mentre un benchmark è in esecuzione.
- Prima di un run, mantenere puliti rispetto a Git `AGENTS.md`, `.gitignore` e tutti i manifesti, prompt, fixture, grader e rubriche selezionati: il preflight deve fallire, non essere aggirato, se questi input divergono.
- Ogni run deve usare un unico snapshot verificato per tutti i modelli, includere e hashare la policy di esecuzione, e registrare SHA-256, commit/stato Git, tree delle baseline, seed e ordine delle task.
- Preparare `.benchmark-scratch/` dentro ogni workspace, ignorarla in Git e usarla per `TMPDIR`, `TMP` e `TEMP`; prompt e fixture devono contenere tutto il necessario senza richiedere `/tmp`, repository esterni o rete.
- Trattare path espliciti risolti fuori workspace, tentativi di rete, mutazioni del repository/snapshot e baseline divergenti come violazioni d'integrità: escludere l'intero modello dalla classifica e interrompere la matrice se lo snapshot condiviso cambia.
- Versionare l'audit, riesaminare gli eventi precedenti quando possibile e mostrare nel report motivo, target ed evidenza senza alterare i `result.json` originali.
- Nei comandi shell distinguere il controllo eseguito dai payload letterali: un heredoc scritto su file non va interpretato come sequenza di path/comandi, mentre un heredoc inviato a un interprete deve mantenere i controlli applicabili.
- `--seed` deve rendere riproducibile l'ordine randomizzato; unload e warmup vanno registrati a ogni cambio modello.
- Ogni versione Pi deve superare il controllo contrattuale sul server OpenAI-compatible sintetico prima delle task, da CLI e UI guidata. Pi 0.85.1 resta la versione di riferimento suggerita in caso di incompatibilità; non aggirare il gate né il probe della sandbox selezionata.
- Ogni profilo, incluso `showcase`, e ogni selezione `--cases` devono attraversare lo stesso controllo thinking. Il default ufficiale resta `off`, canonicalizzato in `reasoning_effort: "none"`; non introdurre fallback silenziosi tra livelli.
- Capability `/api/show`, preflight OpenAI-compatible, configurazione Pi, warmup e task devono concordare sulla policy thinking. Un controllo non verificabile, reasoning osservabile in `off` o retry inatteso deve escludere l'intero modello senza impedire i controlli sugli altri.
- Preflight e warmup non devono contribuire a tempi, token o punteggi delle task. Non persistere la traccia di reasoning del preflight; gli eventi raw delle task possono contenerla e restano artefatti locali sensibili.
- Confrontare `off` e modalità attive soltanto come coorti simmetriche in directory distinte; non concedere una seconda modalità selettivamente dopo un fallimento. `compare` deve rifiutare modalità, controllo, retry, timeout idle, versioni Pi/Ollama, digest o capability incompatibili.
- Ogni nuovo caso deve avere un `case.json` conforme a `schemas/case.schema.json`, titoli italiano/inglese, prompt, fixture, grader con massimo e somma punti pari a 100 e un test di calibrazione che mantenga la fixture iniziale sotto la soglia di completamento.
- `thinking_challenge` deve restare un caso sintetico di pianificazione esatta: il grader usa scenari alternativi non presenti nella fixture, una soluzione hardcoded sull'esempio pubblico deve restare sotto 60 e nessun check deve richiedere o premiare la catena di pensiero.
- Il profilo `thinking` esegue soltanto `thinking_challenge`; `standard` e `full` lo includono, mentre `smoke` e `showcase` mantengono il proprio scopo. Gli esperimenti decisionali `off`/`medium` richiedono almeno tre ripetizioni per cella, condizioni simmetriche e ordine controbilanciato quando possibile.
- Creare i casi con `python3 benchmark.py case create ...` quando possibile e validarli con `python3 benchmark.py case validate [ID]`; revisionare prima il grader perché il validatore lo esegue fuori sandbox con i permessi dell'utente.
- I path dichiarati dal manifesto devono essere relativi e confinati alla directory del caso. Le rubriche manuali sono opzionali, vengono conservate come artefatti separati e non devono modificare lo score automatico.
- Non includere credenziali, repository reali o dati privati nelle fixture.
- Trattare `results/` come output locale potenzialmente sensibile; non versionarlo.
- Il runner deve continuare a registrare configurazione, versioni, risposta, eventi, patch, stato Git e dettaglio dei check per rendere ogni punteggio verificabile.
- La modalità sandbox deve essere sempre esplicita: `audit` non va descritta come isolamento, `auto` deve registrare il fallback e `required` deve fallire se il backend non è realmente applicabile.
- Non dichiarare capacità che il backend non applica: Seatbelt macOS limita file utente e rete loopback ma usa un'interfaccia deprecata; Linux isola filesystem, processi e rete soltanto quando il probe `bwrap`+`unshare` riesce; Windows applica AppContainer soltanto quando profilo, ACL/DACL, named pipe e Job Object superano i controlli. `audit` e il fallback di `auto` non sono isolamento; `required` deve sempre fallire senza un backend realmente applicabile.
- Metriche hardware, processi ed energia devono includere provider, scope e disponibilità; non attribuire al solo modello contatori host-wide o incompleti.
- Confrontare statisticamente soltanto directory distinte e run con versione/parametri, input, digest/capability modello, profilo, controllo thinking, retry, timeout idle, versioni Pi/provider, backend e ambiente compatibili; i modelli esclusi per integrità non devono rientrare tramite l'aggregazione.
- `dashboard-data` deve leggere soltanto `run.json` e `report.json` supportati, applicare una whitelist esplicita e non esportare path assoluti, prompt, risposte, reasoning, preflight dettagliati, comandi, log, evidenze di violazione o errori liberi; input e output devono restare nella root del progetto e le sorgenti non vanno modificate. I run legacy devono risultare `thinking_control: unverified`.
- Il dataset della finalissima deve essere revisionato, congelato nella fixture `results_dashboard`, committato e identico per tutti i finalisti. `not_run_in_next` indica soltanto assenza dal profilo successivo e non deve essere trasformato in un fallimento implicito.
- Il funnel dashboard comprende soltanto `smoke`, `standard` e `full`; `thinking`, `showcase` e profili personalizzati restano indipendenti. Classifiche e fattori devono restare separati per run/modalità thinking e non produrre un rank combinato implicito tra coorti incompatibili.
- La dashboard candidata deve restare statica e offline, senza dipendenze runtime, CDN, telemetria o asset remoti. Il punteggio tecnico del grader e la rubrica visuale manuale devono restare separati; eseguire la verifica browser prima di scegliere o pubblicare un candidato.
- La dashboard ufficiale sotto `dashboard/` è distinta dalle dashboard candidate del caso `results_dashboard`: deve restare statica e offline; `python3 dashboard.py` è il flusso principale e serve il dataset ridotto in memoria. Lo snapshot locale opzionale deriva soltanto dalla fixture revisionata, si rigenera esclusivamente con `python3 dashboard.py --refresh-snapshot --force` e non deve essere tracciato da Git.
- Le mappe di efficienza della dashboard ufficiale devono usare `quality_score` contro durata mediana e token mediani, con asse orizzontale logaritmico dichiarato, punti accessibili da tastiera e coorti separate per run/modalità thinking. Non aggiungere trend line o ranking combinati impliciti e non usare `overall_score` come asse qualità perché incorpora già velocità ed efficienza token.
- `dashboard.py` deve servire soltanto asset esplicitamente autorizzati e il dataset già ridotto in memoria, usare esclusivamente `127.0.0.1`, non esporre directory o file raw di `results/` e non modificare i run sorgente. Lingua e tema possono essere persistiti nel browser, ma nessun risultato deve essere salvato implicitamente.
- Ogni modifica alla dashboard ufficiale richiede test Python e JavaScript, verifica tramite server locale e, quando viene generato uno snapshot locale, anche da `file://`; servono inoltre prova responsive/tastiera e controllo che non partano richieste remote. Il file chooser accetta soltanto export compatibili prodotti da `dashboard-data`.
- La landing pubblica vive esclusivamente sotto `site/`: deve restare statica, bilingue, accessibile, compatibile con il prefisso Pages `/LocalAgentBenchmark/` e priva di dipendenze runtime, CDN, font remoti, form, cookie, analytics, telemetria o richieste remote. Soltanto lingua e tema possono essere persistiti in `localStorage`.
- `assets/Dashboard.mov` e `assets/Guided.mov` sono sorgenti locali immutabili e ignorate da Git: non modificarle, non aggiungerle al repository e non pubblicarle. Versionare sotto `site/assets/` soltanto derivati ritagliati, ottimizzati, privi di metadati superflui e approvati dal progettista.
- Ogni modifica alla landing richiede test statici Python e JavaScript, verifica in browser a 1440×900 e 390×844, entrambe le lingue, tema automatico/chiaro/scuro, tastiera e focus, assenza di overflow, console pulita e controllo che tutte le richieste runtime restino sullo stesso origin.
- Il workflow Pages deve mantenere le azioni fissate a commit revisionati, validare il sito e pubblicare soltanto `site/`. Attivazione Pages, commit, push, PR, merge, tag, release e deploy richiedono l'avallo esplicito previsto da `PLAN.md`.
- Il percorso rapido deve restare una UI sottile sopra il runner esistente: usare nell'ordine la leaderboard ufficiale, non duplicarne formula o tie-break, escludere il singolo modello con task fallite quando la fase resta completa e compatibile, non promuovere run parziali/esclusi e non aggirare doctor, preflight, snapshot, thinking, sandbox, warmup, audit o input puliti.
- I toggle del percorso rapido applicano a tutte le fasi thinking `off`/`medium` e sandbox `audit`/`required`, senza fallback impliciti; `required` deve fallire prima di creare la sessione se il backend OS manca. La dashboard schema 3 espone solo codici d'esclusione sanitizzati separati dalle task effettive e continua a leggere gli schemi 1/2.
- Il funnel guidato è soltanto `smoke` → massimo 4 in `standard` → massimo 2 in `full`; non deve eseguire `showcase` o `results_dashboard`, modificare la fixture congelata o creare classifiche fra coorti incompatibili.
- Tutti i processi del percorso guidato devono ricevere argomenti strutturati senza shell, usare il provider selezionato su loopback, scrivere soltanto sotto la root e conservare gli artefatti in cancellazione/errore. Il completamento apre la dashboard ufficiale con tre run distinti validati; la riapertura diagnostica può usare da uno a tre run disponibili senza presentare un funnel parziale come completo.
- I provider supportati sono Ollama, LM Studio e il router ufficiale llama.cpp. Il server deve restare su HTTP loopback; non introdurre proxy, redirect, token in configurazione o fallback thinking silenziosi. `node-llama-cpp` richiede un bridge dedicato e non è un adapter del benchmark.
- Per LM Studio/llama.cpp, registrare provider, endpoint, versione dichiarata e SHA-256 dei GGUF esplicitamente mappati. Un singolo run può avere provenienza incompleta, ma `compare` deve rifiutare aggregazioni prive di versione runtime o hash GGUF; non dichiarare verificata l'associazione ID/file che le API non provano.
- `guided-run.json` deve essere atomico e registrare discovery, selezione, impostazioni, seed, directory relative, classifiche, esclusioni e transizioni. `.localagent-benchmark/` contiene soltanto preferenze GUI validate ed è ignorata da Git.
- I launcher sotto `launchers/` sono script sorgente, non artifact binari o firmati: documentare con precisione Python/Tkinter, comportamento del doppio clic e limiti di piattaforma senza promettere installer inesistenti.
