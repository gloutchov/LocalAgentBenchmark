# Provider locali / Local model providers

## Italiano

Il benchmark usa Pi come agente e può collegarlo a **Ollama** (default), **LM Studio 0.4 o successivo** oppure al **router `llama-server` di llama.cpp**. Configurare un solo provider alla volta in `benchmark.json`; lo stesso provider viene usato da CLI, percorso guidato, preflight, warmup e task. Il server deve restare su loopback HTTP (`127.0.0.1`, `localhost` o `::1`). Non servono pacchetti Python aggiuntivi, token o download automatici.

### LM Studio

1. Installare LM Studio, scegliere un modello capace di tool calling e avviare il server dalla scheda Developer oppure con `lms server start --port 1234`. Un GGUF già scaricato può essere importato con `lms import <percorso-al-modello.gguf> --copy`; senza `--copy`, LM Studio sposta il file originale.
2. Impostare in `benchmark.json`:

   ```json
   "provider": {"kind": "lmstudio", "url": "http://127.0.0.1:1234"}
   ```

3. Eseguire `python3 benchmark.py doctor`, poi `python3 benchmark.py list` e `python3 benchmark.py run --profile smoke --thinking off --sandbox required`. Il percorso guidato usa la stessa configurazione.

### GGUF con llama.cpp

Avviare una build recente di `llama-server` **in modalità router**, senza `--model`, con file GGUF locali:

```bash
llama-server --models-dir <directory-gguf> --no-models-autoload --jinja --host 127.0.0.1 --port 8080 -c 32768
```

`--jinja` abilita i template per il tool calling. Il benchmark carica e scarica i modelli selezionati tramite `/models/load` e `/models/unload`, quindi funziona anche con `--no-models-autoload`. Impostare:

```json
"provider": {"kind": "llama_cpp", "url": "http://127.0.0.1:8080"}
```

Poi eseguire `doctor`, `list` e uno smoke come sopra. L'integrazione usa il server ufficiale llama.cpp. `node-llama-cpp` è una libreria: per usarla con questo benchmark occorrerebbe un bridge HTTP che implementi l'API e i controlli del provider; non è un adapter incluso.

### Provenienza e confronti

Per `compare` su più run LM Studio/llama.cpp, aggiungere alla sezione `provider` la versione del runtime letta localmente (`lms --version` o `llama-server --version`) e il file GGUF effettivo di ogni modello selezionato:

```json
"runtime_version": "versione-letta-dal-comando-locale",
"model_files": {"id-esatto-da-benchmark-list": "C:/modelli/modello.gguf"}
```

I path restano locali; `run.json` registra solo SHA-256 e metadati in whitelist. La versione è **dichiarata dall'utente**, non verificata automaticamente dal server. `compare` rifiuta run con provider, endpoint, versione, hash, controllo thinking o altri parametri incompatibili; rifiuta anche versioni o hash GGUF mancanti. Un modello MLX di LM Studio, senza GGUF configurabile, può fare un singolo run ma non entra nell'aggregazione statistica. Hashare file grandi può richiedere tempo prima dell'avvio.

Il preflight usa `reasoning_effort: "none"` per `off` e verifica che non emerga reasoning; per le modalità attive richiede un segnale osservabile. Se il server ignora o rifiuta il controllo, il modello viene escluso senza fallback. Pi viene verificato separatamente contro un server sintetico con il provider configurato. Il sandbox `required` consente soltanto il canale verso l'endpoint loopback selezionato. LM Studio e llama.cpp sono processi host esterni alla sandbox; i GGUF non vengono copiati nella workspace della task.

## English

`lms import` moves the source file by default. Use `lms import <path-to-model.gguf> --copy` to retain it, and map `provider.model_files` to a file that still exists after import.

Pi remains the coding agent. The benchmark can connect it to **Ollama** (default), **LM Studio 0.4+**, or the **llama.cpp `llama-server` router**. Select one provider at a time in `benchmark.json`; CLI, guided mode, preflight, warmup, and tasks share it. The server must use HTTP loopback. No extra Python packages, tokens, or automatic model downloads are needed.

For LM Studio, start the local server in Developer or run `lms server start --port 1234`. Import an existing GGUF with `lms import <path-to-model.gguf>`. Set `"provider": {"kind": "lmstudio", "url": "http://127.0.0.1:1234"}`. Run `python3 benchmark.py doctor`, `python3 benchmark.py list`, then `python3 benchmark.py run --profile smoke --thinking off --sandbox required`. Guided mode reads the same configuration.

For llama.cpp, start a recent `llama-server` router with the command above, **without `--model`**. Set `"provider": {"kind": "llama_cpp", "url": "http://127.0.0.1:8080"}`. The benchmark uses `/models/load` and `/models/unload`, so `--no-models-autoload` is supported. `--jinja` enables tool-compatible chat templates. This integration uses the official llama.cpp server. `node-llama-cpp` is a library; using it here would require a separate HTTP bridge implementing the provider API and controls.

To aggregate LM Studio or llama.cpp runs, set `provider.runtime_version` from the local runtime command and map each exact model ID to its local GGUF file in `provider.model_files`, as in the JSON example above. Paths stay local; `run.json` records SHA-256 and allowlisted metadata. Runtime version is **user-declared**, not checked against the server. `compare` rejects missing provenance or incompatible provider, endpoint, version, digest, thinking control, or other settings. An LM Studio MLX model can run individually but cannot be statistically aggregated without a GGUF digest. Hashing a large model adds startup time.

The mandatory thinking preflight sends `reasoning_effort: "none"` for `off` and checks for observable reasoning; active modes require an observable signal. Rejected or unverifiable control excludes the model without fallback. The separate Pi contract probe uses the configured provider ID against a synthetic loopback server. `required` sandbox mode allows only the selected loopback endpoint. LM Studio and llama.cpp run on the host outside the task sandbox; GGUF files are never copied into task workspaces.
