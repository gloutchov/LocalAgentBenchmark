# LocalAgent Benchmark

Benchmark personale, ripetibile e offline per confrontare modelli Ollama usati come coding agent tramite [Pi](https://pi.dev). Gli scenari derivano dalle regole operative di questo repository: patch piccole, architettura modulare, test, sicurezza, configurazione, i18n, documentazione e disciplina Git.

Personal, repeatable, offline benchmark for comparing Ollama models used as coding agents through [Pi](https://pi.dev). Its scenarios derive from this repository's operating rules: small patches, modular architecture, tests, security, configuration, i18n, documentation, and Git discipline.

Stato / Status: **0.12.0 – compatibilità Pi verificata all’avvio / Pi compatibility checked at startup**
Piattaforme / Platforms: macOS, Windows, Linux
Verifica reale / Real-world validation: **run benchmark Pi/Ollama reali verificati soltanto su macOS e Windows; Linux è coperto dalla CI, ma non è ancora stato validato con uno smoke Pi/Ollama reale. / Real Pi/Ollama benchmark runs have been verified only on macOS and Windows; Linux is covered by CI, but has not yet been validated with a real Pi/Ollama smoke run.**
Licenza / License: Apache-2.0

## Cosa misura / What it measures

Il benchmark valuta il risultato completo dell'agente, non una singola risposta testuale:

- qualità funzionale tramite grader e test indipendenti dal prompt;
- rispetto di scope, API e file non correlati;
- sicurezza di path, scritture e log;
- configurazione validata, i18n e preferenze UI;
- aggiornamento coordinato di versione, piano e documentazione;
- casi personali descritti da manifesti validati, con pesi e rubriche manuali opzionali;
- pianificazione esatta multi-vincolo con scenari nascosti per misurare il beneficio osservabile del thinking senza richiederne la traccia;
- esportazione privacy-bounded dei run, finalissima dashboard separata e dashboard ufficiale offline con mappe qualità/tempo e qualità/token;
- stato di uscita, timeout, errori tool, token e tempo end-to-end.

The benchmark evaluates the complete agent outcome rather than a single text response: functional quality, scope discipline, security, configuration/i18n, exact multi-constraint planning, documentation, Git workflow, failures, tokens, and end-to-end time. It also provides privacy-bounded run exports, a separate model dashboard showcase, and an official offline results viewer.

Il punteggio composito pesa **qualità 80%**, **completamento 10%**, **velocità relativa 5%** ed **efficienza token relativa 5%**. Qualità e tempi restano visibili separatamente; un modello veloce che non completa il task non viene favorito in modo sostanziale.

## Requisiti / Requirements

- Python 3.10 o successivo;
- Git;
- Ollama avviato su `http://127.0.0.1:11434`;
- Pi installato e disponibile come comando `pi`;
- almeno un modello Ollama già scaricato e capace di tool calling.

La sandbox OS è opzionale: macOS usa `sandbox-exec`; Linux richiede `bwrap`, `unshare` e user/network namespace utilizzabili; Windows 10/11 usa AppContainer. Ogni backend viene applicato solo dopo un probe reale. `doctor` mostra sempre il backend e le capacità effettivamente disponibili.

The OS sandbox is optional: macOS uses `sandbox-exec`; Linux requires `bwrap`, `unshare`, and usable user/network namespaces; Windows 10/11 uses AppContainer. Each backend is enabled only after a real probe. `doctor` always reports the backend and capabilities that are actually available.

Non servono pacchetti Python esterni. `doctor` e ogni run verificano il comando Pi configurato su un server OpenAI-compatible sintetico in loopback prima delle task. Sono accettate le versioni che superano il contratto; se fallisce, il programma indica il controllo fallito e suggerisce Pi **0.85.1** come versione di riferimento verificata.

No external Python packages are required. `doctor` and every run test the configured Pi command against a synthetic OpenAI-compatible loopback server before tasks. Versions that pass the contract are accepted; on failure, the program identifies the failed check and suggests Pi **0.85.1** as the verified reference version.

Il controllo Pi usa tre richieste sintetiche, tool disabilitati, `--offline` e la sandbox selezionata; `defaults.pi_contract_timeout_seconds` limita ogni richiesta (default 30 s). La GUI lo esegue nel rilevamento e lo ripete in ogni fase. Stato e versione del contratto sono registrati in `run.json`, senza contenuti del probe. Il preflight thinking del modello Ollama resta separato. / The Pi check uses three synthetic requests, disabled tools, `--offline`, and the selected sandbox; `defaults.pi_contract_timeout_seconds` limits each request (default 30 s). The GUI checks during discovery and again in every phase. `run.json` records only the contract version and status. The Ollama model thinking preflight remains separate.

Per vedere subito risultati comprensibili, avviare la dashboard locale; userà automaticamente i run compatibili presenti in `results/`:

```bash
python3 dashboard.py
```

To see understandable results immediately, start the local dashboard with `python3 dashboard.py`; it automatically loads compatible runs from `results/`. See [QUICK-START_Dashboard.md](QUICK-START_Dashboard.md) for explicit runs, JSON import, optional local snapshot generation, and troubleshooting.

## Avvio rapido / Quick start

Per evitare di comporre comandi, aprire con doppio clic il launcher sorgente della propria piattaforma:

- macOS: `launchers/LocalAgent-Benchmark.command`;
- Windows: `launchers\LocalAgent-Benchmark.cmd`;
- Linux: `launchers/LocalAgent-Benchmark.sh` e scegliere **Esegui** se richiesto dal file manager.

La GUI rileva i modelli Ollama, permette di ordinarli per nome, dimensione o thinking e offre toggle per thinking `off`/`medium` e sandbox `audit`/`required`. Le scelte valgono per tutte le fasi; `required` fallisce se l'isolamento OS non è disponibile, mentre `audit` non isola. Dopo conferma esegue `smoke` su tutti i selezionati, promuove al massimo `4` modelli a `standard` e al massimo `2` a `full`, quindi apre la dashboard ufficiale sui tre run. Nel Dettaglio task della dashboard le esclusioni per thinking o violazioni d'integrità compaiono separatamente dalle task svolte. Una task fallita esclude il solo modello interessato se il resto della fase è completo e verificabile. Il percorso non esegue `showcase` né chiede ai modelli di costruire una dashboard. Guida completa: [QUICK-START_Guided.md](QUICK-START_Guided.md).

For a command-free start, double-click the source launcher for macOS, Windows, or Linux. The GUI detects local Ollama models, supports sorting, and offers thinking `off`/`medium` and sandbox `audit`/`required` toggles for all stages. `required` fails when OS isolation is unavailable; `audit` does not isolate. After confirmation it runs the `all → 4 → 2` funnel and opens the official dashboard. Task details lists thinking and integrity exclusions separately from executed tasks. A failed task excludes only its model when the stage remains complete and verifiable. It never runs `showcase` or asks models to build a dashboard. See [QUICK-START_Guided.md](QUICK-START_Guided.md).

La durata dipende da hardware, modelli e casi e non è garantita. Annullamento ed errori preservano gli artefatti diagnosticabili senza promuovere dati parziali; **Riapri dashboard / Reopen dashboard** riutilizza da uno a tre run disponibili dell'ultima sessione senza rieseguire i modelli.

Duration depends on hardware, models, and cases and is not guaranteed. Cancellation and failures preserve diagnostic artifacts without promoting partial data; **Reopen dashboard** reuses one to three available runs from the latest session without rerunning models.

Per il flusso da terminale / For the terminal workflow:

```bash
python3 benchmark.py doctor
python3 benchmark.py list
python3 benchmark.py case validate
python3 benchmark.py run --profile smoke --models qwen3.5:9b-Q4_K_M --thinking off
```

Per verificare la finalissima senza eseguire modelli reali:

```bash
python3 -m unittest tests.test_dashboard_data -v
python3 benchmark.py case validate results_dashboard
```

Per richiedere isolamento OS senza accettare fallback:

```bash
python3 benchmark.py run --profile smoke --models qwen3.5:9b-Q4_K_M --sandbox required
```

Per creare e validare un caso personale senza modificare il core:

```bash
python3 benchmark.py case create api_contract \
  --title-it "Contratto API" \
  --title-en "API contract" \
  --category architecture \
  --weight 1.25 \
  --manual-rubric
python3 benchmark.py case validate api_contract
```

Il comando crea atomicamente `cases/api_contract/` con manifesto, prompt, fixture, grader calibrato e rubrica opzionale. Personalizzare gli input sintetici e committarli prima di un run; il nuovo caso è subito selezionabile con `--cases api_contract` e può essere aggiunto a un profilo in `benchmark.json`. La procedura completa è in [QUICK-START_Case-Author.md](QUICK-START_Case-Author.md).

The command atomically creates `cases/api_contract/` with a manifest, prompt, fixture, calibrated grader, and optional rubric. Customize and commit the synthetic inputs before a run; the case is immediately selectable with `--cases api_contract` and can be added to a `benchmark.json` profile. See [QUICK-START_Case-Author.md](QUICK-START_Case-Author.md) for the complete workflow.

Per un primo confronto di tutti i modelli installati:

```bash
python3 benchmark.py run --profile standard
```

For a more reliable final comparison, run the full profile three times:

```bash
python3 benchmark.py run --profile full --repetitions 3
```

Un run completo con molti modelli può richiedere ore. Conviene prima eseguire `smoke`, eliminare i modelli incompatibili con gli strumenti e poi usare `standard` o `full` sui finalisti.

## Profili / Profiles

| Profilo | Casi | Uso consigliato |
|---|---:|---|
| `smoke` | 1 | Verifica rapida di integrazione Pi/Ollama e tool calling |
| `standard` | 4 | Confronto principale; include il caso multi-vincolo `thinking_challenge` |
| `full` | 5 | Aggiunge versioning, documentazione e disciplina Git |
| `thinking` | 1 | Esperimento rapido e indipendente sul solo `thinking_challenge` |
| `showcase` | 1 | Fa costruire ai finalisti una dashboard offline dallo stesso dataset congelato |

È possibile selezionare modelli e casi esplicitamente:

```bash
python3 benchmark.py run \
  --models devstral-small-2:latest qwen3.6:27b \
  --cases targeted_patch secure_workspace \
  --repetitions 2 \
  --timeout 1800 \
  --thinking off \
  --seed 20260829
```

Su PowerShell, inserire il comando su una sola riga oppure usare il carattere di continuazione appropriato.

## Controllo thinking / Thinking control

Il benchmark ufficiale usa `off`. Prima delle task, per ogni modello, il runner legge le capability da Ollama e prova realmente `reasoning_effort: "none"` sullo stesso endpoint OpenAI-compatible usato da Pi. La configurazione Pi isolata ripete il valore in `samplingParams`, disabilita timeout HTTP idle e retry automatici, e il warmup usa `think: false`. Se il controllo viene rifiutato, compare reasoning osservabile oppure Pi emette un retry inatteso, l'intero modello viene escluso dalla classifica. Il preflight è obbligatorio anche con `--no-warmup`; non salva la catena di pensiero.

The official benchmark uses `off`. Before any task, the runner reads Ollama capabilities and actually probes `reasoning_effort: "none"` through the same OpenAI-compatible endpoint used by Pi. Isolated Pi configuration repeats that value in `samplingParams`, disables HTTP idle timeouts and automatic retries, and warmup uses `think: false`. A rejected control, observable reasoning, or an unexpected Pi retry disqualifies the entire model. The preflight remains mandatory with `--no-warmup` and never stores its chain of thought.

`--thinking off|minimal|low|medium|high|xhigh|max` crea coorti separate senza fallback silenziosi. `minimal`/`low` diventano `low`, `xhigh`/`max` diventano `max`; una modalità attiva richiede capability thinking e reasoning osservabile nel preflight. Non confrontare né aggregare run `off` e run attivi: `compare` li rifiuta. Per un esperimento A/B usare gli stessi modelli, digest, casi, seed e parametri in directory distinte.

`--thinking off|minimal|low|medium|high|xhigh|max` creates separate cohorts without silent fallback. `minimal`/`low` map to `low`, while `xhigh`/`max` map to `max`; active modes require a thinking capability and observable reasoning in preflight. Do not compare or aggregate `off` and active runs: `compare` rejects them. For A/B experiments, use the same models, digests, cases, seed, and parameters in distinct directories.

Il profilo indipendente `thinking` esegue soltanto `thinking_challenge`, un pianificatore esatto con budget, rischio, capacità team, dipendenze, conflitti, categorie obbligatorie e tie-break deterministico. Il grader usa anche scenari non presenti nella fixture e valuta esclusivamente output, test e documentazione. Per una misura A/B eseguire almeno tre ripetizioni `off` e tre `medium` per ogni modello, in directory diverse e con gli stessi seed/parametri; alternare l'ordine delle coorti quando possibile. Timeout ed errori restano risultati della rispettiva coorte e non autorizzano retry selettivi.

The independent `thinking` profile runs only `thinking_challenge`, an exact planner with budget, risk, team capacity, dependencies, conflicts, required categories, and deterministic tie-breaking. Its grader also uses scenarios absent from the fixture and evaluates only outputs, tests, and documentation. For an A/B measurement, run at least three `off` and three `medium` repetitions for every model in separate directories with matching seeds and parameters; counterbalance cohort order when possible. Timeouts and errors remain outcomes of their cohort and never grant selective retries.

## Output e lettura / Output and interpretation

Ogni run crea `results/YYYYMMDD-HHMMSS/` con:

- `REPORT.md` e `report.json`: classifica, isolamento effettivo, metriche disponibili e dettaglio;
- `run.json`: ambiente/hardware, versioni, backend sandbox effettivo, commit/stato Git, modelli/capability, seed, ordine task, hash input, policy di esecuzione, controllo/preflight thinking, retry, timeout idle, warmup e stato d'integrità;
- per ogni modello/caso: workspace finale, eventi JSONL di Pi, risposta finale, stderr, stato Git, patch, score, singoli check e, quando dichiarata, `manual-rubric.md` separata dal punteggio automatico.

All'avvio il runner rifiuta `AGENTS.md`, `.gitignore`, manifesti, prompt, fixture, grader o rubriche selezionati se modificati rispetto a Git. Crea poi un unico snapshot dei soli file tracciati e della policy di esecuzione, escludendo cache e output ignorati, e registra hash e tree Git delle baseline. Ogni task riceve una directory `.benchmark-scratch/` interna e ignorata da Git; `TMPDIR`, `TMP` e `TEMP` puntano lì. L'audit segue i cambi `cd` e `$PWD` anche nei comandi su più righe: un traversal di prova che resta nello scratch interno è valido. Path shell risolti fuori workspace, tentativi espliciti di rete, modifiche al repository o allo snapshot e baseline non uniformi escludono dalla classifica l'intero modello coinvolto; una modifica allo snapshot interrompe anche la matrice. Il report mostra stato e dettaglio delle violazioni prima della classifica.

At startup the runner rejects selected instructions, manifests, prompts, fixtures, graders, or manual rubrics that differ from Git, creates one frozen snapshot containing tracked files and the execution policy (excluding ignored caches and outputs), and records input hashes and baseline Git trees. Each task gets an internal Git-ignored `.benchmark-scratch/` directory used by `TMPDIR`, `TMP`, and `TEMP`. The audit follows `cd` and `$PWD` across multiline shell commands: a traversal test that stays inside internal scratch is valid. Shell paths resolved outside the workspace, explicit network attempts, repository/snapshot mutation, or a divergent baseline disqualify the affected model. Snapshot mutation also aborts the remaining matrix. Integrity status and violation details are shown before the leaderboard.

Il comando termina con exit code `1` se almeno una task va in timeout, Pi restituisce un errore o gli eventi JSONL terminano con un errore agente/provider anche quando il processo Pi esce con codice zero; completa comunque il resto della matrice e genera il report. Un punteggio sotto 60 con stato `ok` e integrità valida non cambia l'exit code: è un risultato negativo valido del modello, non un guasto del runner.

The command exits with code `1` when any task times out, Pi fails, or the JSONL event stream ends with an agent/provider error even if the Pi process exits zero; it still completes the remaining matrix and writes the report. A score below 60 with status `ok` and valid integrity does not change the exit code: it is a valid negative model outcome, not a runner failure.

Esamina sempre `grade.json`, `diff.patch` e il workspace dei due o tre modelli migliori. I grader misurano requisiti osservabili, ma non sostituiscono il giudizio su leggibilità, chiarezza delle spiegazioni o buon gusto architetturale.

Always inspect `grade.json`, `diff.patch`, and the final workspace for the top candidates. Automated graders do not replace human judgment about readability, explanations, or architectural taste.

I tempi includono output, eventuale reasoning della coorte attiva, strumenti e test e sono quindi una misura di produttività end-to-end. Confrontali solo sulla stessa macchina, con lo stesso profilo, modalità thinking e carico simile. Preflight e warmup restano fuori dalle metriche task e sono registrati separatamente; `--no-warmup` non disabilita il preflight.

Ogni `result.json` include inoltre metriche POSIX dei processi figli e, sui sistemi Linux che espongono contatori RAPL leggibili, energia host-wide. Campo `available`, provider e scope impediscono di confondere un dato assente o di sistema con il consumo esclusivo del modello.

Each `result.json` also includes POSIX child-process metrics and, on Linux systems exposing readable RAPL counters, host-wide energy. Availability, provider, and scope fields keep missing or system-wide data from being presented as model-exclusive consumption.

## Confronto multi-run / Multi-run comparison

Aggregare run compatibili senza ricopiare manualmente i punteggi:

```bash
python3 benchmark.py compare results/RUN-1 results/RUN-2 results/RUN-3
```

Il comando produce `comparison.json` e `COMPARISON.md` con media, mediana, deviazione standard e intervallo al 95% approssimato, limitato al dominio naturale della metrica. Rifiuta directory duplicate e confronti tra versioni/parametri, profili, input, digest/capability modello, controllo thinking, retry, timeout idle, versioni Pi/Ollama, backend sandbox, piattaforme o hardware differenti; i modelli esclusi dall'integrità non ricevono campioni. I run precedenti alla 0.7.0 restano leggibili ma sono `thinking_control: unverified` e non sono baseline compatibili con i run verificati.

The command writes `comparison.json` and `COMPARISON.md` with mean, median, standard deviation, and an approximate 95% interval bounded to each metric's natural domain. It rejects duplicate directories and runs with different versions/parameters, profiles, inputs, model digests/capabilities, thinking controls, retry policies, idle timeouts, Pi/Ollama versions, sandbox backends, platforms, or recorded hardware. Pre-0.7.0 runs remain readable as `thinking_control: unverified` but are not compatible baselines for verified runs.

## Finalissima dashboard / Dashboard showcase

Dopo i run `smoke`, `standard` e `full`, creare un unico dataset ridotto per i finalisti:

```bash
python3 benchmark.py dashboard-data \
  results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN \
  --output results/finalists-dashboard-data.json
```

`dashboard-data` accetta run/report schema 2, 3 e 4 e produce dashboard schema 3; continua a leggere dataset schema 1/2. Esporta lo stato sintetico del controllo thinking, codici d'esclusione e l'eventuale ID caso, marcando i run legacy come non verificati. Non copia preflight dettagliati né reasoning. Conserva provenienza tramite hash SHA-256 e soltanto i campi necessari a funnel, classifiche e dettaglio task. Non esporta path assoluti, prompt, risposte, comandi, log, evidenze d'integrità o errori liberi. Gli input e l'output devono restare nella root del progetto, le sorgenti non vengono modificate e un output esistente richiede `--force`. Il formato pubblico segue [`schemas/dashboard-data.schema.json`](schemas/dashboard-data.schema.json).

The `dashboard-data` command accepts run/report schemas 2, 3, and 4 and emits dashboard schema 3 while continuing to read schema-1/2 datasets. It exports summarized thinking-control state, exclusion reason codes and optional case IDs, marks legacy runs as unverified, and excludes detailed preflights and reasoning content. It retains SHA-256 provenance and only the fields required for the funnel, leaderboards, and task details; absolute paths, prompts, responses, commands, logs, integrity evidence, and free-form errors are excluded. Inputs and output stay under the project root, sources are never modified, and replacing an output requires `--force`.

Dopo revisione, congelare lo stesso JSON in `cases/results_dashboard/fixture/dashboard-data.json`, validare e committare il caso, quindi eseguire soltanto i finalisti con `--profile showcase`. Il grader automatico usa anche un dataset alternativo nascosto e resta separato dalla rubrica visuale da 20 punti. Il funnel distingue esplicitamente `not_run_in_next` da un fallimento. Procedura completa: [QUICK-START_Showcase.md](QUICK-START_Showcase.md).

After review, freeze the same JSON as `cases/results_dashboard/fixture/dashboard-data.json`, validate and commit the case, then run only the finalists with `--profile showcase`. The automatic grader also uses a hidden alternate dataset and remains separate from the 20-point visual rubric. The funnel explicitly distinguishes `not_run_in_next` from failure. See [QUICK-START_Showcase.md](QUICK-START_Showcase.md).

Il profilo `showcase` resta un test anche quando nessun candidato supera 60/100: timeout, errori o baseline non modificata sono esiti da conservare e revisionare, senza ritoccare dataset o grader. / The `showcase` profile remains a valid test when no candidate exceeds 60/100: timeouts, errors, or an unchanged baseline are outcomes to retain and review without changing the dataset or grader.

## Dashboard ufficiale / Official results dashboard

La dashboard ufficiale è mantenuta dal progetto e non è il risultato della prova `showcase`. Può essere usata in tre modi:

```bash
# risultati locali compatibili scoperti automaticamente in results/
python3 dashboard.py

# una selezione esplicita di run
python3 dashboard.py results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN

# un export già ridotto e revisionato
python3 dashboard.py --dataset results/finalists-dashboard-data.json
```

Il launcher usa soltanto la libreria standard, serve su `127.0.0.1`, sceglie una porta libera per default e apre il browser. Usare `--no-open` per copiare manualmente l'URL, `--port NUMERO` per una porta fissa e `Ctrl+C` per terminare. Se non trova run validi, usa in memoria la fixture dashboard revisionata. Non scrive né modifica i risultati sorgente.

The official dashboard is maintained by the project and is not an output of the `showcase` test. Its standard-library launcher serves only allowlisted assets and an in-memory public dataset on `127.0.0.1`; it never exposes raw result files. Pass explicit run directories, `--dataset` for an existing sanitized export, `--no-open`, or `--port NUMBER` as needed. If no compatible run is found, the reviewed dashboard fixture is served in memory.

Il percorso guidato le passa le directory `smoke`, `standard` e `full` della sessione completata; se il funnel si arresta, **Riapri dashboard** può leggere dal manifesto locale anche uno o due run già disponibili, senza crearne di nuovi. / The guided path passes the completed session's `smoke`, `standard`, and `full` directories; if the funnel stops, **Reopen dashboard** can also reuse one or two available runs from the local manifest without creating new runs.

La sezione **Mappa di efficienza / Efficiency map** visualizza per ogni run e modalità thinking due grafici distinti: qualità rispetto alla durata mediana e qualità rispetto ai token mediani di output. Gli assi orizzontali sono logaritmici e dichiarati; l’area desiderabile è in alto a sinistra. Il grafico usa `quality_score`, non il punteggio complessivo che incorpora già velocità ed efficienza, e non fonde mai coorti incompatibili. I punti e la legenda distinguono completamento pieno, parziale e assenza di task sopra soglia e sono consultabili anche da tastiera.

The **Efficiency map** shows two separate plots for every run and thinking mode: quality against median duration and quality against median output tokens. Horizontal axes are explicitly logarithmic, and the desirable area is toward the upper left. The plot uses `quality_score`, not the overall score that already includes speed and token efficiency, and never merges incompatible cohorts. Points and legends distinguish full, partial, and zero completion and are keyboard-accessible.

Nel selettore **Scegli file / Choose files**, aprire esclusivamente uno o più file `dashboard-data.json` creati con `python3 benchmark.py dashboard-data ...`: non selezionare `run.json`, `report.json`, directory di run o artefatti raw. L'importazione avviene localmente nel browser, non carica file in rete e non li salva nel repository.

In **Choose files**, select only one or more `dashboard-data.json` exports created by `python3 benchmark.py dashboard-data ...`; do not select `run.json`, `report.json`, run directories, or raw artifacts. Import stays inside the browser and does not upload or commit files. Full instructions: [QUICK-START_Dashboard.md](QUICK-START_Dashboard.md).

## Landing page / Project landing page

La landing page pubblica vive sotto [`site/`](site/) ed è pronta per GitHub Pages all'indirizzo `https://gloutchov.github.io/LocalAgentBenchmark/`. Per l'anteprima locale dalla root del repository:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

Aprire `http://127.0.0.1:8000/` e terminare con `Ctrl+C`. La pagina rileva la lingua del browser, usa italiano soltanto per locale italiani e inglese negli altri casi; lingua e tema possono essere scelti manualmente e sono le sole preferenze salvate in `localStorage`. Tutto il sito è statico: HTML, CSS, JavaScript, font di sistema e immagini sono locali, senza CDN, analytics, telemetria, form o richieste runtime remote. I link a repository, release, documentazione e sito personale sono navigazioni esterne esplicite.

The public landing page lives under [`site/`](site/) and is ready for GitHub Pages at `https://gloutchov.github.io/LocalAgentBenchmark/`. Preview it locally with the command above. The page detects browser language, defaults to Italian only for Italian locales and to English otherwise, and persists only explicit language and theme choices. All runtime assets are local and the site has no CDN, analytics, telemetry, forms, or remote runtime requests.

I fotogrammi sotto `site/assets/` sono derivati ottimizzati dei video locali `assets/Dashboard.mov` e `assets/Guided.mov`: i sorgenti restano ignorati da Git, non vengono pubblicati e non vanno modificati. Quando cambiano testi o UI, mantenere sincronizzati i dizionari in `site/js/i18n.js`, aggiornare entrambe le immagini fallback/WebP quando necessario e verificare `site/index.html`, `site/404.html`, il prefisso Pages `/LocalAgentBenchmark/` e i test statici.

The optimized frames in `site/assets/` are derived from the local `assets/Dashboard.mov` and `assets/Guided.mov` sources. The sources remain Git-ignored, are never published, and must not be edited. Keep both dictionaries synchronized and verify the HTML, fallback/WebP images, Pages prefix, and static tests whenever the landing page changes.

## Configurazione / Configuration

[`benchmark.json`](benchmark.json) centralizza URL Ollama, comando Pi, timeout task/preflight, thinking, timeout idle HTTP, retry agente/provider, contesto, token massimi, warmup, sandbox, profili, directory di discovery dei casi e opzioni locali della dashboard. Il default resta `thinking: "off"`, `http_idle_timeout_ms: 0` e zero retry. La sezione `dashboard` mantiene asset e risultati dentro il repository, impone l'host `127.0.0.1` e configura sorgente dati, porta e apertura automatica. La sezione `guided` fissa i profili `smoke`, `standard`, `full`, i limiti di promozione decrescenti `4`, `2` e il file locale delle preferenze GUI; viene validata senza fallback silenziosi e non può includere `results_dashboard`. L'eventuale `dashboard/data/snapshot.js` è un output locale ignorato da Git. Ogni `cases/<id>/case.json`, verificabile contro [`schemas/case.schema.json`](schemas/case.schema.json), contiene ID, titoli bilingui, categoria, peso e path relativi; i manifesti pre-0.4 inline restano leggibili per compatibilità. `"models": "installed"` rileva tutti i modelli da `/api/tags`; una lista esplicita rende il set stabile. `defaults.sandbox` accetta `audit`, `auto` o `required`; il default conservativo e retrocompatibile è `audit`.

La temperatura è zero per ridurre la varianza. Le ripetizioni restano necessarie: tool calling e generazione locale non sono perfettamente deterministici. L'ordine delle task viene randomizzato e registrato; `--seed` permette di riprodurlo. Per un confronto decisionale usare almeno tre ripetizioni e la stessa alimentazione/condizione termica.

## Isolamento e privacy / Isolation and privacy

Il runner crea per ogni task un repository Git nuovo da uno snapshot condiviso, copia al suo interno questo `AGENTS.md`, premette al prompt una policy di confine bilingue e usa una directory Pi separata. La policy vieta rete e path esterni e indica `.benchmark-scratch/` per test e file temporanei. Pi riceve `--offline` e Ollama usa loopback. Le fixture includono i materiali richiesti dal caso e non contengono credenziali reali.

For each task, the runner creates a fresh Git repository from the shared snapshot, copies this `AGENTS.md`, prepends a bilingual boundary policy to the prompt, and uses a separate Pi directory. The policy forbids network and external paths and designates `.benchmark-scratch/` for tests and temporary files. Pi receives `--offline`, and Ollama remains on loopback. Fixtures include the materials required by each case and contain no real credentials.

`--sandbox audit` conserva il comportamento 0.1.x: policy e rilevamento, senza blocco OS. `auto` usa il backend nativo quando supera il probe e altrimenti registra un fallback esplicito; `required` interrompe prima delle task se l'isolamento non è disponibile. Su macOS Seatbelt blocca letture/scritture nelle aree utente esterne e limita la rete alla porta loopback di Ollama, ma `sandbox-exec` è deprecato. Su Linux `unshare` crea un network namespace vuoto e bubblewrap limita filesystem e processi; un broker host raggiungibile solo tramite socket Unix inoltra verso l'unico endpoint Ollama configurato. Su Windows AppContainer viene avviato senza capability di rete, con ACL temporanee sui soli path necessari, Job Object kill-on-close e un named pipe autorizzato per il SID esatto del container verso lo stesso broker a destinazione fissa.

`--sandbox audit` preserves the 0.1.x behavior: policy and detection without OS enforcement. `auto` uses a native backend only after a successful probe and records an explicit fallback otherwise; `required` stops before tasks when enforcement is unavailable. On macOS, Seatbelt blocks external user-file access and restricts networking to Ollama's loopback port, but `sandbox-exec` is deprecated. On Linux, `unshare` creates an empty network namespace and bubblewrap limits filesystems and processes; a host broker reachable only through a Unix socket forwards to the single configured Ollama endpoint. On Windows, AppContainer runs without network capabilities, with temporary ACLs on only the required paths, a kill-on-close Job Object, and a named pipe authorized for the container's exact SID to the same fixed-destination broker.

An enforced backend narrows risk but does not make untrusted real data safe by itself. Required runtime paths remain readable, graders and brokers run as trusted host processes, result artifacts may contain sensitive content, and `audit`/`auto` fallback remain detection rather than containment. Read [SECURITY_MODEL.md](SECURITY_MODEL.md).

Anche il dataset dashboard ridotto resta potenzialmente sensibile: contiene nomi locali dei modelli, titoli dei casi, punteggi, tempi e hash collegabili alle sorgenti conservate. Dashboard candidate e dashboard ufficiale restano offline; il server ufficiale espone su loopback soltanto la whitelist pubblica, ma ogni pubblicazione richiede comunque revisione manuale.

The reduced dashboard dataset also remains potentially sensitive: it includes local model names, case titles, scores, timings, and hashes linkable to retained sources. Candidate and official dashboards stay offline; the official loopback server exposes only allowlisted public data, but publication still requires manual review.

## Sviluppo / Development

```bash
python3 -m compileall -q benchmark.py dashboard.py guided_benchmark.py src cases tests
python3 -m unittest discover -s tests -v
node --test dashboard/tests/dashboard.test.js site/tests/site.test.js
python3 benchmark.py case validate
```

Per una verifica mirata della landing page: `python3 -m unittest tests.test_site tests.test_site_javascript -v`. Prima della pubblicazione controllare anche desktop/mobile, entrambe le lingue, tema automatico/chiaro/scuro, tastiera, focus, overflow, console e richieste di rete tramite browser reale.

For a focused landing-page check, run `python3 -m unittest tests.test_site tests.test_site_javascript -v`. Before publishing, also verify desktop/mobile layouts, both languages, automatic/light/dark themes, keyboard focus, overflow, console output, and network requests in a real browser.

Per rigenerare un report esistente:

```bash
python3 benchmark.py report results/20260825-120000
```

Non modificare gli input durante un run. Per aggiungere un caso usa `case create`, personalizza i file generati e poi esegui `case validate`: il grader deve assegnare esattamente 100 punti e mantenere la fixture iniziale sotto 60. I grader importati sono codice da revisionare prima della validazione perché vengono eseguiti con i permessi dell'utente, fuori dalla sandbox dell'agente.

Do not edit case inputs during a run. Use `case create`, customize the scaffold, and run `case validate`: the grader must allocate exactly 100 points and keep the initial fixture below 60. Review imported graders before validation because they execute with the user's permissions outside the agent sandbox.

## Distribuzione / Distribution

Il progetto viene eseguito direttamente dal checkout. La 0.11.0 aggiunge launcher sorgente sottili per macOS, Windows e Linux e l'entry point installabile `localagent-benchmark-guided`, ma non distribuisce installer, app bundle o binari firmati. I tag sorgente non includono ancora wheel o artifact binari; un'eventuale distribuzione fuori checkout richiederà packaging smoke e checksum SHA-256 secondo [`PLAN.md`](PLAN.md). Il workflow [GitHub Pages](.github/workflows/pages.yml) valida e pubblica soltanto `site/` dopo un push autorizzato su `main` o un avvio manuale.

The project runs directly from its checkout. Version 0.11.0 adds thin macOS, Windows, and Linux source launchers plus the installable `localagent-benchmark-guided` entry point, but no installer, app bundle, signed executable, wheel, or binary artifact. The [GitHub Pages workflow](.github/workflows/pages.yml) validates and publishes only `site/` after an authorized push to `main` or a manual dispatch.

## Documentazione / Documentation

- [Manuale italiano](ISTRUZIONI.md)
- [English manual](INSTRUCTIONS.md)
- [Percorso rapido guidato / Guided quick path](QUICK-START_Guided.md)
- [Avvio rapido Linux / Linux quick start](QUICK-START_Linux.md)
- [Avvio rapido Windows / Windows quick start](QUICK-START_Windows.md)
- [Guida autore casi / Case author quick start](QUICK-START_Case-Author.md)
- [Finalissima dashboard / Dashboard showcase](QUICK-START_Showcase.md)
- [Dashboard ufficiale / Official results dashboard](QUICK-START_Dashboard.md)
- [Landing page locale / Local landing page](site/)
- [Modello di sicurezza bilingue](SECURITY_MODEL.md)
- [Segnalazione vulnerabilità](SECURITY.md)
- [Guida ai contributi](CONTRIBUTING.md)
- [Piano di sviluppo](PLAN.md)
- [Mappa del repository](MAP.md)
- [Regole per agenti e maintainer](AGENTS.md)
