# Mappa repository / Repository Map

```text
.
├── benchmark.py                    # entry point locale senza installazione
├── dashboard.py                    # launcher loopback della dashboard ufficiale
├── guided_benchmark.py             # entry point Tkinter del percorso rapido
├── benchmark.json                  # provider locale, profili, guided e root casi
├── launchers/                      # launcher sorgente sottili, nessun binario incluso
│   ├── LocalAgent-Benchmark.command # doppio clic macOS
│   ├── LocalAgent-Benchmark.cmd    # doppio clic Windows
│   └── LocalAgent-Benchmark.sh     # equivalente Linux dipendente dal file manager
├── dashboard/                      # dashboard ufficiale statica e offline
│   ├── index.html                  # UI servita dal launcher; file:// richiede snapshot locale
│   ├── styles.css                  # temi, responsive, focus e stampa
│   ├── favicon.svg                 # icona funzionale locale
│   ├── data/snapshot.js            # output locale opzionale generato e ignorato da Git
│   ├── js/                         # core dati, i18n, rendering e stato UI modulari
│   └── tests/dashboard.test.js     # trasformazioni, fixture, i18n e vincoli statici
├── site/                           # landing page pubblica statica per GitHub Pages
│   ├── index.html                  # contenuti, percorsi rapido/full immersion, avvio, documentazione, metadata e CSP
│   ├── 404.html                    # fallback bilingue compatibile con /LocalAgentBenchmark/
│   ├── css/styles.css              # griglia, temi, responsive, focus e reduced motion
│   ├── js/                         # bootstrap tema, dizionari, preferenze e interazioni
│   ├── assets/                     # favicon e fotogrammi dashboard/guided revisionati e ottimizzati
│   └── tests/site.test.js          # i18n, preferenze e vincoli statici senza dipendenze
├── schemas/
│   ├── case.schema.json            # schema pubblico dei manifesti case.json
│   └── dashboard-data.schema.json  # dataset ridotto per la finalissima offline
├── src/localagent_bench/
│   ├── cli.py                      # doctor/list/run/report/compare/dashboard-data e comandi case
│   ├── config.py                   # modello e validazione configurazione
│   ├── case_sdk.py                 # discovery, manifesti, validatore e template atomico dei casi
│   ├── integrity.py                # preflight Git, snapshot, SHA-256 e drift repository
│   ├── thinking.py                 # mapping puro e policy thinking Pi/provider
│   ├── ollama.py                   # tags/version, capability, preflight, warmup e unload
│   ├── providers.py                # adapter LM Studio e router llama.cpp, hash GGUF e preflight
│   ├── pi_adapter.py               # config/payload Pi, JSONL, retry, scratch e audit path/rete
│   ├── pi_compatibility.py         # server sintetico loopback e gate contrattuale Pi
│   ├── runner.py                   # ordine seeded, preflight, workspace, controlli e artefatti
│   ├── grading.py                  # esecuzione isolata e timeout dei grader
│   ├── sandbox.py                  # selezione, probe e launch Seatbelt/bubblewrap/AppContainer/audit
│   ├── sandbox_transport.py        # broker provider Unix e shim Node a destinazione fissa
│   ├── windows_appcontainer.py     # profilo, ACL/DACL, named pipe e Job Object Windows
│   ├── system_metrics.py           # hardware, rusage POSIX e RAPL opzionale
│   ├── comparison.py               # compatibilità e statistiche tra più run
│   ├── guided.py                   # stato funnel, validazione, manifesto e promozioni
│   ├── guided_process.py           # processi senza shell, cancellazione e dashboard child
│   ├── guided_ui.py                # GUI bilingue, toggle thinking/sandbox e riapertura dashboard
│   ├── dashboard_data.py           # whitelist, esclusioni sintetiche, coorti e funnel smoke/standard/full
│   ├── dashboard_app.py            # discovery run, snapshot e server statico loopback in memoria
│   └── report.py                   # aggregazione, metriche, disqualifiche e Markdown
├── cases/
│   ├── targeted_patch/             # manifesto, bugfix, regressioni, scope e README
│   ├── secure_workspace/           # manifesto, path, symlink, atomicità e redazione
│   ├── config_i18n/                # manifesto, validazione, persistenza, lingua e tema
│   ├── thinking_challenge/         # pianificazione esatta, scenari nascosti e calibrazione anti-hardcoding
│   │   ├── case.json               # titolo bilingue, categoria reasoning, peso e path confinati
│   │   ├── prompt.md               # budget, rischio, capacità, dipendenze, conflitti e tie-break
│   │   ├── fixture/                # package Python e test iniziali intenzionalmente incompleti
│   │   └── grader.py               # 100 punti, scenari alternativi e nessuna traccia reasoning
│   ├── milestone_closure/          # branch, versioning, docs e stop pre-merge
│   │   ├── case.json               # titoli bilingui, categoria, peso e path confinati
│   │   ├── prompt.md               # richiesta consegnata al modello
│   │   ├── fixture/                # repository iniziale, inclusa LICENSE richiesta
│   │   ├── grader.py               # controlli esterni al prompt
│   │   └── manual-rubric.md        # valutazione umana opzionale, fuori score automatico
│   └── results_dashboard/          # finalissima HTML/CSS/JS, dataset sintetico e dataset hidden
│       ├── case.json               # manifesto del profilo showcase
│       ├── prompt.md               # UX, API JS, i18n, tema, offline e accessibilità
│       ├── fixture/                # baseline incompleta, dataset schema 1 e test Node
│       ├── grader.py               # 100 punti tecnici e dataset alternativo non hardcoded
│       └── manual-rubric.md        # 20 punti visuali separati dalla classifica
├── tests/
│   ├── test_case_sdk.py            # schema, path corrotti, template, CLI e calibrazione
│   ├── test_dashboard_data.py      # whitelist, privacy, funnel, path, atomicità e CLI
│   ├── test_dashboard_app.py       # discovery, snapshot, confinement, server e header sicurezza
│   ├── test_dashboard_javascript.py # esecuzione della suite Node dalla suite unittest
│   ├── test_guided.py              # selezione, errori, cancellazione e integrazione funnel
│   ├── test_guided_ui.py           # i18n/preferenze GUI e launcher multipiattaforma
│   ├── test_site.py                # asset, link, anchor, metadata, CSP e prefisso Pages
│   ├── test_site_javascript.py     # esecuzione della suite Node della landing page
│   ├── test_ollama.py              # capability, mapping, preflight e warmup thinking
│   ├── test_providers.py           # discovery, hash GGUF, preflight e gestione modelli alternativi
│   ├── test_pi_thinking_contract.py # Pi reale contro server OpenAI-compatible fittizio
│   ├── test_pi_compatibility.py    # regressioni del gate Pi con payload/errori simulati
│   └── ...                         # runner, parser/status provider, sandbox, metriche, confronti e grader
├── results/                        # output, snapshot input, hash e workspace; ignorato da Git
├── .localagent-benchmark/          # preferenze GUI locali validate; generata e ignorata
├── assets/                         # sorgenti video locali ignorate; mai pubblicate o modificate
│   ├── Dashboard.mov               # sorgente dei fotogrammi della dashboard
│   └── Guided.mov                  # sorgente del fotogramma del percorso guidato
├── .github/workflows/ci.yml        # Pi, Node 24, compile, test e documenti su tre OS
├── .github/workflows/pages.yml     # valida e pubblica soltanto site/ su GitHub Pages
├── .github/dependabot.yml          # aggiornamenti settimanali delle GitHub Actions
├── AGENTS.md                       # modus operandi copiato in ogni fixture
├── README.md                       # overview bilingue e quick start
├── ISTRUZIONI.md                   # manuale italiano
├── INSTRUCTIONS.md                 # manuale inglese
├── QUICK-START_Linux.md            # prerequisiti, smoke e diagnosi Linux
├── QUICK-START_Windows.md          # prerequisiti, smoke e diagnosi Windows
├── QUICK-START_Case-Author.md       # creazione, schema, grader, validazione e sicurezza
├── QUICK-START_Showcase.md          # export, freeze, run finalisti e verifica browser
├── QUICK-START_Dashboard.md         # launcher, import, snapshot locale e troubleshooting
├── QUICK-START_Guided.md            # funnel senza terminale, piattaforme, privacy e limiti
├── QUICK-START_LocalProviders.md    # installazione Pi/provider, router GGUF e provenienza
├── SECURITY_MODEL.md               # controlli, rischi e limiti bilingui
├── SECURITY.md                     # canale privato e ambito delle segnalazioni
├── CONTRIBUTING.md                 # regole e verifiche per contribuire
├── PLAN.md                         # milestone, criteri e checklist
├── VERSION                         # versione canonica
├── pyproject.toml                  # metadata Python, senza dipendenze runtime
└── LICENSE                         # Apache License 2.0
```

`results/` nasce al primo run. Il percorso rapido crea `results/guided-<timestamp>-<suffix>/guided-run.json` più tre sottodirectory distinte `smoke/`, `standard/`, `full/`; il manifesto atomico conserva impostazioni, seed, classifiche, esclusioni e passaggi, mentre ogni sottodirectory mantiene i normali artefatti raw. `benchmark-context/` contiene la fotografia condivisa e verificata di manifesti, prompt, fixture, grader, rubriche e `EXECUTION_POLICY.snapshot.md`; `run.json` schema 4 registra commit/stato Git, seed, ordine task, SHA-256, versione audit, sandbox, hardware, versioni Pi/Ollama, digest/capability modello, policy/preflight thinking, retry, timeout idle, warmup e violazioni. Ogni tentativo contiene una `workspace/` deliberatamente modificabile dal modello, una `.benchmark-scratch/` interna ignorata da Git (profilo Seatbelt o socket del broker Linux quando applicabili), una `.pi-agent/` per-task e artefatti fratelli (`result.json`, `grade.json`, `pi-events.jsonl`, `diff.patch` e l'eventuale `manual-rubric.md`), inclusi tree baseline, audit, stato thinking osservabile, backend e metriche di sistema. Gli eventi raw possono contenere reasoning; preflight, report ed export ne conservano soltanto conteggi/stato. Su Windows, metadata di cleanup e sole fasi/conteggi byte del broker vengono registrati negli artefatti runtime; il named pipe vive nel namespace AppContainer della sessione. `comparison-*` contiene `comparison.json` e `COMPARISON.md` per run compatibili anche rispetto al controllo thinking. `dashboard-data-*.json` schema 3 contiene soltanto i campi in whitelist, inclusi codici sintetici d'esclusione; gli schemi 1/2 restano leggibili e i run legacy sono marcati non verificati. La dashboard presenta classifiche, fattori e mappe qualità/tempo e qualità/token separate per run/modalità, con assi orizzontali logaritmici, e limita il funnel alla progressione `smoke` → `standard` → `full`; i profili `thinking` e `showcase` restano coorti indipendenti. Il dataset definitivo va congelato nella fixture `results_dashboard` e committato prima del profilo `showcase`. La dashboard ufficiale usa quella fixture come fallback in memoria e, tramite `dashboard.py`, aggrega i run locali senza esporre i file raw. `dashboard/data/snapshot.js` viene creato soltanto su richiesta per l'apertura `file://` ed è ignorato da Git. La landing sotto `site/` è una superficie pubblica distinta: usa soltanto asset locali, distingue percorso rapido, full immersion da terminale e requisiti iniziali, filtra il manuale per lingua e mostra soltanto istruzioni e quick start nella sezione documentale; salva lingua/tema e il workflow Pages carica esclusivamente quella directory. I fotogrammi pubblicabili derivano da `assets/Dashboard.mov` e `assets/Guided.mov`, ma i video sorgente restano ignorati e fuori dall'artefatto Pages. `output/playwright/` e `.playwright-cli/` sono output locali ignorati. I file sorgente sotto `cases/` non devono essere modificati durante un'esecuzione; il preflight Git li richiede puliti e il confronto post-task rileva cambiamenti successivi.
