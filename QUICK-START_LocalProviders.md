# Provider locali / Local model providers

## Italiano

Il benchmark usa Pi come agente e può collegarlo a **Ollama** (default), **LM Studio 0.4 o successivo**, al **router `llama-server` di llama.cpp** oppure a **Unsloth** con un GGUF locale già caricato e una chiave di sola inferenza. Ogni run usa un solo provider per tutte le fasi. La GUI può rilevare i modelli di più provider configurati in `benchmark.json`. Il server deve restare su loopback HTTP (`127.0.0.1`, `localhost` o `::1`). Non servono pacchetti Python aggiuntivi o download automatici; Unsloth richiede una chiave locale protetta, mentre gli altri tre adapter mantengono la modalità senza autenticazione.

I quattro provider sono gestiti da adattatori interni separati. La selezione resta `provider.kind` in `benchmark.json`: non servono file ricetta aggiuntivi e il formato dei run non cambia.

### Selezionare più provider locali

`provider` resta il default. Aggiungere in `additional_providers` gli altri provider da rilevare. Per esempio, con Ollama come default:

```json
"additional_providers": [
  {"kind": "lmstudio", "url": "http://127.0.0.1:1234"},
  {"kind": "unsloth", "url": "http://127.0.0.1:8888", "credential_ref": "unsloth-local"}
]
```

Usare le porte mostrate dai server locali. Ogni `kind` compare una volta. Da CLI, anteporre `--provider` al sottocomando per selezionare un provider configurato, per esempio `python3 benchmark.py --provider lmstudio list` o `python3 benchmark.py --provider unsloth doctor`. `--config` continua a consentire la scelta di un altro file di configurazione nella root del progetto.

### Colibrì

Predisponi manualmente [Colibrì](https://github.com/JustVugg/colibri/blob/main/docs/api.md) e avvia `coli serve` su loopback con un modello chat caricato, tool calling funzionante, contesto sufficiente e riparazione automatica delle chiamate disabilitata. Usa in `benchmark.json`:

```json
"provider": {
  "kind": "colibri",
  "url": "http://127.0.0.1:8000"
}
```

Usa la porta effettiva del server e configura `defaults.context_window` entro la finestra dichiarata da `/v1/models`. Se il server richiede una chiave, aggiungi `credential_ref` con il riferimento all'archivio protetto oppure usa `--credential-prompt` da CLI prima del sottocomando. Il percorso guidato usa il portachiavi. La chiave resta nel gateway host.

Esegui `python3 benchmark.py --provider colibri doctor`, poi uno smoke mirato e Preliminary con `--thinking off --sandbox required`. La sonda verifica che la modalità `none` non produca reasoning e che un tool sintetico restituisca argomenti JSON validi. Per questa integrazione le modalità thinking attive sono escluse finché il livello effettivo non è verificabile. Pi mantiene la propria configurazione thinking anche quando gli esempi upstream la omettono.

Colibrì mantiene il modello residente. Il benchmark registra il lifecycle manuale e imposta `context_compaction: "off"`. La cache KV può essere riutilizzata o persistita dal runtime. I risultati non attestano un avvio a freddo o un reset della cache.

Per `compare` registra `provider.runtime_version`, `provider.backend_version` e, in `provider.colibri`, `revision` (hash Git completo), `engine`, `quantization`, `kv_slots` e `kv_persistence` (`enabled` o `disabled`). In `provider.colibri.model_bundles` associa l'ID del modello a un oggetto `{"root": "/percorso/assoluto", "files": ["config.json", "tokenizer.json", "weights-01.safetensors"]}`. Elenca tutti i file necessari, inclusi shard e template. Sono letti solo file regolari senza symlink, hashati senza copiarli. L'associazione bundle/ID è dichiarata. Versione, backend, impostazioni e manifesti completi sono necessari al confronto statistico.

### Installazione e verifica su Windows

1. Installare Python 3.10+ e [Git for Windows](https://git-scm.com/download/win). Pi nativo usa Git Bash per i comandi shell; verificare `py -3 --version` e `git --version` in PowerShell.
2. Per installare Pi, installare [Node.js con npm](https://nodejs.org/en/download), poi seguire il [pacchetto ufficiale corrente](https://github.com/earendil-works/pi/tree/main/packages/coding-agent): `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`. Verificare `pi --version` e `py -3 benchmark.py doctor`. Se Pi è già installato e supera `doctor`, non occorre aggiornarlo: ogni versione deve superare il controllo contrattuale del benchmark.
3. Per Ollama, usare l'[installer Windows ufficiale](https://ollama.com/download/windows), avviare l'app e verificare `ollama --version`. Scaricare un modello locale adatto al tool calling con `ollama pull NOME_MODELLO`, poi controllare `ollama list`. Il provider predefinito del benchmark usa `http://127.0.0.1:11434`.
4. Per LM Studio, usare l'[installer ufficiale](https://lmstudio.ai/download), aprire l'app almeno una volta e scaricare o importare un modello adatto al tool calling. Se la scheda **Developer** non è visibile, aprire **Settings → Developer** e attivare [**Developer Mode**](https://lmstudio.ai/docs/app/user-interface/modes); nelle versioni con il vecchio selettore delle modalità scegliere **Developer** in basso nella finestra. Aprire quindi la scheda **Developer** nella barra laterale e [attivare il server](https://lmstudio.ai/docs/developer/rest/quickstart) con l'interruttore in alto a sinistra. In alternativa, se il comando `lms` è disponibile, usare `lms server start --port 1234`.
5. Per llama.cpp, seguire le [istruzioni ufficiali](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md): `winget install llama.cpp`, oppure estrarre un pacchetto Windows dalle [release ufficiali](https://github.com/ggml-org/llama.cpp/releases). Verificare che `llama-server --version` funzioni, usando il path completo a `llama-server.exe` se il binario non è nel `PATH`. Preparare una directory con GGUF locali; serve una versione con modalità router e `/models/load`.

Selezionare **un solo provider per run** in `benchmark.json`. Attendere la fine di un run prima di modificare la configurazione o i file del repository: il runner controlla gli hash delle sorgenti tra le task. Gli altri server possono restare avviati, ma non vengono usati dal run. Per macOS e Linux usare le pagine ufficiali collegate sopra e i requisiti sandbox descritti nei quick start di piattaforma.

### Ollama

Con l'app in esecuzione e almeno un modello già scaricato, lasciare `"provider": {"kind": "ollama", "url": "http://127.0.0.1:11434"}` in `benchmark.json`. Da PowerShell eseguire `py -3 benchmark.py doctor`, `py -3 benchmark.py list`, poi `py -3 benchmark.py run --profile smoke --models NOME_ESATTO --thinking off --sandbox required --timeout 300`. Il nome esatto è quello mostrato da `list`.

### LM Studio

1. Installare LM Studio e scegliere un modello capace di tool calling. Se manca la scheda **Developer**, attivare **Developer Mode** da **Settings → Developer**; nel vecchio layout scegliere la modalità **Developer** dal selettore in basso. Aprire **Developer** nella barra laterale e accendere il server con l'interruttore in alto a sinistra, oppure usare `lms server start --port 1234` se la CLI è disponibile. Un GGUF già scaricato può essere importato con `lms import <percorso-al-modello.gguf> --copy`; senza `--copy`, LM Studio sposta il file originale.
2. Impostare in `benchmark.json`:

   ```json
   "provider": {"kind": "lmstudio", "url": "http://127.0.0.1:1234"}
   ```

3. Eseguire `py -3 benchmark.py doctor`, poi `py -3 benchmark.py list` e `py -3 benchmark.py run --profile smoke --models NOME_ESATTO --thinking off --sandbox required --timeout 300`. Selezionare un solo modello per il primo smoke; il percorso guidato usa la stessa configurazione.

### GGUF con llama.cpp

Avviare una build recente di `llama-server` **in modalità router**, senza `--model`, con file GGUF locali:

```bash
llama-server --models-dir <directory-gguf> --no-models-autoload --jinja --host 127.0.0.1 --port 8080 -c 32768
```

Su Windows sostituire `<directory-gguf>` con il path reale fra virgolette; se necessario usare il path completo a `llama-server.exe`. Il valore `-c 32768` deve concordare con `defaults.context_window` in `benchmark.json` e richiede memoria sufficiente.

`--jinja` abilita i template per il tool calling. Il benchmark carica e scarica i modelli selezionati tramite `/models/load` e `/models/unload`, quindi funziona anche con `--no-models-autoload`. Impostare:

```json
"provider": {"kind": "llama_cpp", "url": "http://127.0.0.1:8080"}
```

Poi eseguire `doctor`, `list` e uno smoke su un solo modello come sopra. L'integrazione usa il server ufficiale llama.cpp. `node-llama-cpp` è una libreria: per usarla con questo benchmark occorrerebbe un bridge HTTP che implementi l'API e i controlli del provider; non è un adapter incluso.

`/models/load` e `/models/unload` possono confermare le richieste prima che l'istanza del modello abbia concluso il cambio di stato. Il benchmark attende `loaded` da `/models` prima dell'inferenza e `unloaded` prima di un nuovo caricamento. Un processo fallito o un timeout di caricamento escludono il modello prima dell'inferenza. Caricamento e scaricamento non contribuiscono ai tempi della task.

### Unsloth

1. Installare manualmente una versione di [Unsloth con API locale](https://unsloth.ai/docs/basics/api). Caricare nell'app un **GGUF locale** compatibile con tool calling e mantenere attivo il server su HTTP loopback. Modelli remoti, MLX e modelli non ancora caricati non appartengono al percorso Unsloth di questa versione del benchmark.
2. In **Impostazioni → API**, inserire un nome e premere **Crea token**. Nel riquadro della nuova chiave scegliere **Inferenza**, quindi copiarne il valore completo con il pulsante di copia prima di premere **Fatto**. La chiave deve avere accesso **`inference`**, senza privilegi completi. Il benchmark ne verifica la restrizione prima dell'inferenza; una chiave completa, una versione senza la policy richiesta o un controllo non verificabile interrompono il percorso. La policy di sola inferenza del server disabilita strumenti host, ricerca web, esecuzione codice e caricamento automatico; gli strumenti delle task rimangono quelli di Pi nella sandbox selezionata.
3. Conservare la chiave usando il gestore credenziali del proprio sistema, senza inserirla in `benchmark.json`, file `.env`, comandi o variabili d'ambiente. Il benchmark legge elementi già esistenti e non li crea né modifica:
   - **macOS:** in Accesso Portachiavi creare un elemento password generico con servizio/nome `LocalAgentBenchmark` e account `unsloth-local`. Nella finestra di creazione scegliere esplicitamente il portachiavi **login**; gli elementi salvati in iCloud non vengono trovati da questo lookup. Inserire la chiave nel campo Password.
   - **Windows:** in Gestione credenziali aggiungere una credenziale generica con destinazione `LocalAgentBenchmark:unsloth-local`; la password è la chiave API, conservata come stringa UTF-16. Il nome utente non è usato per il lookup.
   - **Linux:** usare un Secret Service disponibile nella sessione e `secret-tool`. Per creare un elemento interattivo: `secret-tool store --label='LocalAgent Benchmark Unsloth' service LocalAgentBenchmark account unsloth-local`; inserire la chiave al prompt del gestore, senza aggiungerla alla riga di comando.
4. Configurare il provider nel file centrale, usando la porta mostrata dalla propria installazione. L'URL è la sola origine, **senza `/v1`**:

   ```json
   "provider": {
     "kind": "unsloth",
     "url": "http://127.0.0.1:8888",
     "credential_ref": "unsloth-local",
     "runtime_version": "versione-Unsloth-verificata-localmente",
     "backend_version": "versione-backend-verificata-localmente",
     "model_files": {"ID_GGUF_DA_LIST": "/percorso/locale/modello.gguf"},
     "transport": {
       "timeout_seconds": 1200,
       "max_request_bytes": 8388608,
       "max_response_bytes": 33554432,
       "max_header_bytes": 16384,
       "max_connections": 16
     }
   }
   ```

   `credential_ref` è soltanto un nome scelto dall'utente e deve coincidere con l'account/riferimento del portachiavi. Tutti i limiti di `provider.transport` sono validati e facoltativi; i valori mostrati sono i default. Su Windows usare un percorso GGUF del tipo `C:/modelli/modello.gguf`. Per `compare` sono richiesti versione Unsloth dichiarata, `provider.backend_version` e digest GGUF; questi dati restano dichiarazioni dell'utente sull'installazione selezionata.
5. Eseguire `python3 benchmark.py doctor`, `python3 benchmark.py list`, quindi uno smoke su un solo ID realmente caricato: `python3 benchmark.py run --profile smoke --models ID_GGUF_DA_LIST --thinking off --sandbox required --timeout 300`. Su Windows usare `py -3` al posto di `python3`.

Per usare la CLI senza conservare la chiave nel portachiavi, scegliere esplicitamente il prompt in memoria **prima del sottocomando**:

```bash
python3 benchmark.py --credential-prompt doctor
python3 benchmark.py --credential-prompt list
python3 benchmark.py --credential-prompt run --profile smoke --models ID_GGUF_DA_LIST --thinking off --sandbox required --timeout 300
```

Ogni processo richiede nuovamente la chiave; il prompt richiede un terminale interattivo, non è persistito e non è disponibile nella GUI. Il percorso guidato legge il portachiavi prima del rilevamento e nelle singole fasi. La chiave reale resta nel gateway host a destinazione fissa; Pi riceve una chiave fittizia e soltanto il canale locale controllato. Nei risultati viene conservato l'endpoint di origine, senza la porta effimera del gateway o la chiave.

**Misure:** ogni POST di generazione attraversa due letture aggiuntive di policy/modelli nel gateway. Il loro tempo è incluso nella latenza al primo testo, nella durata E2E delle task Pi e nelle sonde Preliminary, incluso il denominatore token/s E2E. Preflight e warmup separati restano esclusi dalle metriche delle task. Per confronti usare lo stesso provider e condizioni compatibili; il costo del gateway non è decode puro.

**Contesto:** se il server dichiara una finestra caricata inferiore a `defaults.context_window`, il modello è escluso prima della generazione (`context_window_mismatch`). Ricaricarlo manualmente con una finestra sufficiente oppure scegliere esplicitamente una configurazione coerente prima di un nuovo run. Un contesto non dichiarato rimane sconosciuto; `compare` richiede finestre residenti dichiarate, positive e identiche fra i run, oltre a runtime/backend e digest.

**Lifecycle:** il benchmark verifica i GGUF già caricati; non esegue load/unload di Unsloth, non scarica pesi e non può certificare un reset della cache o un avvio a freddo. Caricamenti, scaricamenti e cambi del set di modelli sono operazioni manuali, da completare prima di un nuovo run. Un modello scaricato durante la prova fallisce il controllo invece di essere ricaricato automaticamente.

**Diagnosi:** chiave rifiutata (HTTP 401) → creare una nuova chiave nella stessa istanza Unsloth e aggiornare il campo password del portachiavi; credenziale assente/negata → controllare riferimento e accesso al gestore o usare il prompt CLI; chiave completa/policy non verificabile → creare una chiave `inference` su una versione supportata; elenco vuoto → caricare un GGUF locale; esclusione thinking → scegliere una combinazione modello/template che rispetti la modalità richiesta, senza fallback; timeout → controllare separatamente timeout della task, delle sonde Preliminary e del gateway. Le letture native dei portachiavi e gli smoke reali dipendono dalla piattaforma e richiedono verifica locale; test con server sintetici non attestano da soli la compatibilità di un'installazione Unsloth reale.

### Provenienza e confronti

Per `compare` su più run LM Studio/llama.cpp/Unsloth, aggiungere alla sezione `provider` la versione del runtime letta localmente (`lms --version` o `llama-server --version`) e il file GGUF effettivo di ogni modello selezionato:

```json
"runtime_version": "versione-letta-dal-comando-locale",
"model_files": {"id-esatto-da-benchmark-list": "C:/modelli/modello.gguf"}
```

I path restano locali; `run.json` registra solo SHA-256 e metadati in whitelist. La versione è **dichiarata dall'utente**, non verificata automaticamente dal server. `compare` rifiuta run con provider, endpoint, versione, hash, controllo thinking o altri parametri incompatibili; rifiuta anche versioni o hash GGUF mancanti. Un modello MLX di LM Studio, senza GGUF configurabile, può fare un singolo run ma non entra nell'aggregazione statistica. Hashare file grandi può richiedere tempo prima dell'avvio.

Il preflight usa `reasoning_effort: "none"` per `off` e verifica che non emerga reasoning; per le modalità attive richiede un segnale osservabile. Se il server ignora o rifiuta il controllo, il modello viene escluso senza fallback. Pi viene verificato separatamente contro un server sintetico con il provider configurato. Il sandbox `required` consente soltanto il canale verso l'endpoint loopback selezionato. LM Studio e llama.cpp sono processi host esterni alla sandbox; i GGUF non vengono copiati nella workspace della task.

## English

Pi remains the coding agent. The benchmark can connect it to **Ollama** (default), **LM Studio 0.4+**, the **llama.cpp `llama-server` router**, or **Unsloth** with an already-loaded local GGUF and an inference-only key. Each run uses a single provider for all phases. The GUI can discover models from multiple providers configured in `benchmark.json`. The server must use HTTP loopback. No extra Python packages or automatic model downloads are needed. Unsloth requires a protected local key; the original three adapters retain their unauthenticated mode.

The four providers use separate built-in adapters. Select one with `provider.kind` in `benchmark.json`; no extra recipe files are required, and run formats do not change.

### Configure multiple local providers

`provider` remains the default. Add the other providers to `additional_providers` as shown in the Italian example. Use the ports reported by your local servers and configure each `kind` once. Put `--provider` before a CLI subcommand to select a configured provider, for example `python3 benchmark.py --provider lmstudio list` or `python3 benchmark.py --provider unsloth doctor`. `--config` still selects an alternative configuration file in the project root.

### Colibrì setup

Prepare [Colibrì](https://github.com/JustVugg/colibri/blob/main/docs/api.md) manually and start `coli serve` on HTTP loopback with a resident chat model, working tool calling, enough context and automatic tool-call repairs disabled. Use `provider.kind: "colibri"`, the server origin such as `http://127.0.0.1:8000` and a `defaults.context_window` no larger than the window reported by `/v1/models`. Set a protected `credential_ref` when authentication is required, or use the CLI's explicit `--credential-prompt` before the subcommand. Guided mode uses the credential store.

Use `python3 benchmark.py --provider colibri doctor`, followed by a one-model smoke and Preliminary with `--thinking off --sandbox required`. The probe tests `none` and a synthetic structured tool call. Active effort stays unavailable until the runtime can demonstrate the effective level. The gateway sets `context_compaction: "off"`. The resident model and its KV cache remain under server control.

For `compare`, declare the runtime, backend, commit, engine, quantization, KV slots and persistence, and map the model ID to a complete `provider.colibri.model_bundles` entry as shown above. The benchmark hashes each explicitly listed regular file and rejects symlinks. The file association is a user declaration.

### Install and verify on Windows

1. Install Python 3.10+ and [Git for Windows](https://git-scm.com/download/win). Native Pi uses Git Bash for shell commands. Check `py -3 --version` and `git --version` in PowerShell.
2. To install Pi, install [Node.js with npm](https://nodejs.org/en/download), then use the [current official package](https://github.com/earendil-works/pi/tree/main/packages/coding-agent): `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`. Check `pi --version` and `py -3 benchmark.py doctor`. Keep an existing Pi installation if it already passes `doctor`; every version must pass the benchmark contract probe.
3. For Ollama, use the [official Windows installer](https://ollama.com/download/windows), start the app, and check `ollama --version`. Download a local tool-capable model with `ollama pull MODEL_NAME`, then check `ollama list`. The default benchmark endpoint is `http://127.0.0.1:11434`.
4. For LM Studio, use the [official installer](https://lmstudio.ai/download), open the app at least once, and download or import a tool-capable model. If the **Developer** tab is hidden, enable [**Developer Mode**](https://lmstudio.ai/docs/app/user-interface/modes) under **Settings → Developer**; older layouts have a **Developer** mode selector at the bottom of the window. Open **Developer** in the sidebar and [turn on the server](https://lmstudio.ai/docs/developer/rest/quickstart) with the toggle at the top left. Alternatively, if `lms` is available, run `lms server start --port 1234`.
5. For llama.cpp, follow the [official installation guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md): `winget install llama.cpp`, or extract a Windows build from the [official releases](https://github.com/ggml-org/llama.cpp/releases). Check `llama-server --version`; use the full path to `llama-server.exe` if needed. Prepare a directory of local GGUF files and use a build with router mode and `/models/load`.

Select **one provider per run** in `benchmark.json`. Finish a run before changing configuration or repository files: the runner checks source hashes between tasks. Other servers may stay running but are not used by that run. On macOS and Linux, use the official links above and the platform sandbox quick starts.

### Ollama

With the app running and a model downloaded, keep `"provider": {"kind": "ollama", "url": "http://127.0.0.1:11434"}` in `benchmark.json`. In PowerShell run `py -3 benchmark.py doctor`, `py -3 benchmark.py list`, then `py -3 benchmark.py run --profile smoke --models EXACT_NAME --thinking off --sandbox required --timeout 300`. Use the exact name from `list`.

### LM Studio

Enable **Developer Mode** under **Settings → Developer** if the **Developer** tab is hidden; older layouts have a mode selector at the bottom. Start the local server with the toggle at the top left of that tab, or run `lms server start --port 1234` if the CLI is available. Import an existing GGUF with `lms import <path-to-model.gguf> --copy`: without `--copy`, LM Studio moves the source file. Map `provider.model_files` to a file that still exists after import. Set `"provider": {"kind": "lmstudio", "url": "http://127.0.0.1:1234"}`. Run `py -3 benchmark.py doctor`, `py -3 benchmark.py list`, then `py -3 benchmark.py run --profile smoke --models EXACT_NAME --thinking off --sandbox required --timeout 300`. Select one model for the first smoke; guided mode reads the same configuration.

### GGUF with llama.cpp

Start a recent `llama-server` in router mode **without `--model`**:

```text
llama-server --models-dir <gguf-directory> --no-models-autoload --jinja --host 127.0.0.1 --port 8080 -c 32768
```

On Windows, replace `<gguf-directory>` with the real path in quotes; use the full path to `llama-server.exe` if needed. Keep `-c 32768` consistent with `defaults.context_window` in `benchmark.json` and ensure enough memory is available. Set `"provider": {"kind": "llama_cpp", "url": "http://127.0.0.1:8080"}`. The benchmark uses `/models/load` and `/models/unload`, so `--no-models-autoload` is supported. `--jinja` enables tool-compatible chat templates. This integration uses the official llama.cpp server. `node-llama-cpp` is a library; using it here would require a separate HTTP bridge implementing the provider API and controls.

`/models/load` and `/models/unload` may acknowledge requests before the model instance has finished changing state. The benchmark waits for `/models` to report `loaded` before inference and `unloaded` before another load. A failed child process or load timeout excludes the model before inference. Loading and unloading time do not count toward task timing.

### Unsloth

1. Manually install an [Unsloth version with the local API](https://unsloth.ai/docs/basics/api). Load a tool-capable **local GGUF** in the app and keep its HTTP loopback server running. Remote models, MLX models and models that have not been loaded are outside this release's Unsloth integration.
2. In **Settings → API**, enter a name and select **Create token**. In the new-key panel select **Inference**, then copy the complete value using its copy button before selecting **Done**. The key must have **`inference`** access without full privileges. The benchmark checks this restriction before inference; a full-access key, a server version lacking the required policy or an unverifiable check stops the flow. The server's inference-only policy disables provider-hosted tools, web search, code execution and automatic model loading. Task tools remain inside Pi under the selected sandbox.
3. Store the key using your OS credential manager. Do not put it in `benchmark.json`, `.env` files, command arguments or environment variables. The benchmark only reads existing entries; it does not create or modify them:
   - **macOS:** use Keychain Access to create a generic password item with service/name `LocalAgentBenchmark` and account `unsloth-local`. Explicitly select the **login** keychain in the creation dialog; this lookup does not find items saved in iCloud. Put the key in the Password field.
   - **Windows:** add a generic credential in Credential Manager with target `LocalAgentBenchmark:unsloth-local`; its password is the API key, stored as a UTF-16 string. The lookup does not use its user name.
   - **Linux:** provide a session Secret Service and `secret-tool`. Create an entry interactively with `secret-tool store --label='LocalAgent Benchmark Unsloth' service LocalAgentBenchmark account unsloth-local`, entering the key at the store's prompt rather than in the command line.
4. Use the same provider JSON shown in the Italian section. Replace the port with your installation's port; `provider.url` is the origin **without `/v1`**. `credential_ref` is a non-secret user-selected name matching the credential-store account/reference. The optional, validated `provider.transport` fields shown are the defaults: 1,200 seconds, 8 MiB request body, 32 MiB response body, 16 KiB headers and 16 concurrent connections. On Windows use a GGUF path such as `C:/models/model.gguf`. For `compare`, declare both the Unsloth runtime version and `provider.backend_version`, and provide GGUF digests. The runtime/backend versions remain user declarations about the selected installation.
5. Run `python3 benchmark.py doctor`, `python3 benchmark.py list`, then a single-model smoke: `python3 benchmark.py run --profile smoke --models LOADED_GGUF_ID --thinking off --sandbox required --timeout 300`. On Windows replace `python3` with `py -3`.

For the CLI's explicit memory-only key prompt, place `--credential-prompt` **before the subcommand**, for example `python3 benchmark.py --credential-prompt doctor` or `python3 benchmark.py --credential-prompt run --profile smoke --models LOADED_GGUF_ID --thinking off --sandbox required --timeout 300`. Each process asks again and requires an interactive terminal. The GUI has no key prompt: it reads the existing OS credential before discovery and each stage. The real key stays in the host's fixed-destination gateway; Pi receives only its dummy key and the controlled local channel. Results record the origin endpoint, excluding the gateway's ephemeral port and real key.

**Measurements:** each generation POST includes two additional gateway reads checking policy/models. Their latency is included in first-answer time, Pi task E2E duration and Preliminary probes, including the E2E tokens/s denominator. Separate preflight and warmup remain outside task metrics. Compare the same provider under compatible conditions; gateway overhead is not pure decode time.

**Context:** if the server reports a loaded window smaller than `defaults.context_window`, the model is excluded before generation (`context_window_mismatch`). Reload it manually with a sufficient window or explicitly choose a matching configuration before a new run. An unreported context remains unknown; `compare` requires reported, positive and identical resident windows across runs, as well as runtime/backend versions and digests.

**Lifecycle:** only already-loaded GGUF models are checked. The benchmark does not load/unload Unsloth models, download weights, certify cache reset or claim a cold start. Complete manual loading, unloading or model-set changes before a new run. A model unloaded during a run fails its check rather than being loaded automatically.

**Troubleshooting:** for a rejected key (HTTP 401), create a new key in the same Unsloth instance and update the OS-store password value; for missing/denied credentials, check the reference and OS-store access or use the CLI prompt; for full keys or unverifiable policy, create an `inference` key on a supported server; for an empty list, load a local GGUF; for thinking exclusions, use a model/template combination honoring the requested policy without fallback; for timeouts, distinguish task, Preliminary-probe and gateway deadlines. Native credential-store access and real smoke coverage depend on the host platform and require local verification. Synthetic HTTP tests alone do not certify a real Unsloth installation.

To aggregate LM Studio, llama.cpp or Unsloth runs, set `provider.runtime_version` from the local runtime command and map each exact model ID to its local GGUF file in `provider.model_files`, as in the JSON example above. Paths stay local; `run.json` records SHA-256 and allowlisted metadata. Runtime version is **user-declared**, not checked against the server. `compare` rejects missing provenance or incompatible provider, endpoint, version, digest, thinking control, or other settings. An LM Studio MLX model can run individually but cannot be statistically aggregated without a GGUF digest. Hashing a large model adds startup time.

The mandatory thinking preflight sends `reasoning_effort: "none"` for `off` and checks for observable reasoning; active modes require an observable signal. Rejected or unverifiable control excludes the model without fallback. The separate Pi contract probe uses the configured provider ID against a synthetic loopback server. `required` sandbox mode allows only the selected loopback endpoint. LM Studio and llama.cpp run on the host outside the task sandbox; GGUF files are never copied into task workspaces.

## Preliminary

I quattro provider possono essere descritti con `python3 benchmark.py run --profile preliminary`. Le sonde usano `/v1/chat/completions` in streaming senza strumenti e richiedono il protocollo SSE con usage quando disponibile. Il preflight thinking resta obbligatorio: nessun fallback se il provider non lo rispetta. Token/sec E2E e decode dichiarato sono distinti; campi mancanti risultano N/D.

All four providers support the independent Preliminary flow through streaming `/v1/chat/completions`, without tools. SSE usage is used when available. Thinking preflight remains mandatory, with no silent fallback. E2E tokens/s and provider-reported decode are distinct; unavailable fields stay N/A. See [Preliminary](QUICK-START_Preliminary.md).
