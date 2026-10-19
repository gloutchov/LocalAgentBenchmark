# Provider locali / Local model providers

## Italiano

Il benchmark usa Pi come agente e può collegarlo a **Ollama** (default), **LM Studio 0.4 o successivo** oppure al **router `llama-server` di llama.cpp**. Configurare un solo provider alla volta in `benchmark.json`; lo stesso provider viene usato da CLI, percorso guidato, preflight, warmup e task. Il server deve restare su loopback HTTP (`127.0.0.1`, `localhost` o `::1`). Non servono pacchetti Python aggiuntivi, token o download automatici.

### Installazione e verifica su Windows

1. Installare Python 3.10+ e [Git for Windows](https://git-scm.com/download/win). Pi nativo usa Git Bash per i comandi shell; verificare `py -3 --version` e `git --version` in PowerShell.
2. Per installare Pi, installare [Node.js con npm](https://nodejs.org/en/download), poi seguire il [pacchetto ufficiale corrente](https://github.com/earendil-works/pi/tree/main/packages/coding-agent): `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`. Verificare `pi --version` e `py -3 benchmark.py doctor`. Se Pi è già installato e supera `doctor`, non occorre aggiornarlo: ogni versione deve superare il controllo contrattuale del benchmark.
3. Per Ollama, usare l'[installer Windows ufficiale](https://ollama.com/download/windows), avviare l'app e verificare `ollama --version`. Scaricare un modello locale adatto al tool calling con `ollama pull NOME_MODELLO`, poi controllare `ollama list`. Il provider predefinito del benchmark usa `http://127.0.0.1:11434`.
4. Per LM Studio, usare l'[installer ufficiale](https://lmstudio.ai/download), aprire l'app almeno una volta, scaricare o importare un modello adatto al tool calling e avviare il server dalla scheda Developer. In alternativa, verificare `lms --version` e usare `lms server start --port 1234`.
5. Per llama.cpp, seguire le [istruzioni ufficiali](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md): `winget install llama.cpp`, oppure estrarre un pacchetto Windows dalle [release ufficiali](https://github.com/ggml-org/llama.cpp/releases). Verificare che `llama-server --version` funzioni, usando il path completo a `llama-server.exe` se il binario non è nel `PATH`. Preparare una directory con GGUF locali; serve una versione con modalità router e `/models/load`.

Selezionare **un solo provider per run** in `benchmark.json`. Attendere la fine di un run prima di modificare la configurazione o i file del repository: il runner controlla gli hash delle sorgenti tra le task. Gli altri server possono restare avviati, ma non vengono usati dal run. Per macOS e Linux usare le pagine ufficiali collegate sopra e i requisiti sandbox descritti nei quick start di piattaforma.

### Ollama

Con l'app in esecuzione e almeno un modello già scaricato, lasciare `"provider": {"kind": "ollama", "url": "http://127.0.0.1:11434"}` in `benchmark.json`. Da PowerShell eseguire `py -3 benchmark.py doctor`, `py -3 benchmark.py list`, poi `py -3 benchmark.py run --profile smoke --models NOME_ESATTO --thinking off --sandbox required --timeout 300`. Il nome esatto è quello mostrato da `list`.

### LM Studio

1. Installare LM Studio, scegliere un modello capace di tool calling e avviare il server dalla scheda Developer oppure con `lms server start --port 1234`. Un GGUF già scaricato può essere importato con `lms import <percorso-al-modello.gguf> --copy`; senza `--copy`, LM Studio sposta il file originale.
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

### Provenienza e confronti

Per `compare` su più run LM Studio/llama.cpp, aggiungere alla sezione `provider` la versione del runtime letta localmente (`lms --version` o `llama-server --version`) e il file GGUF effettivo di ogni modello selezionato:

```json
"runtime_version": "versione-letta-dal-comando-locale",
"model_files": {"id-esatto-da-benchmark-list": "C:/modelli/modello.gguf"}
```

I path restano locali; `run.json` registra solo SHA-256 e metadati in whitelist. La versione è **dichiarata dall'utente**, non verificata automaticamente dal server. `compare` rifiuta run con provider, endpoint, versione, hash, controllo thinking o altri parametri incompatibili; rifiuta anche versioni o hash GGUF mancanti. Un modello MLX di LM Studio, senza GGUF configurabile, può fare un singolo run ma non entra nell'aggregazione statistica. Hashare file grandi può richiedere tempo prima dell'avvio.

Il preflight usa `reasoning_effort: "none"` per `off` e verifica che non emerga reasoning; per le modalità attive richiede un segnale osservabile. Se il server ignora o rifiuta il controllo, il modello viene escluso senza fallback. Pi viene verificato separatamente contro un server sintetico con il provider configurato. Il sandbox `required` consente soltanto il canale verso l'endpoint loopback selezionato. LM Studio e llama.cpp sono processi host esterni alla sandbox; i GGUF non vengono copiati nella workspace della task.

## English

Pi remains the coding agent. The benchmark can connect it to **Ollama** (default), **LM Studio 0.4+**, or the **llama.cpp `llama-server` router**. Select one provider at a time in `benchmark.json`; CLI, guided mode, preflight, warmup, and tasks share it. The server must use HTTP loopback. No extra Python packages, tokens, or automatic model downloads are needed.

### Install and verify on Windows

1. Install Python 3.10+ and [Git for Windows](https://git-scm.com/download/win). Native Pi uses Git Bash for shell commands. Check `py -3 --version` and `git --version` in PowerShell.
2. To install Pi, install [Node.js with npm](https://nodejs.org/en/download), then use the [current official package](https://github.com/earendil-works/pi/tree/main/packages/coding-agent): `npm install -g --ignore-scripts @earendil-works/pi-coding-agent`. Check `pi --version` and `py -3 benchmark.py doctor`. Keep an existing Pi installation if it already passes `doctor`; every version must pass the benchmark contract probe.
3. For Ollama, use the [official Windows installer](https://ollama.com/download/windows), start the app, and check `ollama --version`. Download a local tool-capable model with `ollama pull MODEL_NAME`, then check `ollama list`. The default benchmark endpoint is `http://127.0.0.1:11434`.
4. For LM Studio, use the [official installer](https://lmstudio.ai/download), open the app at least once, download or import a tool-capable model, and start its server from Developer. Alternatively, check `lms --version` and run `lms server start --port 1234`.
5. For llama.cpp, follow the [official installation guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md): `winget install llama.cpp`, or extract a Windows build from the [official releases](https://github.com/ggml-org/llama.cpp/releases). Check `llama-server --version`; use the full path to `llama-server.exe` if needed. Prepare a directory of local GGUF files and use a build with router mode and `/models/load`.

Select **one provider per run** in `benchmark.json`. Finish a run before changing configuration or repository files: the runner checks source hashes between tasks. Other servers may stay running but are not used by that run. On macOS and Linux, use the official links above and the platform sandbox quick starts.

### Ollama

With the app running and a model downloaded, keep `"provider": {"kind": "ollama", "url": "http://127.0.0.1:11434"}` in `benchmark.json`. In PowerShell run `py -3 benchmark.py doctor`, `py -3 benchmark.py list`, then `py -3 benchmark.py run --profile smoke --models EXACT_NAME --thinking off --sandbox required --timeout 300`. Use the exact name from `list`.

### LM Studio

Start the local server in Developer or run `lms server start --port 1234`. Import an existing GGUF with `lms import <path-to-model.gguf> --copy`: without `--copy`, LM Studio moves the source file. Map `provider.model_files` to a file that still exists after import. Set `"provider": {"kind": "lmstudio", "url": "http://127.0.0.1:1234"}`. Run `py -3 benchmark.py doctor`, `py -3 benchmark.py list`, then `py -3 benchmark.py run --profile smoke --models EXACT_NAME --thinking off --sandbox required --timeout 300`. Select one model for the first smoke; guided mode reads the same configuration.

### GGUF with llama.cpp

Start a recent `llama-server` in router mode **without `--model`**:

```text
llama-server --models-dir <gguf-directory> --no-models-autoload --jinja --host 127.0.0.1 --port 8080 -c 32768
```

On Windows, replace `<gguf-directory>` with the real path in quotes; use the full path to `llama-server.exe` if needed. Keep `-c 32768` consistent with `defaults.context_window` in `benchmark.json` and ensure enough memory is available. Set `"provider": {"kind": "llama_cpp", "url": "http://127.0.0.1:8080"}`. The benchmark uses `/models/load` and `/models/unload`, so `--no-models-autoload` is supported. `--jinja` enables tool-compatible chat templates. This integration uses the official llama.cpp server. `node-llama-cpp` is a library; using it here would require a separate HTTP bridge implementing the provider API and controls.

To aggregate LM Studio or llama.cpp runs, set `provider.runtime_version` from the local runtime command and map each exact model ID to its local GGUF file in `provider.model_files`, as in the JSON example above. Paths stay local; `run.json` records SHA-256 and allowlisted metadata. Runtime version is **user-declared**, not checked against the server. `compare` rejects missing provenance or incompatible provider, endpoint, version, digest, thinking control, or other settings. An LM Studio MLX model can run individually but cannot be statistically aggregated without a GGUF digest. Hashing a large model adds startup time.

The mandatory thinking preflight sends `reasoning_effort: "none"` for `off` and checks for observable reasoning; active modes require an observable signal. Rejected or unverifiable control excludes the model without fallback. The separate Pi contract probe uses the configured provider ID against a synthetic loopback server. `required` sandbox mode allows only the selected loopback endpoint. LM Studio and llama.cpp run on the host outside the task sandbox; GGUF files are never copied into task workspaces.
