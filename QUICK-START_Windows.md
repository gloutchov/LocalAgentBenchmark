# Avvio rapido Windows / Windows Quick Start

## Italiano

### Requisiti

- Windows 10 o 11;
- Python 3.10+, Git, Pi compatibile e Ollama già configurati;
- un modello Ollama già scaricato;
- esecuzione come utente standard, con permesso di creare un profilo AppContainer e modificare temporaneamente le ACL dei path del run.

AppContainer è incluso in Windows: non occorre installare un pacchetto sandbox. Non avviare il benchmark da una shell elevata salvo diagnosi amministrativa esplicita.

### Verifica e smoke test

In PowerShell:

```powershell
py -3 benchmark.py doctor
py -3 benchmark.py run --profile smoke --models NOME_MODELLO --thinking off --sandbox required
```

`doctor` deve verificare Pi sul server sintetico locale, incluso lo staging AppContainer, e accettare una versione compatibile e riportare `windows-appcontainer` con isolamento filesystem, processi e rete. Prima della task, il preflight deve inoltre confermare `reasoning_effort: "none"`; `--no-warmup` non lo disabilita. In `required`, un probe fallito interrompe il run prima delle task. `auto` consente invece un fallback registrato e `audit` applica soltanto policy e rilevamento.

Il launcher crea un profilo AppContainer senza capability di rete, prepara una copia per-task dei runtime Pi/Node/Python, configura nella copia il tool shell di Pi su `cmd.exe`, concede ACL temporanee al SID esatto soltanto per workspace, configurazione Pi e runtime staged, assegna il processo sospeso a un Job Object kill-on-close e poi lo avvia. Un named pipe nel namespace AppContainer raggiunge un broker host vincolato all'host e alla porta Ollama configurati.

### Risoluzione problemi

- Se il probe segnala `AppContainer non utilizzabile`, rieseguire `doctor` come lo stesso utente che lancerà il benchmark e controllare che workspace, directory Pi e installazione Pi siano accessibili.
- Se Pi non parte, verificare prima `pi --version` e `ollama list` nella stessa shell.
- Durante o dopo un errore, consultare `.benchmark-scratch/windows-sandbox.json` nella workspace della task. Contiene stato di cleanup, fasi del broker e conteggi byte, non i payload Ollama.
- Profilo e ACE vengono rimossi in best effort. Dopo un arresto anomalo, conservare i metadata e diagnosticare l'eventuale residuo prima di cancellarlo manualmente.
- Se `required` fallisce, non descrivere il run come sandboxed e non confrontarlo con run enforced.

## English

### Requirements

- Windows 10 or 11;
- Python 3.10+, Git, Pi compatibile, and Ollama already configured;
- at least one downloaded Ollama model;
- a standard-user session allowed to create an AppContainer profile and temporarily update ACLs on run paths.

AppContainer is built into Windows; no sandbox package is required. Do not launch the benchmark from an elevated shell except for explicit administrative diagnosis.

### Verification and smoke test

In PowerShell:

```powershell
py -3 benchmark.py doctor
py -3 benchmark.py run --profile smoke --models MODEL_NAME --thinking off --sandbox required
```

`doctor` must test Pi on the local synthetic server, including AppContainer staging, and accept a compatible version and report `windows-appcontainer` with filesystem, process, and network isolation. Before the task, preflight must also confirm `reasoning_effort: "none"`; `--no-warmup` does not disable it. In `required` mode, a failed probe stops before any task. `auto` permits a recorded fallback, while `audit` applies policy and detection only.

The launcher creates an AppContainer profile without network capabilities, prepares per-task copies of the Pi/Node/Python runtimes, configures Pi's staged shell tool to use `cmd.exe`, grants temporary ACLs to the exact SID only for the workspace, Pi configuration, and staged runtime, assigns the suspended process to a kill-on-close Job Object, and then starts it. A named pipe in the AppContainer namespace reaches a trusted host broker pinned to the configured Ollama host and port.

### Troubleshooting

- If the probe reports `AppContainer non utilizzabile`, rerun `doctor` as the same user that will launch the benchmark and check access to the workspace, Pi directory, and Pi installation.
- If Pi does not start, first verify `pi --version` and `ollama list` in the same shell.
- During or after an error, inspect `.benchmark-scratch/windows-sandbox.json` in the task workspace. It contains cleanup state, broker phases, and byte counts, never Ollama payloads.
- The profile and ACEs are removed on a best-effort basis. After an abnormal exit, retain the metadata and diagnose any residue before deleting it manually.
- If `required` fails, do not describe the run as sandboxed or compare it with enforced runs.
