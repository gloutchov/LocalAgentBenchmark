# Preliminary — reattività e affidabilità / responsiveness and grounding

## Italiano

Preliminary è un profilo autonomo descrittivo della versione 0.14.0. Non produce punteggi, classifiche o promozioni. Il funnel ufficiale rimane smoke → standard → full.

Dalla root di un checkout con input committati:

```sh
python3 benchmark.py run --profile preliminary --models NOME_MODELLO --thinking off --sandbox required --seed 42
python3 benchmark.py report results/NOME_RUN
python3 dashboard.py results/NOME_RUN
```

`audit` è una scelta esplicita alternativa a `required`, senza isolamento OS. Anche Preliminary esegue il gate contrattuale Pi, il probe della sandbox selezionata, discovery, fingerprint, preflight thinking, snapshot e controlli di integrità. Le misure successive sono richieste HTTP host al solo endpoint loopback configurato, senza Pi, strumenti o accesso del modello al filesystem: il backend sandbox registrato riguarda il gate Pi, non le sonde HTTP. Non si eseguono download, chiamate Internet o valutazioni tramite altri LLM.

Nel percorso rapido il toggle **Preliminary: reattività e affidabilità** è inizialmente attivo nel nuovo `benchmark.json`; può essere disattivato prima dell'avvio. I vecchi file di configurazione senza questa opzione conservano il percorso a tre fasi. Il manifesto guidato registra la scelta. La fase descrive tutti i modelli selezionati; lentezza, risposte sbagliate, errori di protocollo della risposta e fallimenti delle singole misure non determinano promozioni. Soltanto i controlli obbligatori non validi escludono il modello. Lo smoke riparte con i propri preflight, unload e warmup; non eredita conversazioni dalla fase precedente.

### Misure

La suite versionata `preliminary/suite.json` comprende due contesti, breve e lungo, e 16 quesiti indipendenti: 8 con risposta presente, 4 con informazione assente, 4 con premessa falsa. Per impostazione iniziale si eseguono tre ripetizioni per contesto e una prova per quesito: **22 richieste per modello**, oltre ai controlli e al warmup. Modelli lenti possono richiedere diversi minuti; non è una stima della durata delle task di coding.

- **Primo testo (s):** dall'invio HTTP al primo testo visibile della risposta, escludendo campi e tag reasoning riconosciuti. Un output privo di risposta ha valore N/D.
- **Durata (s):** intera richiesta in streaming fino alla conclusione. Include attesa, elaborazione input e reasoning.
- **Token/s E2E:** token output dichiarati dal provider divisi per durata completa. Include reasoning quando incluso nel conteggio del provider; non è velocità pura di decode e non si ricava dividendo token per il tempo delle task agentiche.
- **Decode token/s:** valore `timings.predicted_per_second` soltanto se fornito dal provider. Le altre API possono lasciarlo N/D; non si simula una misura equivalente.
- **Pausa max (s):** massimo intervallo osservato fra eventi di testo visibile ricevuti dal client. Può risentire del buffering e non è latenza per singolo token.

Report e dashboard mostrano mediane e, per primo testo e token/s E2E, intervallo minimo–massimo. I singoli campioni sono in `run.json`. Non si stimano percentili affidabili da tre ripetizioni. Campioni falliti e risposte troncate sono contati esplicitamente; non sono sostituiti da zero. Le metriche disponibili derivano dai soli campioni completati che le espongono. Confrontare hardware, quantizzazione, versione provider, context window, temperature, lunghezza effettiva degli output e modalità thinking compatibili. Tokenizer differenti rendono il token/s una misura specifica del modello/runtime.

La sequenza di modelli e sonde è registrata con `--seed`; ogni richiesta contiene un identificativo deterministico diverso e usa una conversazione nuova. Questo riduce il riuso dei prefissi fra ripetizioni, ma non svuota o certifica le cache interne del runtime. Le misure sono **successive al preflight**, con unload e warmup registrati; non sono presentate come avvii a freddo verificati. Un warmup viene eseguito per cambio modello quando abilitato. Ogni modello viene scaricato al termine, anche dopo errori, prima del passaggio allo smoke.

### Affidabilità rispetto alle fonti

Il modello deve rispondere nel protocollo JSON richiesto (`status`, `value`), senza spiegazioni. Lo stesso documento sintetico accompagna ciascuna domanda: nessuna dipendenza dalla conoscenza generale o da altri quesiti. Il grader confronta categoria e valore attesi; non valuta né premia la catena di pensiero.

Si registrano separatamente risposte note corrette, informazioni mancanti riconosciute, premesse corrette, risposte non supportate a domande mancanti/con premessa falsa, astensioni inutili su domande rispondibili, errori residui, risposte non valutabili e fallimenti tecnici. Risposte non JSON o troncate sono non valutabili, non automaticamente allucinazioni. Un modello che dice sempre “non lo so” non ottiene successo sulle domande note o con premessa falsa. Questi conteggi descrivono soltanto questa batteria controllata, non un tasso generale di allucinazioni.

### Configurazione e output

La sezione `preliminary` di `benchmark.json` configura percorso suite confinato, ripetizioni (2–20), max token (64–8192), timeout per richiesta (10–1200 s), limite totale risposta e limite evento. `--repetitions` e `--timeout` sovrascrivono ripetizioni e timeout; `--cases` non è accettato con questo profilo. Non sono ammessi retry automatici o fallback thinking. I parametri della fase sono registrati nel manifesto; la suite è copiata e hashata insieme alla policy e alle istruzioni. Input sporchi/non tracciati o snapshot mutato fanno fallire i controlli. Non modificare la suite durante un run.

Ogni run ha `run.json`, `report.json`, `REPORT.md` e `benchmark-context/`. Le osservazioni locali includono risposte finali dei quesiti e soli metadati di errore; i campi reasoning e i tag `<think>` riconosciuti vengono scartati prima della persistenza. La rimozione non dimostra l'assenza di reasoning non dichiarato dal provider. Non vengono prodotti `result.json` di task agentiche. Output confinato alla root del progetto, senza sovrascrivere run esistenti. Il client rifiuta proxy, redirect, endpoint remoti, stream incompleti, eventi malformati, payload eccessivi e timeout; non salva body HTTP di errore.

`dashboard-data` esporta in schema 4 soltanto aggregati esplicitamente autorizzati da `run.json` e `report.json`; schema 1/2/3 e snapshot precedenti restano leggibili. Non esporta suite, prompt, risposte, reasoning, eventi raw, path o errori liberi. Preliminary è separato per run/thinking, fuori dal funnel e dalle mappe qualità/efficienza. `compare` rifiuta questo profilo, evitando classifiche statistiche implicite. La dashboard resta offline e lo snapshot locale è opzionale, ignorato da Git e generato soltanto con il comando esplicito documentato nella guida Dashboard.

## English

Preliminary is an independent descriptive profile introduced in 0.14.0. It creates no scores, rankings or promotions. The official funnel remains smoke → standard → full.

Run the commands above from a checkout with committed inputs, replacing the model and result-directory names. `audit` is an explicit alternative to `required`, without OS isolation. Preliminary retains the Pi contract gate, selected sandbox probe, discovery, fingerprints, thinking preflight, snapshot and integrity checks. Subsequent measurements are host HTTP calls to the configured loopback endpoint, without Pi, tools or model filesystem access: recorded sandbox enforcement applies to the Pi gate, not HTTP probes. There are no downloads, Internet requests or external LLM judges.

The quick path initially enables **Preliminary: responsiveness and grounding** in the new configuration. Turn it off before starting to retain the three-stage path. Legacy configurations without the option retain their previous behavior. The guided manifest records the choice. Slowness, incorrect answers, answer-protocol errors and individual measurement failures do not select or promote models. Mandatory control failures still exclude a model. Smoke performs its own preflight, unload and warmup, with no conversation inherited from Preliminary.

### Measurements

The versioned `preliminary/suite.json` contains short and long contexts and 16 independent questions: 8 answerable, 4 missing-information and 4 false-premise questions. Defaults run three repetitions per context and each question once: **22 requests per model**, plus gates and warmup. Slow models may take several minutes; this is not a coding-task duration estimate.

- **First answer (s):** request submission to the first visible answer text, excluding recognized reasoning fields/tags; N/A when no answer text arrives.
- **Duration (s):** full streaming request, including waiting, input processing and reasoning.
- **E2E tokens/s:** provider-reported output tokens divided by full request duration, including reasoning when included in provider counts. This is not pure decode throughput or tokens divided by agent-task duration.
- **Decode tokens/s:** `timings.predicted_per_second` only when the provider supplies it. Unsupported telemetry remains N/A.
- **Max gap (s):** longest observed gap between received visible-text events. Buffering affects this measure; it is not per-token latency.

Reports and dashboard display medians, plus minimum–maximum ranges for first answer and E2E tokens/s. Raw samples remain in `run.json`. Three repetitions do not establish reliable tail percentiles. Failed samples and truncated answers are counted separately, never replaced by zero. Available metrics use completed samples that actually expose each metric. Compare compatible hardware, quantization, provider versions, context windows, temperature, actual output lengths and thinking modes. Different tokenizers make tokens/s specific to the model/runtime.

`--seed` records reproducible model/probe order; requests use distinct deterministic identifiers and fresh conversations. This reduces repeated-prefix reuse but neither clears nor certifies runtime caches. Measurements occur **after preflight**, with recorded unload/warmup, and never claim verified cold-start behavior. Enabled warmup runs at each model change. Models are unloaded at the end, including on error, before smoke begins.

### Grounding against supplied sources

Every question includes its own synthetic document and requires exactly the JSON protocol (`status`, `value`), without explanations. Grading matches the expected category and value, with no external facts, dependence on previous questions or evaluation of chain of thought.

Counts distinguish correct known answers, recognized missing information, corrected false premises, unsupported answers to missing/false-premise questions, unnecessary abstentions on answerable questions, other incorrect answers, unscorable responses and technical failures. Non-JSON or truncated responses are unscorable rather than automatically hallucinations. Always answering “unknown” does not pass answerable or false-premise controls. Counts characterize this controlled suite, not a universal hallucination rate.

### Configuration and output

The `preliminary` section of `benchmark.json` controls the confined suite path, repetitions (2–20), max tokens (64–8192), per-request timeout (10–1200 seconds), response limit and event limit. `--repetitions` and `--timeout` override the respective settings; `--cases` is rejected for this profile. No automatic retries or thinking fallbacks occur. Settings are recorded; the suite, policy and instructions are frozen and hashed. Dirty/untracked inputs or a changed shared snapshot fail integrity controls. Never edit the suite during a run.

Runs contain `run.json`, `report.json`, `REPORT.md` and `benchmark-context/`. Local observations retain final question answers and error metadata only. Recognized reasoning fields and `<think>` blocks are removed before persistence; this does not establish absence of reasoning that the provider does not identify. No agent-task `result.json` files are created. Output stays in the project root without overwriting existing runs. The client refuses proxies, redirects, remote endpoints, incomplete/malformed streams, excessive payloads and timeouts, and does not save HTTP error bodies.

`dashboard-data` schema 4 exports only explicitly whitelisted aggregates from `run.json` and `report.json`. Legacy schemas 1/2/3 remain readable. Suite contents, prompts, responses, reasoning, raw events, paths and free-form errors are excluded. Preliminary stays separate by run/thinking, outside the funnel and quality/efficiency maps. `compare` rejects this descriptive profile. Dashboard runtime stays offline; its optional local snapshot remains Git-ignored and requires the explicit command in the Dashboard guide.
