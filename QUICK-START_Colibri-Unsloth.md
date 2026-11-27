# Provare i modelli Colibrì e Unsloth uno alla volta / Test Colibrì and Unsloth models one at a time

## Italiano

1. Configura Colibrì e Unsloth in `benchmark.json` come `provider` e `additional_providers` oppure usa un file di configurazione separato nella root del progetto per ciascuno. La [guida ai provider locali](QUICK-START_LocalProviders.md) descrive endpoint, credenziali e finestra di contesto.
2. Carica un GGUF locale in Unsloth Studio e usa una chiave di sola inferenza dal portachiavi. Per Colibrì avvia `coli serve` su loopback con il modello chat scelto e una finestra di contesto sufficiente. Imposta `defaults.context_window` a un valore comune supportato da tutti i modelli che vuoi confrontare. Per entrambi i provider, `benchmark.py --provider … list` mostra l’ID del modello caricato.
3. Esegui lo stesso profilo per ogni modello. Al termine di un run carica il successivo nel provider, verifica il nuovo ID e ripeti con una directory di output distinta. Lascia stabili versione del benchmark, casi, contesto, seed, thinking, sandbox, timeout, warmup e ripetizioni. Durante le misure evita altri carichi di inferenza sulla stessa macchina.
4. Apri insieme le directory dei run nella dashboard locale. Leggi qualità, durata, token e integrità per ciascun run e annota provider, motore e quantizzazione. Se cambi provider, le prestazioni descrivono la combinazione modello e motore. `compare` richiede run compatibili per l’aggregazione statistica. Preliminary usa misure descrittive indipendenti dalla classifica.

Nel percorso rapido, carica il modello prima di aprire la GUI oppure premi **Rileva di nuovo** dopo averlo cambiato. Seleziona la riga del modello e controlla la colonna **Provider**. Lascia **Thinking attivo** spento e abilita **Sandbox OS obbligatoria**. Per confrontare soltanto lo smoke usa i comandi qui sotto. Dalla GUI, i risultati dello stesso stadio sono nelle sottodirectory del tipo `results/guided-…/smoke`.

Con Colibrì verifica la finestra dichiarata da `/v1/models`. Nella prova M17 un prompt Pi da 13.232 token è stato rifiutato con una finestra di 8.192 token. Con 32.768 token il server lo ha accettato, ma la task ha raggiunto il timeout mentre il modello elaborava ancora il prompt. Consulta lo stato nel report prima di interpretare il punteggio.

## English

1. Configure Colibrì and Unsloth as `provider` and `additional_providers` in `benchmark.json`, or use a separate configuration file for each in the project root. See the [local provider guide](QUICK-START_LocalProviders.md) for endpoints, credentials, and context settings.
2. Load a local GGUF in Unsloth Studio and use an inference-only key from the OS credential store. For Colibrì, start `coli serve` on loopback with the chosen chat model and enough context. Set `defaults.context_window` to a common value supported by every model you want to compare. For either provider, `benchmark.py --provider … list` displays the loaded model’s ID.
3. Run the same profile for every model. When a run ends, load the next model in its provider, verify the new ID, and repeat with a distinct output directory. Keep the benchmark version, cases, context, seed, thinking, sandbox, timeout, warmup, and repetitions consistent. Avoid other inference workloads on the same machine during measurements.
4. Open the run directories together in the local dashboard. Read quality, duration, tokens, and integrity for each run and note its provider, engine, and quantization. Across providers, performance reflects the model and engine combination. `compare` requires compatible runs for statistical aggregation. Preliminary measures stay outside the ranking.

For the guided path, load the model before opening the GUI or click **Detect again** after switching it. Select the model’s row and check the **Provider** column. Leave **Enable thinking** off and select **Require OS sandbox**. Use the commands below for a smoke-only comparison. From the GUI, find matching stages in directories such as `results/guided-…/smoke`.

For Colibrì, check the context window reported by `/v1/models`. In M17 testing, an 8,192-token window rejected a 13,232-token Pi prompt. The server accepted the prompt at 32,768 tokens, but the task timed out during prompt processing. Check the status in the report before interpreting the score.

## Comandi / Commands

Esegui dalla root del progetto con entrambi i provider configurati in `benchmark.json`. Sostituisci gli ID con quelli stampati da `list` e scegli directory nuove ad ogni ripetizione. Se usi file separati, aggiungi `--config NOME_FILE.json` prima del sottocomando.

Run from the project root with both providers configured in `benchmark.json`. Replace the model IDs with the values printed by `list` and choose new output directories each time. With separate configuration files, add `--config FILE_NAME.json` before the subcommand.

```bash
python3 benchmark.py --provider unsloth list
python3 benchmark.py --provider unsloth run --profile smoke --models ID_UNSLOTH \
  --thinking off --sandbox required --seed 17 --repetitions 1 --timeout 1200 --warmup \
  --output results/smoke-unsloth-a

python3 benchmark.py --provider colibri list
python3 benchmark.py --provider colibri run --profile smoke --models ID_COLIBRI \
  --thinking off --sandbox required --seed 17 --repetitions 1 --timeout 1200 --warmup \
  --output results/smoke-colibri-a

python3 dashboard.py results/smoke-unsloth-a results/smoke-colibri-a
```

[Dashboard ufficiale / Official dashboard](QUICK-START_Dashboard.md) · [Percorso rapido / Guided quick path](QUICK-START_Guided.md)
