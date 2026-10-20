# Manuale utente – LocalAgent Benchmark

## 1. Scopo

LocalAgent Benchmark confronta modelli locali Ollama, LM Studio o llama.cpp quando lavorano come coding agent attraverso Pi. Ogni modello riceve input copiati dallo stesso snapshot congelato di `AGENTS.md`, manifesto, prompt e fixture Git. Il risultato viene misurato con controlli automatici e conservato per revisione manuale. La configurazione dei provider alternativi è descritta in [QUICK-START_LocalProviders.md](QUICK-START_LocalProviders.md).

## 2. Requisiti

- Python 3.10+ e Git nel `PATH`;
- un server locale configurato e raggiungibile su loopback: Ollama, LM Studio 0.4+ oppure il router `llama-server`;
- Pi installato come comando `pi` (ogni versione deve superare il test di compatibilità locale);
- modelli locali già scaricati e adatti al tool calling;
- spazio libero sufficiente per una copia delle fixture per ogni esecuzione.

La procedura di installazione e verifica su Windows per Pi, Ollama, LM Studio e `llama-server`, con link alle fonti ufficiali, è in [QUICK-START_LocalProviders.md](QUICK-START_LocalProviders.md). Se Pi è già installato e supera `doctor`, non serve aggiornarlo prima di un benchmark.

Per l'isolamento OS opzionale servono `sandbox-exec` utilizzabile su macOS; `bwrap`, `unshare` e user/network namespace utilizzabili su Linux; oppure Windows 10/11 con AppContainer. `doctor` esegue un probe reale e mostra disponibilità, backend e capacità effettive senza installare componenti. Le procedure specifiche sono in [QUICK-START_Linux.md](QUICK-START_Linux.md) e [QUICK-START_Windows.md](QUICK-START_Windows.md).

Verificare l'ambiente:

```bash
python3 benchmark.py doctor
```

Il comando mostra versioni, controlli falliti, capability thinking e compatibilità preliminare dei modelli, oltre allo stato di pulizia degli input, senza eseguire task agentici. La compatibilità definitiva richiede comunque il preflight del run.

`doctor` e ogni avvio di benchmark eseguono tre richieste sintetiche tramite il Pi configurato verso un server temporaneo su `127.0.0.1`: thinking disattivato, thinking `medium` ed errore provider. Il controllo verifica payload, eventi e retry senza chiamare il server di modelli; usa tool disabilitati, `--offline`, directory isolate e il backend sandbox selezionato. Il timeout per ciascuna richiesta è `defaults.pi_contract_timeout_seconds` (30 secondi per impostazione predefinita, valori ammessi 10–300). La GUI mostra l'esito durante il rilevamento e consente di annullarlo; ogni fase CLI ripete il controllo. Nei risultati restano solo stato e codice diagnostico, mai prompt o risposta del probe. Il preflight thinking sul modello selezionato resta separato e obbligatorio.

## 3. Primo avvio

Elencare profili, casi e modelli:

```bash
python3 benchmark.py list
```

Eseguire un solo caso su un modello piccolo per verificare il tool calling:

```bash
python3 benchmark.py run --profile smoke --models qwen3.5:9b-Q4_K_M --thinking off
```

Se il modello termina e produce un report, passare al profilo standard:

```bash
python3 benchmark.py run --profile standard
```

## 4. Flussi principali

### Percorso rapido guidato senza comandi

Aprire con doppio clic `launchers/LocalAgent-Benchmark.command` su macOS, `launchers\LocalAgent-Benchmark.cmd` su Windows o `launchers/LocalAgent-Benchmark.sh` su Linux. La finestra esegue `doctor`, rileva i modelli del provider locale configurato, permette di scegliere i partecipanti e di ordinarli per nome, dimensione o thinking cliccando sulle intestazioni, quindi mostra thinking, sandbox, timeout e warmup effettivi prima di chiedere conferma.

Il tema segue il sistema, con override chiaro/scuro dal selettore. Nel tema scuro, selettori e modelli selezionati mantengono un contrasto leggibile; la barra mostra le task completate dentro ogni fase del percorso.

Usare il toggle **Thinking** per scegliere `off` (spento) o `medium` (acceso), e il toggle **Sandbox** per scegliere `audit` senza isolamento OS (spento) o `required` (acceso). `required` interrompe l'avvio se il backend OS non è applicabile. Le scelte valgono per tutte le fasi e sono registrate in `guided-run.json`; non vengono salvate come preferenze permanenti. Nel **Dettaglio task** della dashboard, i modelli esclusi al preflight per thinking osservato con `off` o dopo violazioni dei confini workspace/rete compaiono in un elenco separato dalle task svolte. È indicato il backend sandbox effettivo; l'esclusione non prova da sola un blocco OS.

Il funnel esegue `smoke` su tutti i selezionati, usa l'ordine della leaderboard ufficiale per promuovere al massimo i primi quattro a `standard`, poi al massimo i primi due a `full`. Un modello con task fallita viene escluso senza fermare gli altri quando la fase è completa e verificabile; una fase parziale o incompatibile ferma invece il percorso. Al termine la dashboard ufficiale si apre sui tre run distinti. Il percorso non esegue `showcase` né il caso `results_dashboard`.

`defaults.timeout_seconds` in `benchmark.json` limita **ogni task** (1.200 secondi, cioè 20 minuti, per default), non l'intero funnel. Il controllo Pi, il preflight thinking e il warmup hanno limiti separati; la GUI mostra il valore task prima della conferma. Su Windows, alla scadenza il runner chiude l'albero dei processi Pi/Node e limita anche la raccolta finale dell'output. Per un primo test più breve, selezionare un solo modello e impostare `defaults.timeout_seconds` prima di aprire la GUI, oppure usare `--timeout 300` da CLI. Non cambiare la configurazione durante un run.

**Annulla** termina il gruppo di processi dopo conferma e conserva gli artefatti. Una sessione interrotta non è ripresa: risolvere il problema e crearne una nuova. **Riapri dashboard** riutilizza invece da uno a tre run disponibili dell'ultima sessione senza rieseguire i modelli, anche dopo il riavvio della GUI. La durata non è garantita. Procedura completa, comportamento per piattaforma e privacy: [QUICK-START_Guided.md](QUICK-START_Guided.md).

### Confronto rapido

Usare `smoke` con tutti i modelli. Serve soprattutto a individuare modelli che non emettono correttamente chiamate agli strumenti.

### Confronto ordinario

Usare `standard`: comprende una patch mirata, un hardening di sicurezza, configurazione/i18n e il caso di pianificazione esatta multi-vincolo `thinking_challenge`.

### Scelta finale

Usare `full --repetitions 3` soltanto sui finalisti. Il quinto caso verifica branch, versione, documentazione, piano e stop prima del merge.

### Esperimento thinking mirato

Il profilo indipendente `thinking` esegue soltanto `thinking_challenge`. Il caso richiede un pianificatore esatto con budget, rischio, capacità team, dipendenze, conflitti, categorie obbligatorie e tie-break deterministico. Il grader usa scenari alternativi non presenti nella fixture e non chiede né premia la catena di pensiero.

Per confrontare `off` e `medium`, usare gli stessi modelli, seed, parametri e tre ripetizioni per cella, ma directory distinte:

```bash
python3 benchmark.py run --profile thinking --models MODELLO --thinking off --repetitions 3 --seed 20260919 --output results/thinking-off
python3 benchmark.py run --profile thinking --models MODELLO --thinking medium --repetitions 3 --seed 20260919 --output results/thinking-medium
```

Alternare o controbilanciare l'ordine delle coorti nelle campagne più ampie. Non eseguire la seconda modalità soltanto per i fallimenti: timeout, errori e punteggi sotto soglia restano esiti della relativa coorte. `compare` rifiuta intenzionalmente di aggregare modalità diverse.

Quando i finalisti sono definiti, usare il profilo separato `showcase`: il caso `results_dashboard` chiede a ciascun modello di costruire una dashboard statica dallo stesso dataset congelato. Non aggiungere il caso ai profili precedenti, perché la valutazione visuale deve restare una finalissima distinta.

### Selezione manuale

`--models` accetta uno o più nomi esatti mostrati da `benchmark.py list`. `--cases` accetta gli ID elencati dal comando `list`. `--timeout` è espresso in secondi; `--output` sceglie una directory nuova o vuota. `--thinking` accetta `off`, `minimal`, `low`, `medium`, `high`, `xhigh` o `max` e prevale sul default senza fallback. Il runner randomizza l'ordine delle task; `--seed NUMERO` permette di riprodurre esattamente lo stesso ordine, registrato anche in `run.json`. `--sandbox` accetta `audit`, `auto` o `required`: `required` è la scelta corretta quando il run non deve continuare senza isolamento OS.

### Controllo thinking

Il benchmark ufficiale usa `--thinking off`. Prima di eseguire qualsiasi caso, per ogni modello Ollama il runner legge `/api/show`; per LM Studio e llama.cpp usa i metadati dell'endpoint modelli. Poi invia una richiesta minima a `/v1/chat/completions` con `reasoning_effort: "none"`. La configurazione isolata di Pi contiene lo stesso parametro, `max_tokens`, timeout idle disabilitato e zero retry; il warmup usa l'API del provider scelto. `--no-warmup` evita solo il warmup aggiuntivo, non il preflight obbligatorio.

Con llama.cpp, il runner attende che `/models` confermi `loaded` dopo `/models/load`, sia nel preflight sia prima delle task, e `unloaded` dopo `/models/unload` prima di cambiare modello. Se il processo del modello fallisce o il caricamento supera il timeout, il modello viene escluso senza avviare l'inferenza. Se lo scaricamento fallisce o scade, il runner segnala l'errore; il caricamento successivo può fallire e il modello viene escluso.

Un preflight rifiutato o non verificabile esclude il modello prima delle task senza fermare gli altri. In una coorte `off`, reasoning osservabile o retry inattesi durante una task escludono l'intero modello. Il preflight registra solo stato, durata e conteggi: non conserva la traccia di reasoning. Le modalità attive richiedono la capability `thinking` e un segnale osservabile; devono essere eseguite in directory e coorti separate. Non usare una seconda modalità solo per i modelli falliti: se si confrontano `off` e `medium`, tutti i modelli devono ricevere entrambe con condizioni simmetriche.

Nell'export e nella dashboard, `thinking` e `showcase` restano profili indipendenti: sono filtrabili e mostrano modalità e controllo thinking, ma non diventano fasi del funnel `smoke` → `standard` → `full`. Le classifiche di run `off` e `medium` sono presentate in gruppi separati e non fuse in un rank combinato.

### Confronto statistico tra run

```bash
python3 benchmark.py compare results/RUN-1 results/RUN-2 results/RUN-3
```

Il confronto accetta soltanto directory distinte e run con versione/parametri, profilo, casi, fingerprint input, digest/capability modello, controllo thinking, retry, timeout idle, versioni Pi/Ollama, backend sandbox, piattaforma e hardware registrato compatibili. I run legacy restano consultabili come `thinking_control: unverified`, ma non si aggregano ai run verificati. Il comando genera `comparison.json` e `COMPARISON.md` con media, mediana, deviazione standard e intervallo al 95% approssimato, limitato al dominio naturale della metrica. I modelli assenti o esclusi per integrità non ricevono un campione per quel run.

### Dataset e finalissima dashboard

Per testare il sistema senza un benchmark Pi/Ollama reale:

```bash
python3 -m unittest tests.test_dashboard_data -v
python3 benchmark.py case validate results_dashboard
```

Dopo i run reali, aggregare profili anche diversi con il comando dedicato, non con `compare`:

```bash
python3 benchmark.py dashboard-data \
  results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN \
  --output results/finalists-dashboard-data.json
```

Il comando accetta `run.json` e `report.json` schema 2, 3 o 4, con massimo 32 MiB per file. Produce schema dashboard 3 e continua a leggere i dataset schema 1 e 2. Registra hash e commit e usa una whitelist: mantiene soltanto profilo, sandbox, integrità sintetica, stato/livello thinking, partecipanti, classifiche, metriche task e codici d'esclusione con eventuale ID del caso. I run storici sono marcati `unverified`; preflight dettagliati e contenuto del reasoning non vengono esportati. Non copia path, prompt, risposte, comandi, log, evidenze di violazione o messaggi di errore liberi. Input e output devono restare nella root del progetto; non è consentito scrivere dentro un run sorgente. Per sostituire atomicamente un output già esistente aggiungere `--force`.

Revisionare il JSON, quindi congelarlo nella fixture:

```bash
python3 benchmark.py dashboard-data \
  results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN \
  --output cases/results_dashboard/fixture/dashboard-data.json \
  --force
python3 benchmark.py case validate results_dashboard
```

Dopo una validazione riuscita, controllare e committare soltanto la fixture congelata:

```bash
git status --short
git diff -- cases/results_dashboard/fixture/dashboard-data.json
git add -- cases/results_dashboard/fixture/dashboard-data.json
git diff --cached --name-only
git diff --cached --check
git commit -m "test: freeze showcase finalist dataset"
git status --short
```

Prima del commit, `git diff --cached --name-only` deve elencare soltanto `cases/results_dashboard/fixture/dashboard-data.json`, salvo altri aggiornamenti intenzionali già revisionati. Non usare `git add .`. L'ultimo controllo non deve mostrare modifiche residue ad `AGENTS.md`, `.gitignore` o agli input del caso; gli eventuali aggiornamenti intenzionali del piano o della documentazione vanno revisionati e committati separatamente. Il push non è necessario per il run locale; usare `git push` sul branch corrente soltanto quando occorre condividere il commit o attivare la CI.

Eseguire quindi soltanto i finalisti con `python3 benchmark.py run --profile showcase --models MODEL-A MODEL-B --thinking off --sandbox required`. Anche la finalissima attraversa capability discovery, preflight e controllo task della milestone 7. Il runner consegna la stessa fotografia a tutti. Il grader tecnico vale 100 punti e usa anche un dataset nascosto; la rubrica visuale da 20 punti resta manuale e separata. Per avvio locale, import multiplo e checklist browser seguire [QUICK-START_Showcase.md](QUICK-START_Showcase.md).

La finalissima resta un test valido anche quando nessun modello supera 60/100. Conservare timeout, errori, punteggi sotto soglia e baseline non modificate come risultati negativi; non cambiare dataset o grader per ottenere una dashboard completata. La revisione manuale può assegnare `0/20` oppure indicare “non applicabile” quando non esiste un'interfaccia funzionante, senza modificare lo score automatico.

### Dashboard ufficiale dei risultati

La dashboard ufficiale sotto `dashboard/` è il lettore stabile mantenuto dal progetto; non va confusa con le dashboard prodotte dai modelli durante la finalissima. Per visualizzare tutti i run compatibili presenti direttamente sotto `results/`, eseguire dalla root del repository:

```bash
python3 dashboard.py
```

Il comando aggrega i run validi soltanto in memoria, avvia un server su `127.0.0.1` con una porta libera, apre il browser e stampa l'URL. Non serve file raw e non modifica i risultati. Terminare con `Ctrl+C`. Se non esistono run compatibili, serve in memoria la fixture dashboard revisionata.

La sezione **Mappa di efficienza** mostra, separatamente per ogni run e modalità thinking, il rapporto tra `quality_score` e durata mediana e tra `quality_score` e token mediani di output. Gli assi orizzontali sono logaritmici: spostarsi verso sinistra significa consumare meno tempo o token, mentre salire significa ottenere qualità maggiore. I numeri nei punti corrispondono alla legenda sottostante; punto pieno, punto ciano e punto vuoto indicano rispettivamente completamento 100%, parziale e nessuna task sopra soglia. Passare sul punto o raggiungerlo con `Tab` mostra i valori completi. Non confrontare visivamente coorti diverse come se fossero un unico esperimento.

È possibile scegliere sorgenti e comportamento in modo esplicito:

```bash
python3 dashboard.py results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN
python3 dashboard.py --dataset results/finalists-dashboard-data.json
python3 dashboard.py --no-open --port 8765
```

- le directory passate come argomenti devono essere run distinti dentro la root del progetto;
- `--dataset` accetta un singolo export già sanificato prodotto da `dashboard-data` e non si combina con directory di run;
- `--no-open` evita l'apertura automatica del browser; copiare l'URL stampato;
- `--port 0`, valore predefinito, sceglie una porta disponibile; una porta fissa occupata produce un errore chiaro.

Il pulsante **Scegli file** dentro la pagina serve solo per aggiungere uno o più file `dashboard-data.json` compatibili. Non scegliere `run.json`, `report.json`, una directory, `REPORT.md`, `result.json`, log o altri artefatti raw. Per crearne uno:

```bash
python3 benchmark.py dashboard-data \
  results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN \
  --output results/finalists-dashboard-data.json
```

L'importazione resta nella memoria della scheda del browser: non invia dati in rete e non committa file. Ricaricando la pagina si torna alla sorgente iniziale. Lingua e tema sono le sole preferenze persistite nel `localStorage` del browser. Uno snapshot opzionale per `file://` può essere generato con `python3 dashboard.py --refresh-snapshot --force`: è ignorato da Git e non deve mai essere committato. La guida breve completa è [QUICK-START_Dashboard.md](QUICK-START_Dashboard.md).

### Landing page del progetto

La landing page pubblica è mantenuta sotto `site/` ed è pubblicata all'indirizzo `https://gloutchov.github.io/LocalAgentBenchmark/`. Per controllarla localmente dalla root del repository:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

Aprire `http://127.0.0.1:8000/` e terminare il server con `Ctrl+C`. L'introduzione mostra subito i pulsanti per repository, ultima release e percorso rapido. La voce «Novità» apre la sezione dedicata a Ollama, LM Studio e llama.cpp, prima del punto 01; lì si trova anche la guida ai provider. Il resto della pagina presenta criteri, profili, metodo, controlli, dashboard e documentazione. Non è la dashboard dei risultati e non legge le directory `results/`.

La lingua iniziale segue il browser: italiano per locale italiani, inglese in ogni altro caso. Il selettore consente l'override manuale. Il tema può essere automatico, chiaro o scuro. Soltanto queste due preferenze vengono salvate in `localStorage`; la pagina non usa cookie, form, analytics o telemetria. Tutti gli asset runtime sono locali. I link esterni effettuano una normale navigazione solo quando vengono attivati.

Per manutenerla, aggiornare insieme i testi italiano/inglese in `site/js/i18n.js`, conservare i percorsi compatibili con il prefisso `/LocalAgentBenchmark/` e verificare immagini, testo alternativo, 404, link e metadata. Le immagini pubblicabili in `site/assets/` sono fotogrammi ottimizzati e revisionati; `assets/Dashboard.mov` resta un sorgente locale ignorato da Git e non deve essere pubblicato. Eseguire i test indicati nel README e una verifica browser desktop/mobile prima di ogni deploy.

## 5. Configurazione

`benchmark.json` contiene tutti i parametri modificabili:

- `provider.kind` (`ollama`, `lmstudio`, `llama_cpp`) e `provider.url`: runtime e endpoint HTTP su loopback; la vecchia sezione `ollama.url` resta leggibile;
- `provider.runtime_version` e `provider.model_files`: versione dichiarata e path GGUF opzionali per il singolo run, obbligatori per aggregare run dei provider alternativi;
- `pi.command`: comando e argomenti iniziali di Pi;
- `models`: `installed` oppure lista stabile;
- `defaults`: timeout task/preflight, ripetizioni, thinking, timeout idle HTTP, retry agente/provider, warmup, keep-alive, contesto, output massimo, temperatura e modalità sandbox;
- `profiles`: gruppi di casi;
- `cases.directory`: directory, interna al repository, da cui scoprire i manifesti `case.json`.
- `dashboard`: directory degli asset, directory dei risultati, sorgente dello snapshot, host loopback, porta e apertura automatica del browser.
- `guided`: sequenza obbligatoria `smoke`, `standard`, `full`, limiti di promozione decrescenti `4`, `2` e file locale delle preferenze GUI.

La configurazione viene validata all'avvio. Non contiene e non deve contenere segreti. Pi riceve una chiave fittizia pari all'ID del provider; sono supportati server locali senza autenticazione. I GGUF dichiarati sono letti dall'host per calcolare SHA-256, senza copiarli nei risultati; la corrispondenza fra ID modello e file è dichiarata dall'utente. La versione runtime non è verificata automaticamente. Un run singolo funziona senza questi campi, ma `compare` richiede versione e digest per LM Studio/llama.cpp. La GUI e la CLI usano la stessa selezione; per cambiarla occorre modificare `benchmark.json` prima di avviare un nuovo run.

### Creazione e validazione di casi personali

Creare uno scheletro autocontenuto:

```bash
python3 benchmark.py case create api_contract \
  --title-it "Contratto API" \
  --title-en "API contract" \
  --category architecture \
  --weight 1.25 \
  --manual-rubric
```

Il comando crea `case.json`, `prompt.md`, `fixture/`, `grader.py` e, se richiesta, `manual-rubric.md`. I metadati e il peso vivono nel manifesto; per eseguire il caso non serve modificare il core. Aggiungere l'ID a un profilo di `benchmark.json` soltanto se deve far parte stabilmente di quel gruppo.

Dopo aver personalizzato materiali sintetici e controlli, validare il caso:

```bash
python3 benchmark.py case validate api_contract
```

Senza ID, `case validate` controlla tutti i casi. Verifica schema strutturale, path confinati, file richiesti, contratto JSON del grader, somma di 100 punti e baseline sotto 60. Il grader viene eseguito con i permessi dell'utente e fuori dalla sandbox dell'agente: revisionare sempre il codice dei casi importati prima della validazione. La guida completa è in [QUICK-START_Case-Author.md](QUICK-START_Case-Author.md).

## 6. Come leggere il report

Il totale combina qualità (80%), completamento (10%), velocità relativa (5%) ed efficienza token relativa (5%). Una task è completata a 60/100 con uscita Pi corretta.

Leggere prima **Ambiente e isolamento** e **Integrità del run**. La prima sezione distingue backend richiesto ed effettivo e non presenta il fallback come sandbox. L'audit segue `$PWD` e i cambi `cd` anche nei comandi multilinea: un path `../` che resta nella workspace, per esempio nello scratch interno, non è una violazione. Un modello che riferisce esplicitamente un path risolto fuori workspace, tenta la rete, modifica il repository o lo snapshot, oppure riceve una baseline divergente viene escluso integralmente dalla classifica anche se il grader ha assegnato punti. Una mutazione dello snapshot interrompe le task successive. Il report elenca modello, caso, ripetizione, motivo, target ed evidenza; `run.json` conserva hardware, sandbox, commit e stato Git iniziali, seed, ordine, hash degli input e della policy, e violazioni. Ogni `result.json` conserva tree della baseline, versione dell'audit, metriche di sistema e dettagli originali.

- Dare priorità a `quality_score` e ai casi più simili al proprio lavoro.
- Usare `median_duration_seconds` per capire l'attesa quotidiana.
- Usare `tool_errors` per scoprire incompatibilità nel tool calling.
- Confrontare `score_stddev` dopo almeno tre ripetizioni.
- Trattare energia RAPL come misura host-wide: è utile soltanto a parità di macchina e carico, non come consumo esclusivo del modello.
- Aprire `diff.patch` e `workspace/` prima di scegliere il modello.
- Se esiste `manual-rubric.md`, compilarla separatamente: non entra nel punteggio automatico.

Il modello primo in classifica non è automaticamente il migliore per ogni uso. Per attività security-sensitive può essere preferibile il migliore nel caso `secure_workspace`; per manutenzione ordinaria conta di più `targeted_patch`.

## 7. Riproducibilità

Usare stessa configurazione, stesso profilo, stessa modalità thinking, stesso numero di ripetizioni, stesso seed e stesso computer. Chiudere carichi pesanti e mantenere condizioni termiche/alimentazione comparabili. Il runner scarica il modello, esegue il preflight separato e lo scarica di nuovo; prima di ogni cambio modello può poi registrare un warmup aggiuntivo e avviare la task. Preflight e warmup non entrano nei tempi o token della task.

All'avvio `AGENTS.md`, `.gitignore`, manifesti, prompt, fixture, grader e rubriche selezionati devono essere puliti rispetto a Git. Il runner copia una volta in `benchmark-context/` soltanto i file tracciati e la policy di esecuzione, escludendo cache e output ignorati, e tutte le workspace nascono da quella fotografia. Gli hash degli input includono anche manifesto e rubrica. Ogni workspace contiene `.benchmark-scratch/`, ignorata da Git e usata anche come `TMPDIR`, `TMP` e `TEMP`: i modelli devono usarla per smoke test e file temporanei senza ricorrere a `/tmp`. Non modificare né sorgenti né snapshot durante il run. La temperatura zero limita, ma non elimina, la variabilità. Conservare l'intera directory del run quando il risultato deve essere confrontato nel tempo.

## 8. Risoluzione problemi

- Provider locale non raggiungibile: avviare il server configurato in `benchmark.json` e verificare `benchmark.py doctor`.
- GUI guidata senza modelli o prerequisiti: usare **Rileva di nuovo** dopo aver avviato il provider/installato Pi; gli input protetti sporchi devono essere revisionati e committati, non aggirati.
- percorso guidato interrotto: consultare `results/guided-*/guided-run.json` e i run già creati; nessun risultato parziale viene promosso e nessun run precedente viene cancellato.
- dashboard guidata non avviabile: usare **Riapri dashboard** dopo aver risolto il problema locale; da uno a tre run disponibili vengono riutilizzati senza rieseguire i modelli.
- `pi: comando non trovato`: installare Pi o modificare `pi.command` con il percorso corretto.
- `Modelli non installati`: usare il nome esatto restituito da `doctor` e installare/importare il modello nel provider configurato.
- `timeout`: aumentare `--timeout` o `defaults.timeout_seconds` per la GUI; controllare anche memoria e log `stderr.log`. Il limite riguarda ciascuna task e non include preflight e warmup.
- `pi_error`: controllare `pi-events.jsonl` e `stderr.log`; un errore terminale agente/provider viene classificato come operativo anche quando il processo Pi termina con codice zero. Il testo libero dell'errore resta negli artefatti locali e non viene esportato da `dashboard-data`.
- score basso con uscita corretta: leggere `grade.json`; il modello può aver risposto senza modificare i file o aver interpretato male un vincolo.
- token a zero: alcune combinazioni provider/modello non riportano usage; la qualità resta valida, mentre l'efficienza token non viene premiata.
- `Input benchmark modificati`: ripristinare o committare intenzionalmente `AGENTS.md`, `.gitignore` e i file dei casi prima di riprovare; non usare una fixture già completata.
- `Manifesto mancante` o `paths.*`: completare `case.json`, usare soltanto path relativi POSIX interni al caso e rimuovere symlink sui path dichiarati; rieseguire `case validate`.
- errore `max_score`, `points`, `earned` o baseline: correggere il contratto del grader; i check devono totalizzare 100 e la fixture iniziale deve restare sotto 60.
- errore `Controllo compatibilità Pi fallito`: leggere il controllo indicato, verificare il comando `pi` e la sandbox selezionata; Pi 0.85.1 è la versione di riferimento verificata, ma non risolve necessariamente ogni problema;
- `thinking_control_unverified`: controllare capability, esito preflight, versione del provider e supporto del livello richiesto; non forzare un fallback;
- `unexpected_thinking` o `unexpected_retry`: conservare gli artefatti, escludere il modello e correggere il controllo prima di un nuovo run;
- errore `dashboard-data`: verificare schema 2/3/4, coerenza del profilo, directory distinte e path interni alla root; usare `--force` soltanto dopo aver revisionato il file da sostituire.
- dashboard senza dati aprendo direttamente `index.html`: usare `python3 dashboard.py` oppure generare prima lo snapshot locale opzionale.
- nessun run locale nella dashboard: verificare che ogni directory immediatamente sotto `results/` contenga `run.json` e `report.json` compatibili, oppure passare directory esplicite.
- porta dashboard occupata: omettere `--port`, usare `--port 0` o scegliere un altro numero.
- il browser non si apre: usare `python3 dashboard.py --no-open` e aprire manualmente l'URL stampato.
- **Scegli file** rifiuta il file: generare e selezionare `dashboard-data.json`, non `run.json` o `report.json`; il limite è 32 MiB per file.
- `violations_detected`: leggere prima la tabella **Violazioni rilevate**, poi aprire `report.json`, `run.json` e il relativo `pi-events.jsonl`; il modello indicato è escluso e non va reinserito manualmente in classifica. La rigenerazione del report applica l'audit corrente agli eventi più vecchi senza cambiare i `result.json` originali.
- `snapshot_compromised`: il runner ha interrotto la matrice perché la fotografia condivisa non è più affidabile; conservare gli artefatti per diagnosi e avviare un nuovo run solo dopo aver risolto la causa.
- `Sandbox OS richiesta ma non disponibile`: installare/abilitare il backend indicato da `doctor`, usare consapevolmente `--sandbox auto` per consentire fallback oppure `--sandbox audit` per il comportamento storico.
- `linux-bubblewrap` non disponibile: verificare `bwrap`, `unshare` e la policy di user namespace seguendo il quick start Linux; non eseguire il benchmark come root per aggirare il probe.
- `windows-appcontainer` non disponibile: eseguire `doctor` come utente standard e verificare ACL, profilo AppContainer e named pipe seguendo il quick start Windows.

Il runner restituisce exit code `1` se una o più task terminano con errore o timeout, gli eventi terminano con un errore agente/provider oppure l'integrità non è valida, ma scrive comunque il report disponibile. Uno score basso con stato `ok` e integrità `ok` è invece un risultato negativo valido e non rende fallito il comando.

## 9. Sicurezza e privacy

Non inserire dati privati, repository reali o credenziali nelle fixture. Manifesti e template non concedono permessi: un grader importato resta codice non fidato finché non viene revisionato, perché validazione e grading lo eseguono sul processo host. `audit` e il fallback di `auto` non sono sandbox. Il percorso guidato usa argomenti strutturati senza shell, accetta soltanto provider HTTP su loopback, conserva manifesto e risultati dentro la root e richiede conferma prima dell'avvio e dell'annullamento; `results/` resta potenzialmente sensibile. Il backend macOS restringe file utente esterni e rete salvo la porta loopback del provider ed è basato sulla deprecata interfaccia `sandbox-exec`. Su Linux Pi opera in un network namespace vuoto e raggiunge soltanto il broker del provider tramite un socket Unix interno alla workspace. Su Windows AppContainer non riceve capability di rete e usa un named pipe dedicato al suo SID; ACL temporanee concedono solo i path necessari e un Job Object termina i discendenti. Broker e grader restano processi fidati eseguiti fuori sandbox. Il dataset dashboard omette contenuti raw ma conserva nomi modello, titoli, metriche e hash: resta un file locale potenzialmente sensibile e non deve essere pubblicato automaticamente. Il server ufficiale è confinato a `127.0.0.1`, serve soltanto asset autorizzati e il dataset pubblico in memoria, ma altri processi locali e le estensioni del browser restano fuori dal suo confine di fiducia. Consultare `SECURITY_MODEL.md`.

## 10. Limiti noti

- I grader automatici non misurano interamente leggibilità o qualità delle spiegazioni.
- Le rubriche manuali sono artefatti di supporto: il runner non raccoglie né aggrega il punteggio umano.
- I tempi dipendono da hardware, quantizzazione, pressione di memoria e temperatura.
- Il runner supporta Ollama, LM Studio e il router llama.cpp; non offre ancora un adapter Codex di controllo né un bridge `node-llama-cpp` diretto.
- I task sono sintetici e devono essere ampliati quando cambia il tipo di lavoro abituale.
- Il backend Linux dipende da user/network namespace non privilegiati; su host con policy kernel o AppArmor più restrittive il probe fallisce e `required` interrompe il run.
- AppContainer concede lettura al runtime Pi e applica/rimuove ACL e profilo in best effort; un arresto anomalo del launcher può richiedere pulizia o diagnosi manuale.
- Il broker inoltra soltanto alla destinazione provider configurata, ma non autentica né filtra semanticamente il contenuto delle richieste.
- Comandi dinamici o offuscati possono ancora eludere l'audit quando non è attivo un backend enforced.
- `sandbox-exec` è deprecato e può non essere disponibile in future versioni macOS; `required` evita fallback silenziosi.
- Le metriche POSIX possono non includere integralmente tutti i discendenti; RAPL misura il sistema host e può non essere leggibile senza privilegi.
- Il grader della dashboard verifica trasformazioni e requisiti osservabili, ma responsive, resa visuale, tastiera e assenza di richieste remote richiedono anche una prova in browser e la rubrica manuale sul workspace candidato.
- La dashboard ufficiale non rende anonimo un export e non pubblica risultati: nomi, punteggi e hash vanno revisionati prima di condividere lo snapshot o un `dashboard-data.json`.
- Il preflight prova il comportamento osservabile dell'endpoint, non può dimostrare processi interni che il provider o il modello non espongono. Un modello che non espone reasoning in modalità attiva viene escluso come non verificabile.
- I launcher guidati sono script sorgente, non installer o applicazioni firmate; il doppio clic Linux dipende dal file manager e Tkinter deve essere incluso nella distribuzione Python.
- Una sessione guidata annullata o fallita viene conservata ma non può essere ripresa dal punto interrotto; la dashboard può comunque riaprire da uno a tre run già disponibili senza un nuovo benchmark.
