# Avvio rapido Windows / Windows Quick Start

## Italiano

### Requisiti

- Windows 10 o 11;
- Python 3.10+, Git, Pi compatibile e un provider locale già configurato: Ollama, LM Studio o router llama.cpp;
- almeno un modello locale capace di tool calling;
- esecuzione come utente standard, con permesso di creare un profilo AppContainer e modificare temporaneamente le ACL dei path del run.

AppContainer è incluso in Windows: non occorre installare un pacchetto sandbox. Non avviare il benchmark da una shell elevata salvo diagnosi amministrativa esplicita.

Per installare e verificare Pi, Ollama, LM Studio e `llama-server`, seguire [QUICK-START_LocalProviders.md](QUICK-START_LocalProviders.md). Configurare il provider in `benchmark.json` prima del run e non cambiare configurazione o file del repository mentre il benchmark è in esecuzione.

### Verifica e smoke test

In PowerShell:

```powershell
py -3 benchmark.py doctor
py -3 benchmark.py list
py -3 benchmark.py run --profile smoke --models NOME_ESATTO --thinking off --sandbox required --timeout 300
```

`doctor` deve verificare Pi sul server sintetico locale, incluso lo staging AppContainer, e accettare una versione compatibile e riportare `windows-appcontainer` con isolamento filesystem, processi e rete. Prima della task, il preflight deve inoltre confermare `reasoning_effort: "none"`; `--no-warmup` non lo disabilita. In `required`, un probe fallito interrompe il run prima delle task. `auto` consente invece un fallback registrato e `audit` applica soltanto policy e rilevamento.

Per il primo smoke selezionare un solo nome esatto mostrato da `list`; `--timeout 300` limita la durata di ciascuna task, mentre il preflight thinking e il controllo Pi restano obbligatori. Il launcher crea un profilo AppContainer senza capability di rete, prepara una copia per-task dei runtime Pi/Node/Python, configura nella copia il tool shell di Pi su `cmd.exe`, concede ACL temporanee al SID esatto soltanto per workspace, configurazione Pi e runtime staged, assegna il processo sospeso a un Job Object kill-on-close e poi lo avvia. Un named pipe nel namespace AppContainer raggiunge un broker host vincolato all'host e alla porta del provider configurato.

### Risoluzione problemi

- Se il probe segnala `AppContainer non utilizzabile`, rieseguire `doctor` come lo stesso utente che lancerà il benchmark e controllare che workspace, directory Pi e installazione Pi siano accessibili.
- Se Pi non parte, verificare prima `pi --version` e `py -3 benchmark.py doctor` nella stessa shell; controllare anche `ollama list` o il catalogo del provider scelto.
- Durante o dopo un errore, consultare `.benchmark-scratch/windows-sandbox.json` nella workspace della task. Contiene stato di cleanup, fasi del broker e conteggi byte, non i payload del provider.
- Profilo e ACE vengono rimossi in best effort. Dopo un arresto anomalo, conservare i metadata e diagnosticare l'eventuale residuo prima di cancellarlo manualmente.
- Se `required` fallisce, non descrivere il run come sandboxed e non confrontarlo con run enforced.

## English

### Requirements

- Windows 10 or 11;
- Python 3.10+, Git, compatible Pi, and one configured local provider: Ollama, LM Studio, or the llama.cpp router;
- at least one local model capable of tool calling;
- a standard-user session allowed to create an AppContainer profile and temporarily update ACLs on run paths.

AppContainer is built into Windows; no sandbox package is required. Do not launch the benchmark from an elevated shell except for explicit administrative diagnosis.

Follow [QUICK-START_LocalProviders.md](QUICK-START_LocalProviders.md) to install and verify Pi, Ollama, LM Studio, and `llama-server`. Select the provider in `benchmark.json` before a run, and do not change configuration or repository files while the benchmark runs.

### Verification and smoke test

In PowerShell:

```powershell
py -3 benchmark.py doctor
py -3 benchmark.py list
py -3 benchmark.py run --profile smoke --models EXACT_NAME --thinking off --sandbox required --timeout 300
```

`doctor` must test Pi on the local synthetic server, including AppContainer staging, and accept a compatible version and report `windows-appcontainer` with filesystem, process, and network isolation. Before the task, preflight must also confirm `reasoning_effort: "none"`; `--no-warmup` does not disable it. In `required` mode, a failed probe stops before any task. `auto` permits a recorded fallback, while `audit` applies policy and detection only.

For the first smoke test, select one exact model name from `list`. `--timeout 300` limits each task; the thinking preflight and Pi contract probe still run. The launcher creates an AppContainer profile without network capabilities, prepares per-task copies of the Pi/Node/Python runtimes, configures Pi's staged shell tool to use `cmd.exe`, grants temporary ACLs to the exact SID only for the workspace, Pi configuration, and staged runtime, assigns the suspended process to a kill-on-close Job Object, and then starts it. A named pipe in the AppContainer namespace reaches a trusted host broker pinned to the configured provider host and port.

### Troubleshooting

- If the probe reports `AppContainer non utilizzabile`, rerun `doctor` as the same user that will launch the benchmark and check access to the workspace, Pi directory, and Pi installation.
- If Pi does not start, first verify `pi --version` and `py -3 benchmark.py doctor` in the same shell; check `ollama list` or the selected provider's model catalog too.
- During or after an error, inspect `.benchmark-scratch/windows-sandbox.json` in the task workspace. It contains cleanup state, broker phases, and byte counts, never provider payloads.
- The profile and ACEs are removed on a best-effort basis. After an abnormal exit, retain the metadata and diagnose any residue before deleting it manually.
- If `required` fails, do not describe the run as sandboxed or compare it with enforced runs.
