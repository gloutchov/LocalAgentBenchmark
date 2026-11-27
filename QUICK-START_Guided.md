# Percorso rapido guidato / Guided quick path

Questa procedura confronta i modelli di un provider locale scelto tra quelli configurati in `benchmark.json` senza richiedere di comporre comandi. Sono supportati Ollama, LM Studio, il router llama.cpp e Unsloth; vedere [QUICK-START_LocalProviders.md](QUICK-START_LocalProviders.md). Dopo una conferma esplicita propone Preliminary opzionale, poi esegue `smoke` su tutti i modelli selezionati, promuove al massimo i primi quattro classificabili a `standard`, promuove al massimo i primi due a `full` e apre la dashboard ufficiale sui tre run del funnel e sull'eventuale Preliminary.

This workflow compares models from one of the local providers configured in `benchmark.json`: Ollama, LM Studio, the llama.cpp router, or Unsloth. See [QUICK-START_LocalProviders.md](QUICK-START_LocalProviders.md). After explicit confirmation it optionally runs Preliminary, then runs `smoke` on every selected model, promotes up to four rankable models to `standard`, up to two to `full`, and opens the official dashboard on the three funnel runs plus optional Preliminary.

## Requisiti / Requirements

- checkout sorgente completo di LocalAgent Benchmark 0.16.0;
- Python 3.10 o successivo con Tkinter;
- Git;
- provider locale configurato su loopback con almeno un modello tool-capable;
- Pi disponibile come `pi`; compatibilità verificata durante il rilevamento e prima di ogni fase;
- `AGENTS.md`, `.gitignore`, manifesti, prompt, fixture, grader e rubriche selezionati puliti rispetto a Git.

The source checkout, Python 3.10+ with Tkinter, Git, a configured loopback model server, Pi passing the startup compatibility check, and clean protected benchmark inputs are required. No third-party Python package is added.

## Elenco dei provider / Provider list

La colonna **Provider** indica l'origine di ogni modello. La GUI rileva `provider` e le voci opzionali di `additional_providers` in `benchmark.json`. Un server spento compare tra i provider non disponibili, mentre gli altri restano utilizzabili. Selezionare i modelli di un solo provider per volta. **Tutti del provider** seleziona i modelli del provider della prima riga selezionata, oppure del primo provider disponibile se la selezione è vuota. La finestra di conferma indica quale provider useranno tutte le fasi.

The **Provider** column identifies each model's source. The GUI discovers `provider` and the optional entries in `additional_providers` in `benchmark.json`. A stopped server appears under unavailable providers while the others remain usable. Select models from one provider per run. **All from provider** selects the provider of the first selected row, or the first available provider when the selection is empty. The confirmation dialog identifies the provider used in all stages.

## Unsloth nel percorso guidato / Unsloth in guided mode

Configurare una voce con `kind: "unsloth"`, un URL HTTP loopback e `credential_ref` come descritto nella [guida provider](QUICK-START_LocalProviders.md#unsloth). Prima del rilevamento caricare manualmente un GGUF locale e predisporre nel portachiavi una chiave Unsloth con accesso `inference`. La GUI legge soltanto la credenziale esistente: non chiede la chiave in una finestra, non eredita `--credential-prompt` e non salva segreti nelle preferenze. Se il portachiavi manca o l'accesso è negato, correggere la configurazione prima di riprovare oppure usare la CLI con prompt esplicito. I modelli devono rimanere caricati durante le fasi; caricamento/scaricamento e reset della cache sono manuali. Nessun warmup viene descritto come avvio a freddo.

Configure an entry with `kind: "unsloth"`, an HTTP loopback URL and `credential_ref` as described in the [provider guide](QUICK-START_LocalProviders.md#unsloth). Before discovery, manually load a local GGUF and place an Unsloth key with `inference` access in the OS credential store. The GUI only reads an existing credential: it has no key-entry dialog, does not inherit `--credential-prompt`, and never stores secrets in preferences. Resolve missing/denied credential-store access before retrying, or use the explicit CLI prompt. Keep models loaded throughout the phases; loading, unloading and cache reset are manual. Warmup does not certify a cold start.

Nel catalogo Colibrì usa il server `coli serve` con un solo modello chat residente. Imposta la finestra dichiarata, seleziona **Thinking off** e **Sandbox required** e verifica il modello con la [guida Colibrì](QUICK-START_LocalProviders.md#colibrì).

For Colibrì discovery, use `coli serve` with one resident chat model. Use the advertised context window, select **Thinking off** and **Sandbox required**, and follow the [Colibrì guide](QUICK-START_LocalProviders.md#colibrì).

## Avvio con doppio clic / Double-click launch

- **macOS:** aprire `launchers/LocalAgent-Benchmark.command`. Se Finder mostra un avviso per uno script sorgente non firmato, usare il menu contestuale **Apri** dopo aver verificato il checkout.
- **Windows 10/11:** aprire `launchers\LocalAgent-Benchmark.cmd`. Il launcher prova prima `py -3`, poi `python`; una finestra console può restare dietro alla GUI e mostrare soltanto eventuali errori di avvio.
- **Linux:** aprire `launchers/LocalAgent-Benchmark.sh`. Il comportamento del doppio clic dipende dal file manager; scegliere **Esegui** quando viene chiesto. Non viene distribuito un pacchetto desktop nativo.

On macOS open `launchers/LocalAgent-Benchmark.command`; on Windows open `launchers\LocalAgent-Benchmark.cmd`; on Linux open `launchers/LocalAgent-Benchmark.sh` and choose **Run** if the file manager asks. These are thin source launchers, not signed binaries or installers.

Chi preferisce un launcher già installato dal pacchetto Python può avviare `localagent-benchmark-guided`; non è necessario per il normale checkout sorgente.

An installed source package also exposes `localagent-benchmark-guided`; it is not required for a normal source checkout.

## Prima della conferma / Before confirmation

La finestra esegue i controlli equivalenti a `doctor`, rileva i modelli dal provider configurato e mostra:

- nome, dimensione e capability thinking nota dei modelli locali;
- modelli selezionati, inizialmente tutti;
- profili `smoke` → `standard` → `full` e limiti `4` → `2`;
- due toggle per scegliere thinking `off`/`medium` e sandbox `audit`/`required`, più timeout e warmup da `benchmark.json`;
- un avviso che la durata dipende da modelli, hardware e casi e non è garantita.

Fare clic sull'intestazione modello, dimensione o thinking per ordinare la tabella; un secondo clic inverte l'ordine e la freccia mostra la direzione attiva. La selezione resta invariata durante il riordino.

Il toggle **Thinking** spento richiede `off`, acceso richiede `medium`; non c'è fallback automatico. Il toggle **Sandbox** spento usa solo l'audit senza isolamento OS; acceso richiede un backend OS applicabile e interrompe l'avvio se manca. Le scelte sono mostrate prima della conferma, valgono per tutte e tre le fasi e vengono registrate nel manifesto. Nella dashboard, **Dettaglio task** elenca separatamente i modelli esclusi prima delle task per thinking osservato con `off` e quelli esclusi dopo tentativi fuori workspace/rete o altre violazioni; la riga indica se la sandbox OS era applicata. Un'esclusione non dimostra da sola che il sistema operativo abbia bloccato l'azione.

The window performs the equivalent of `doctor`, detects models from the configured provider, and displays the selected models, funnel, promotion limits, thinking mode, sandbox, timeout, warmup, and an explicit duration warning. Click the model, size, or thinking column heading to sort it; a second click reverses the order and the arrow shows the active direction. Selection is preserved while sorting. The benchmark starts only after confirmation.

Il timeout mostrato è per **singola task** (`defaults.timeout_seconds`, default 1.200 secondi), non per l'intera sessione; controllo Pi, preflight e warmup hanno limiti propri. Per limitare un primo test, selezionare un modello e ridurre il valore in `benchmark.json` prima di aprire la GUI. Su Windows, alla scadenza vengono terminati anche i processi Pi/Node figli e l'attesa dell'output è limitata; AppContainer `required` concede al watchdog esterno fino a 300 secondi aggiuntivi.

The displayed timeout is **per task** (`defaults.timeout_seconds`, 1,200 seconds by default), not for the whole session; the Pi contract, preflight, and warmup have their own limits. For a shorter first test, select one model and lower this setting in `benchmark.json` before starting the GUI. On Windows, expiry also terminates Pi/Node child processes and bounds output collection; `required` AppContainer allows the outer watchdog up to 300 additional seconds.

The **Thinking** toggle selects `off` or `medium` without automatic fallback. The **Sandbox** toggle selects audit only, without OS isolation, or `required`, which stops before a run if no applicable OS backend is available. Both choices apply to all three stages and are recorded in the session manifest. In the dashboard, **Task details** lists preflight thinking exclusions and workspace/network integrity exclusions separately from executed tasks, with the effective sandbox status. An exclusion alone does not prove that the OS blocked the action.

Lingua e tema seguono il sistema per default. Gli override vengono salvati soltanto in `.localagent-benchmark/guided-preferences.json`, dentro la root e ignorato da Git.

Language and theme follow the operating system by default. Overrides are stored only in `.localagent-benchmark/guided-preferences.json` inside the project root and ignored by Git.

Nel tema scuro, i selettori di lingua e tema, i modelli selezionati, i pulsanti disabilitati e la barra di avanzamento usano colori coordinati con contrasto leggibile. La barra avanza per le task completate all'interno di ogni fase e arriva al termine della fase dopo la verifica degli artefatti.

In dark mode, the language and theme selectors, selected models, disabled buttons, and progress bar use readable contrasting colors. The bar advances for completed tasks within each stage and reaches the stage boundary after its artifacts are validated.

## Selezione e risultati / Selection and results

Il flusso non ricalcola la classifica: usa nell'ordine la `leaderboard` già prodotta dal report ufficiale. Modelli esclusi per integrità, controllo thinking non verificato, incompletezza o task fallita non vengono promossi. Una task fallita esclude il solo modello interessato quando il report della fase è completo e compatibile; gli altri continuano. Se i classificabili sono meno di quattro o due, proseguono tutti quelli disponibili; se non ne resta nessuno, il percorso si ferma senza trasformare un fallimento in successo.

The flow does not reimplement ranking: it consumes the official report `leaderboard` in its existing order. Integrity exclusions, unverified thinking controls, incomplete models, and failed tasks never become successful promotions. A failed task excludes only its model when the stage report is complete and compatible, allowing other valid models to continue. Fewer candidates simply means a smaller next stage.

Ogni sessione crea una directory simile a:

```text
results/guided-YYYYMMDD-HHMMSS-XXXXXX/
├── guided-run.json
├── smoke/
├── standard/
└── full/
```

`guided-run.json` registra modelli scoperti e selezionati, impostazioni effettive, seed base e di fase, directory, graduatorie, esclusioni e transizioni. I tre run conservano i normali `run.json`, `report.json`, `REPORT.md` e artefatti per task. Tutto può contenere nomi modello, path, output e altri dati locali sensibili: non condividere `results/` senza revisione.

The session manifest records discovery, selection, effective settings, seeds, directories, leaderboards, exclusions, and transitions. Normal raw run artifacts remain local and potentially sensitive.

## Annullamento, ripresa e dashboard / Cancellation, recovery, and dashboard

Il pulsante **Annulla / Cancel** chiede conferma, termina il runner e i suoi processi figli e conserva gli artefatti completati o diagnosticabili. Una sessione interrotta non viene ripresa né promossa parzialmente: correggere il problema e avviare una nuova sessione.

**Cancel** asks for confirmation, stops the runner process tree, and preserves completed or diagnostic artifacts. Interrupted sessions are not resumed or partially promoted; fix the issue and start a new session.

Al completamento viene validato in memoria il dataset ridotto dei tre run e viene avviata la dashboard ufficiale su `127.0.0.1`. Se il funnel si ferma, **Riapri dashboard / Reopen dashboard** può usare da uno a quattro run già disponibili e mostrare i risultati parziali senza reinterpretarli come completamento. Funziona anche dopo aver riaperto la GUI e non riesegue il benchmark. La dashboard non è la dashboard candidata del profilo `showcase`.

After completion the reduced three-run dataset is validated in memory and the official loopback dashboard is launched. If the funnel stops, **Reopen dashboard** can reuse one to four available runs and show partial results without presenting them as a completed funnel. It also works after restarting the GUI and never reruns models.

## Configurazione / Configuration

Il percorso usa `benchmark.json` come fonte unica. La sezione dedicata è:

```json
"guided": {
  "profiles": ["smoke", "standard", "full"],
  "promotion_limits": [4, 2],
  "preferences_file": ".localagent-benchmark/guided-preferences.json"
}
```

I profili devono restare esattamente nell'ordine indicato, i limiti devono essere interi positivi decrescenti e nessun profilo guidato può includere `results_dashboard`. Provider/endpoint, Pi, thinking, retry, timeout, warmup, sandbox e directory risultati continuano a provenire dalle rispettive sezioni centrali. Il percorso guidato rifiuta endpoint non locali e non applica fallback silenziosi.

Profiles must remain in the listed order, promotion limits must be descending positive integers, and guided profiles cannot include `results_dashboard`. All other effective settings come from the central configuration. Non-local provider endpoints and silent fallback are rejected.

## Cosa non esegue / What it does not run

Il percorso rapido non esegue mai `showcase`, non apre il caso `results_dashboard`, non chiede ai modelli di creare una dashboard e non modifica la fixture congelata della finalissima. Riduce il lavoro sui modelli meno promettenti, ma non cambia formula, tie-break, preflight, snapshot, sandbox, audit, warmup o scoring.

The quick path never runs `showcase`, never selects `results_dashboard`, never asks models to build a dashboard, and never changes the frozen showcase fixture. It saves work on less promising models without changing scoring or controls.

## Risoluzione problemi / Troubleshooting

- **Tkinter non disponibile / Tkinter unavailable:** installare una distribuzione Python che includa Tk; i launcher sorgente non scaricano componenti.
- **Provider non raggiungibile / Provider unavailable:** avviare il server selezionato e usare un endpoint loopback in `benchmark.json`.
- **Nessun modello / No models:** rendere disponibile almeno un modello tool-capable nel provider, poi scegliere **Rileva di nuovo / Detect again**.
- **Pi non disponibile o versione errata / Pi missing or wrong version:** verificare che `pi` sia nel `PATH` del launcher grafico e leggere il controllo fallito; Pi 0.85.1 è la versione di riferimento verificata.
- **Input protetti sporchi / Dirty protected inputs:** revisionare e committare legittimamente le modifiche prima del benchmark; non aggirare il preflight.
- **Sandbox required non disponibile / required sandbox unavailable:** installare/configurare il backend previsto oppure cambiare consapevolmente `benchmark.json`; non avviene alcun downgrade automatico.
- **Task fallita o fase incompleta / Failed task or incomplete stage:** consultare la directory mostrata e i report; il funnel non prosegue.
- **Dashboard non avviabile / Dashboard cannot start:** chiudere eventuali processi locali in conflitto e usare **Riapri dashboard**; i run non vengono ricreati.
- **Durata elevata / Long duration:** è normale con molti modelli. Il funnel limita le fasi più costose, ma non garantisce un tempo massimo complessivo.

## Privacy e distribuzione / Privacy and distribution

La GUI non introduce telemetria, CDN o chiamate Internet. Gli endpoint applicativi sono i provider configurati e la dashboard su loopback. I processi ricevono argomenti strutturati, non comandi shell interpolati. Non vengono cancellati automaticamente run precedenti.

The GUI adds no telemetry, CDN, or Internet call. Its application endpoints are the local model provider and the loopback dashboard. Child processes receive structured arguments rather than interpolated shell commands, and prior runs are never deleted automatically.

La release 0.11.0 distribuisce questi launcher come file sorgente nel repository e negli archivi sorgente generati da GitHub. Non promette installer, app bundle, eseguibili firmati o artifact binari multipiattaforma.

Release 0.11.0 distributes these launchers as source files in the repository and GitHub-generated source archives. It does not claim to provide installers, signed app bundles, executables, or cross-platform binary artifacts.

## Preliminary opzionale / Optional Preliminary

Prima di smoke, il toggle Preliminary esegue sui modelli selezionati misure descrittive di reattività e affidabilità su fonti sintetiche. È attivo nella nuova configurazione e può essere disattivato prima di avviare. Le promozioni restano soltanto smoke → standard → full; la dashboard può ricevere quattro directory distinte, con Preliminary fuori dal funnel e dalle classifiche. Errori descrittivi non escludono modelli, i controlli obbligatori sì.

Before smoke, optionally run descriptive responsiveness and synthetic-source grounding probes on all selected models. The new configuration enables this toggle; disable it before starting to skip it. Promotions remain smoke → standard → full. The dashboard may receive four distinct directories; Preliminary stays outside rankings and funnel. Descriptive errors do not exclude models; mandatory control failures do. See [Preliminary](QUICK-START_Preliminary.md).

Le dimensioni GUI sono centralizzate in `guided.window_size` (900×720) e `guided.minimum_size` (760×720). La tabella scorrevole si adatta all’altezza disponibile e lascia spazio ai pulsanti in fondo. I file legacy senza queste opzioni usano gli stessi valori. / GUI dimensions are configured by `guided.window_size` (900×720) and `guided.minimum_size` (760×720). The scrollable table adapts to the available height and leaves room for the action buttons. Legacy configurations use the same defaults.
