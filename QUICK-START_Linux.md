# Avvio rapido Linux / Linux Quick Start

## Italiano

### Requisiti

- Python 3.10+, Git, Pi compatibile e Ollama già configurati;
- `bubblewrap` (`bwrap`) e `unshare` da util-linux;
- user namespace e network namespace non privilegiati consentiti dalla policy dell'host;
- un modello Ollama già scaricato.

Su Debian/Ubuntu i componenti OS si installano normalmente con:

```bash
sudo apt install bubblewrap util-linux
```

L'elevazione serve soltanto all'installazione amministrativa. Eseguire benchmark, Pi e Ollama come utente standard; non usare `sudo` per aggirare un probe fallito.

### Verifica e smoke test

```bash
python3 benchmark.py doctor
python3 benchmark.py run --profile smoke --models NOME_MODELLO --thinking off --sandbox required
```

`doctor` deve verificare Pi sul server sintetico locale e accettare una versione compatibile e riportare `linux-bubblewrap` con isolamento filesystem, processi e rete. Prima della task, il preflight deve inoltre confermare `reasoning_effort: "none"`; `--no-warmup` non lo disabilita. In `required`, un probe fallito interrompe il run prima delle task. `auto` consente invece un fallback registrato e `audit` applica soltanto policy e rilevamento.

Il backend avvia Pi in un user/network namespace nuovo, usa bubblewrap per montare read-only i runtime necessari e read-write soltanto workspace e configurazione Pi, e non configura interfacce di rete. Uno Unix socket dentro `.benchmark-scratch/` raggiunge un broker host che inoltra esclusivamente all'host e alla porta Ollama configurati.

### Risoluzione problemi

- Se manca un comando, verificare `command -v bwrap` e `command -v unshare`.
- Se `unshare` restituisce `Operation not permitted`, la policy kernel, container o AppArmor dell'host impedisce il backend. Non indebolirla in modo permanente senza approvazione amministrativa: usare un host approvato oppure scegliere consapevolmente `auto`/`audit` con fixture soltanto sintetiche.
- Se Ollama non risponde, verificarlo prima fuori dal benchmark con `ollama list`, poi ricontrollare `benchmark.json`.
- Se `required` fallisce, conservare l'errore di `doctor`: non descrivere il run come sandboxed e non confrontarlo con run enforced.

## English

### Requirements

- Python 3.10+, Git, Pi compatibile, and Ollama already configured;
- `bubblewrap` (`bwrap`) and util-linux `unshare`;
- unprivileged user and network namespaces allowed by host policy;
- at least one downloaded Ollama model.

On Debian/Ubuntu, install the OS components with:

```bash
sudo apt install bubblewrap util-linux
```

Elevation is needed only for administrative installation. Run the benchmark, Pi, and Ollama as a standard user; do not use `sudo` to bypass a failed probe.

### Verification and smoke test

```bash
python3 benchmark.py doctor
python3 benchmark.py run --profile smoke --models MODEL_NAME --thinking off --sandbox required
```

`doctor` must test Pi on the local synthetic server and accept a compatible version and report `linux-bubblewrap` with filesystem, process, and network isolation. Before the task, preflight must also confirm `reasoning_effort: "none"`; `--no-warmup` does not disable it. In `required` mode, a failed probe stops before any task. `auto` permits a recorded fallback, while `audit` applies policy and detection only.

The backend starts Pi in new user/network namespaces, uses bubblewrap to mount required runtime paths read-only and only the workspace and Pi configuration read-write, and configures no network interface. A Unix socket under `.benchmark-scratch/` reaches a trusted host broker pinned to the configured Ollama host and port.

### Troubleshooting

- If a command is missing, check `command -v bwrap` and `command -v unshare`.
- If `unshare` returns `Operation not permitted`, the host kernel, container, or AppArmor policy blocks the backend. Do not weaken it permanently without administrative approval; use an approved host or deliberately choose `auto`/`audit` with synthetic fixtures only.
- If Ollama does not answer, first check `ollama list` outside the benchmark, then review `benchmark.json`.
- If `required` fails, retain the `doctor` error: do not describe the run as sandboxed or compare it with enforced runs.
