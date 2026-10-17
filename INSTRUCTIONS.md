# User Manual – LocalAgent Benchmark

## 1. Purpose

LocalAgent Benchmark compares local Ollama models acting as coding agents through Pi. Every model receives inputs copied from the same frozen snapshot of `AGENTS.md`, the case manifest, prompt, and Git fixture. Independent checks score the resulting workspace, while raw artifacts remain available for human review.

## 2. Requirements

- Python 3.10+ and Git on `PATH`;
- Ollama running on the configured loopback endpoint;
- Pi available as the `pi` command (every version must pass the local compatibility test);
- one or more downloaded Ollama models;
- enough disk space for one fixture workspace per attempt.

Optional OS enforcement requires a usable `sandbox-exec` on macOS; `bwrap`, `unshare`, and usable user/network namespaces on Linux; or Windows 10/11 with AppContainer. `doctor` performs a real probe and reports availability, the effective backend, and its capabilities without installing components. Platform-specific procedures are in [QUICK-START_Linux.md](QUICK-START_Linux.md) and [QUICK-START_Windows.md](QUICK-START_Windows.md).

Verify the environment without running an agent task:

```bash
python3 benchmark.py doctor
```

The command reports versions, model thinking capabilities and preliminary compatibility, and verifies that `AGENTS.md`, `.gitignore`, manifests, prompts, fixtures, graders, and optional rubrics are clean relative to Git. Definitive compatibility still requires the run preflight.

`doctor` and every benchmark start send three synthetic requests through the configured Pi command to a temporary `127.0.0.1` server: thinking off, thinking `medium`, and a provider error. The check inspects payloads, events, and retries without contacting Ollama. It uses disabled tools, `--offline`, isolated directories, and the selected sandbox. `defaults.pi_contract_timeout_seconds` controls each request (default 30 seconds; allowed 10–300). The GUI reports the result during discovery and lets you cancel it; each CLI phase repeats the check. Results retain only status and a diagnostic code, never probe prompts or responses. The model-specific Ollama thinking preflight remains mandatory.

## 3. First run

List profiles, cases, and models:

```bash
python3 benchmark.py list
```

Start with one small model and the smoke profile:

```bash
python3 benchmark.py run --profile smoke --models qwen3.5:9b-Q4_K_M --thinking off
```

Then compare all installed models with the standard profile:

```bash
python3 benchmark.py run --profile standard
```

## 4. Main workflows

### Command-free guided quick path

Double-click `launchers/LocalAgent-Benchmark.command` on macOS, `launchers\LocalAgent-Benchmark.cmd` on Windows, or `launchers/LocalAgent-Benchmark.sh` on Linux. The window performs the equivalent of `doctor`, detects local Ollama models, lets you select participants and sort them by name, size, or thinking from the column headings, and shows effective settings before asking for confirmation.

Use the **Thinking** toggle to select `off` (off) or `medium` (on), and the **Sandbox** toggle to select `audit` without OS isolation (off) or `required` (on). `required` stops before a run when no applicable OS backend is available. The choices apply to every stage and are recorded in `guided-run.json`; they are not saved as permanent preferences. The dashboard's **Task details** lists models excluded at preflight for thinking observed with `off` or after workspace/network boundary violations separately from executed tasks. It shows the effective sandbox backend; exclusion alone does not prove an OS-level block.

The funnel runs `smoke` on every selected model, consumes the official leaderboard order to promote up to four rankable models to `standard`, then up to two to `full`. A model with a failed task is excluded without stopping the others when the stage is complete and verifiable; a partial or incompatible stage still stops the funnel. The official dashboard then opens on the three distinct runs. The path never runs `showcase` or `results_dashboard`.

**Cancel** asks for confirmation, terminates the process tree, and retains diagnostic artifacts. Interrupted sessions are not resumed; fix the issue and create a new session. **Reopen dashboard** reuses one to three available runs from the latest session without rerunning models, including after restarting the GUI. Duration is not guaranteed. See [QUICK-START_Guided.md](QUICK-START_Guided.md) for platform behavior, configuration, troubleshooting, and privacy.

- `smoke` checks Pi/Ollama integration and basic tool calling.
- `standard` covers a targeted patch, security hardening, validated configuration/i18n, and the exact multi-constraint `thinking_challenge` case.
- `full` adds milestone closure, versioning, documentation, and Git discipline.
- `thinking` independently runs only `thinking_challenge` for focused A/B experiments.
- `showcase` is a separate final that asks shortlisted models to build a static dashboard from the same frozen dataset; do not mix it into earlier profiles.

### Focused thinking experiment

`thinking_challenge` requires an exact planner covering budget, risk, team capacities, dependencies, conflicts, required categories, and deterministic tie-breaking. Its grader uses alternative scenarios absent from the fixture and never asks for or rewards a chain-of-thought trace.

Run the independent `thinking` profile in separate `off` and `medium` directories with the same models, seed, parameters, and at least three repetitions per cell:

```bash
python3 benchmark.py run --profile thinking --models MODEL --thinking off --repetitions 3 --seed 20260919 --output results/thinking-off
python3 benchmark.py run --profile thinking --models MODEL --thinking medium --repetitions 3 --seed 20260919 --output results/thinking-medium
```

Counterbalance cohort order across larger campaigns. Never grant the second mode only to failures: timeouts, errors, and below-threshold scores remain outcomes of their cohort. `compare` intentionally refuses to aggregate different thinking modes.

Use `--models` for exact Ollama model names, `--cases` for explicit case IDs, `--timeout` for a per-task limit in seconds, and `--output` for a new or empty destination. `--thinking` accepts `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max` and overrides the default without fallback. Tasks are randomized; pass `--seed NUMBER` to reproduce the exact order recorded in `run.json`. `--sandbox` accepts `audit`, `auto`, or `required`; use `required` when the run must not continue without OS enforcement. Run the full profile three times on shortlisted models when making a final choice.

### Thinking control

The official benchmark uses `--thinking off`. Before any case runs, the runner queries `/api/show` for each model and sends a minimal request to `/v1/chat/completions` with `reasoning_effort: "none"`. Isolated Pi configuration contains the same explicit parameter, `max_tokens`, disabled HTTP idle timeout, and zero retries; native warmup uses `think: false`. `--no-warmup` disables only the optional extra warmup, never the mandatory preflight.

A rejected or unverifiable preflight excludes that model before its tasks without stopping other models. In an `off` cohort, observable reasoning or an unexpected retry during any task disqualifies the entire model. The probe stores only status, duration, and counts—never reasoning content. Active modes require the `thinking` capability and an observable reasoning signal and must run in distinct directories/cohorts. Do not grant a second mode only to failed models: an `off`/`medium` comparison must give every participant both modes under symmetric conditions.

In exports and the official dashboard, `thinking` and `showcase` remain independent profiles: they are filterable and show their thinking mode/control, but they are not stages in the `smoke` → `standard` → `full` funnel. Rankings from `off` and `medium` runs are grouped separately instead of being merged into a combined rank.

Compare compatible runs statistically:

```bash
python3 benchmark.py compare results/RUN-1 results/RUN-2 results/RUN-3
```

The command accepts only distinct directories and runs with matching versions/parameters, profiles, cases, input fingerprints, model digests/capabilities, thinking control, retry policy, idle timeout, Pi/Ollama versions, sandbox backend, platform, and recorded hardware. Legacy runs remain readable as `thinking_control: unverified` but are not aggregated with verified runs. It writes `comparison.json` and `COMPARISON.md` with mean, median, standard deviation, and an approximate 95% interval bounded to each metric's natural domain. Missing or integrity-disqualified models receive no sample for that run.

### Dashboard dataset and showcase

Verify the system without a real Pi/Ollama benchmark:

```bash
python3 -m unittest tests.test_dashboard_data -v
python3 benchmark.py case validate results_dashboard
```

After the real runs, aggregate different profiles with the dedicated command, not with `compare`:

```bash
python3 benchmark.py dashboard-data \
  results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN \
  --output results/finalists-dashboard-data.json
```

The command accepts schema 2, 3, or 4 `run.json` and `report.json` files, capped at 32 MiB each. It emits dashboard schema 3 while continuing to read schema-1 and schema-2 datasets. A strict whitelist retains the profile, sandbox, summarized integrity and thinking-control status, participants, leaderboards, task metrics, exclusion reason codes and optional case IDs, hashes, and commit provenance. Legacy runs are marked unverified; detailed preflights and reasoning content are never exported. Paths, prompts, responses, commands, logs, violation evidence, and free-form errors are excluded. Inputs and output must remain under the project root, and output cannot be written inside a source run. Add `--force` only to atomically replace a reviewed output.

Review the JSON, then freeze it in the fixture:

```bash
python3 benchmark.py dashboard-data \
  results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN \
  --output cases/results_dashboard/fixture/dashboard-data.json \
  --force
python3 benchmark.py case validate results_dashboard
```

After successful validation, inspect and commit only the frozen fixture:

```bash
git status --short
git diff -- cases/results_dashboard/fixture/dashboard-data.json
git add -- cases/results_dashboard/fixture/dashboard-data.json
git diff --cached --name-only
git diff --cached --check
git commit -m "test: freeze showcase finalist dataset"
git status --short
```

Before committing, `git diff --cached --name-only` must list only `cases/results_dashboard/fixture/dashboard-data.json`, unless other intentional changes have already been reviewed. Do not use `git add .`. The final check must show no remaining modifications to `AGENTS.md`, `.gitignore`, or the case inputs; review and commit any intentional plan or documentation changes separately. A push is not required for a local run; use `git push` on the current branch only when the commit must be shared or CI triggered.

Then run only the finalists with `python3 benchmark.py run --profile showcase --models MODEL-A MODEL-B --thinking off --sandbox required`. The showcase uses the same capability discovery, preflight, and task-level thinking checks as every other profile. Every finalist receives the same snapshot. The 100-point technical grader uses an additional hidden dataset; the 20-point visual rubric remains separate and manual. See [QUICK-START_Showcase.md](QUICK-START_Showcase.md) for local startup, multi-file import, and browser review.

The showcase remains a valid test even when no model exceeds 60/100. Preserve timeouts, errors, below-threshold scores, and unchanged baselines as negative outcomes; do not alter the dataset or grader to obtain a completed dashboard. Manual review may assign `0/20` or record “not applicable” when no functional interface exists, without changing the automatic score.

### Official results dashboard

The official dashboard under `dashboard/` is the stable viewer maintained by the project; it is separate from dashboards produced by models during the showcase. Start it from the repository root to view compatible runs directly below `results/`:

```bash
python3 dashboard.py
```

The command aggregates valid runs in memory, starts a server on `127.0.0.1` using an available port, opens the browser, and prints the URL. It never serves raw result files or modifies source runs. Stop it with `Ctrl+C`. If no compatible run exists, it serves the reviewed dashboard fixture in memory.

The **Efficiency map** shows, separately for every run and thinking mode, `quality_score` against median duration and against median output tokens. Horizontal axes are logarithmic: moving left means using less time or fewer tokens, while moving up means higher quality. Point numbers map to the legend below; filled, cyan, and hollow points respectively indicate 100%, partial, and zero completion. Hover over a point or reach it with `Tab` to read the complete values. Do not interpret separate cohorts as one combined experiment.

Select sources and launcher behavior explicitly when needed:

```bash
python3 dashboard.py results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN
python3 dashboard.py --dataset results/finalists-dashboard-data.json
python3 dashboard.py --no-open --port 8765
```

- positional paths must identify distinct run directories inside the project root;
- `--dataset` accepts one already-sanitized `dashboard-data` export and cannot be combined with run directories;
- `--no-open` leaves browser startup to you; open the printed URL;
- port `0`, the default, selects an available port; an occupied fixed port returns a clear error.

The page's **Choose files** control accepts only one or more compatible `dashboard-data.json` files. Do not choose `run.json`, `report.json`, a directory, `REPORT.md`, `result.json`, logs, or other raw artifacts. Create a compatible file with:

```bash
python3 benchmark.py dashboard-data \
  results/SMOKE-RUN results/STANDARD-RUN results/FULL-RUN \
  --output results/finalists-dashboard-data.json
```

Import stays in the browser tab's memory: no file is uploaded or committed. Reloading returns to the initial source. Language and theme are the only preferences stored in browser `localStorage`. An optional `file://` snapshot can be generated with `python3 dashboard.py --refresh-snapshot --force`; it is ignored by Git and must never be committed. See [QUICK-START_Dashboard.md](QUICK-START_Dashboard.md) for the complete short workflow.

### Project landing page

The public landing page is maintained under `site/` and is published at `https://gloutchov.github.io/LocalAgentBenchmark/`. Preview it from the repository root with:

```bash
python3 -m http.server 8000 --bind 127.0.0.1 --directory site
```

Open `http://127.0.0.1:8000/` and stop the server with `Ctrl+C`. The page introduces the purpose, criteria, profiles, methodology, controls, official dashboard, and quick start. Its buttons navigate explicitly to the repository, latest release, documentation, and project owner's website. It is not the results dashboard and never reads `results/` directories.

The initial language follows the browser: Italian for Italian locales and English otherwise. The selector provides a manual override. Theme can be automatic, light, or dark. Only these two preferences are stored in `localStorage`; the page has no cookies, forms, analytics, or telemetry. Every runtime asset is local. External links perform a normal navigation only when activated.

When maintaining the page, update both dictionaries in `site/js/i18n.js`, keep paths compatible with the `/LocalAgentBenchmark/` prefix, and verify images, alternative text, the 404 page, links, and metadata. Published images under `site/assets/` are optimized, reviewed frames; `assets/Dashboard.mov` remains a local Git-ignored source and must not be published. Run the checks listed in the README and complete a desktop/mobile browser review before every deployment.

## 5. Configuration

`benchmark.json` is the central configuration file. It defines the Ollama URL, Pi command, model selection, task/preflight timeouts, repetitions, thinking level, HTTP idle timeout, agent/provider retries, warmup, context and output limits, temperature, sandbox mode, profiles, the in-repository case discovery directory, and official dashboard paths, loopback host, port, and browser behavior. Its `guided` section fixes the required `smoke`, `standard`, `full` progression, descending `4`, `2` promotion limits, and the local GUI preference file; guided profiles cannot include `results_dashboard`. Official defaults are thinking `off`, HTTP idle timeout `0`, and zero retries. Each `cases/<id>/case.json` holds bilingual titles, category, weight, and relative input paths.

Configuration is validated at startup. It must not contain secrets. The generated Ollama provider uses the literal dummy key `ollama`, which the local server ignores.

### Creating and validating personal cases

Create a self-contained scaffold:

```bash
python3 benchmark.py case create api_contract \
  --title-it "Contratto API" \
  --title-en "API contract" \
  --category architecture \
  --weight 1.25 \
  --manual-rubric
```

The command creates `case.json`, `prompt.md`, `fixture/`, `grader.py`, and, when requested, `manual-rubric.md`. Metadata and weight live in the manifest, so core code does not need modification. Add the ID to a `benchmark.json` profile only when it should become a permanent member of that group.

After replacing the examples with synthetic inputs and observable checks, validate the case:

```bash
python3 benchmark.py case validate api_contract
```

Without IDs, `case validate` checks every discovered case. It validates structure, confined paths, required files, the grader JSON contract, exactly 100 allocated points, and an initial score below 60. The grader executes with the user's permissions outside the agent sandbox; always review imported grader code before validation. See [QUICK-START_Case-Author.md](QUICK-START_Case-Author.md) for the full author workflow.

## 6. Reading results

The composite score weighs quality at 80%, completion at 10%, relative speed at 5%, and relative token efficiency at 5%. A task counts as complete when Pi exits normally and its grade is at least 60/100.

Read **Environment and isolation** and **Run integrity** before the leaderboard. The former distinguishes the requested and effective backend and never labels a fallback as sandboxed. The audit follows `$PWD` and `cd` across multiline commands: a `../` path that remains inside the workspace, such as internal scratch, is not a violation. A model is entirely disqualified if it explicitly references a path resolved outside its workspace, attempts network access, mutates the benchmark repository or frozen snapshot, or receives a divergent baseline. Snapshot mutation also aborts the remaining matrix. The report lists model, case, repetition, reason, target, and evidence; `run.json` records hardware, sandbox, Git provenance, seed, task order, input and policy hashes, and violations. Each `result.json` records its baseline tree, audit version, system metrics, and original details.

- Prioritize quality and the cases closest to your real work.
- Use median duration to estimate day-to-day waiting time.
- Tool errors reveal model/provider tool-calling problems.
- Score standard deviation becomes useful after at least three repetitions.
- Treat RAPL energy as a host-wide measurement: compare it only on the same machine under similar load.
- Inspect the patch and final workspace for top-ranked models.
- Complete `manual-rubric.md` separately when present; it never changes the automatic score.

The overall winner is not necessarily best for every activity. A security-heavy workflow may favor the best `secure_workspace` score, while ordinary maintenance may favor `targeted_patch`.

## 7. Reproducibility

Use the same configuration, profile, thinking mode, repetitions, seed, hardware, and similar system load. The runner unloads each model around its separate preflight; at each task-model switch it may then record an optional warmup before starting the task. Preflight and warmup never contribute to task time or tokens. Selected manifests, prompts, fixtures, graders, and rubrics must be clean at startup; only tracked files and the execution policy are copied once into `benchmark-context/`, excluding ignored caches and outputs. Input hashes include the manifest and optional rubric. Every workspace contains a Git-ignored `.benchmark-scratch/` directory also used for `TMPDIR`, `TMP`, and `TEMP`; models must use it for smoke tests and temporary files instead of `/tmp`. Do not modify source inputs or the snapshot during a run. Temperature zero reduces but does not eliminate variance.

## 8. Troubleshooting

- `Ollama non raggiungibile`: start Ollama and check `ollama list`.
- Guided GUI has no models or prerequisites: start Ollama or install Pi, then choose **Detect again**; review and commit dirty protected inputs rather than bypassing the preflight.
- Guided path stopped: inspect `results/guided-*/guided-run.json` and existing stage runs; partial data is never promoted and earlier runs are never deleted.
- Guided dashboard failed to start: resolve the local issue and use **Reopen dashboard**; completed run data is not regenerated.
- `pi: command not found`: install Pi or update `pi.command`.
- Missing model: use the exact name shown by `doctor`.
- Timeout: increase `--timeout` and inspect `stderr.log`.
- `pi_error`: inspect `pi-events.jsonl` and `stderr.log`; a terminal agent/provider failure is operational even when the Pi process exits with code zero. Free-form error text remains in local artifacts and is not exported by `dashboard-data`.
- Low score with a successful exit: inspect `grade.json`; the model may have answered without editing or missed a constraint.
- Zero usage tokens: some model/provider combinations omit usage; quality remains valid, while token efficiency receives no credit.
- `Input benchmark modificati`: restore or intentionally commit the listed benchmark inputs before rerunning.
- `Manifesto mancante` or `paths.*`: complete `case.json`, use only POSIX-style relative paths inside the case, remove symlinks from declared paths, and rerun `case validate`.
- `max_score`, `points`, `earned`, or baseline errors: repair the grader contract; checks must total 100 and the starting fixture must remain below 60.
- `Controllo compatibilità Pi fallito`: inspect the failed check, configured Pi command, and selected sandbox; Pi 0.85.1 is the verified reference version but may not resolve unrelated problems.
- `thinking_control_unverified`: inspect capabilities, preflight status, Ollama version, and support for the requested level; never force a fallback.
- `unexpected_thinking` or `unexpected_retry`: retain the evidence, exclude the model, and correct the control before a new run.
- `dashboard-data` error: verify schema 2/3/4, consistent profiles, distinct directories, and paths inside the project root; use `--force` only after reviewing the file being replaced.
- Dashboard shows no data when opening `index.html` directly: run `python3 dashboard.py`, or explicitly generate the optional local snapshot first.
- No local dashboard runs: each immediate directory under `results/` must contain compatible `run.json` and `report.json`, or pass explicit run directories.
- Dashboard port is occupied: omit `--port`, use `--port 0`, or select another number.
- Browser does not open: run `python3 dashboard.py --no-open` and open the printed URL manually.
- **Choose files** rejects the file: generate and select `dashboard-data.json`, not `run.json` or `report.json`; each file is capped at 32 MiB.
- `violations_detected`: read **Detected violations**, then inspect `report.json`, `run.json`, and the corresponding `pi-events.jsonl`; do not manually restore the disqualified model to the leaderboard. Regenerating a report applies the current audit to older events without changing their original `result.json` files.
- `snapshot_compromised`: preserve the diagnostic artifacts, fix the cause, and start a new run.
- `Sandbox OS richiesta ma non disponibile`: install or enable the backend reported by `doctor`, deliberately use `--sandbox auto` to permit fallback, or choose `--sandbox audit` for the historical behavior.
- `linux-bubblewrap` unavailable: check `bwrap`, `unshare`, and the user-namespace policy using the Linux quick start; do not run the benchmark as root to bypass the probe.
- `windows-appcontainer` unavailable: run `doctor` as a standard user and check ACL, AppContainer profile, and named-pipe diagnostics using the Windows quick start.

The runner exits with code `1` when one or more tasks end in an error or timeout, the event stream ends with an agent/provider error, or integrity is not valid, while still writing the available report. A low grade with status `ok` and integrity `ok` is a valid negative model result and does not fail the command.

## 9. Security and privacy

Do not add private data, real repositories, or credentials to cases. Manifests and templates do not grant trust: an imported grader remains untrusted until reviewed because validation and grading execute it on the host. `audit` and the `auto` fallback are not sandboxes. The guided flow uses structured arguments without a shell, accepts local Ollama only, keeps its manifest/results inside the project root, and asks for confirmation before start and cancellation; `results/` remains potentially sensitive. The macOS backend restricts external user files and networking except Ollama loopback and relies on the deprecated `sandbox-exec` interface. On Linux, Pi runs in an empty network namespace and reaches only the Ollama broker through a Unix socket inside the workspace. On Windows, AppContainer receives no network capabilities and uses a named pipe dedicated to its SID; temporary ACLs grant only required paths, and a Job Object terminates descendants. Brokers and graders remain trusted host processes outside the sandbox. The dashboard export omits raw content but retains model names, titles, metrics, and hashes; it remains potentially sensitive local data and must not be published automatically. The official server is bound to `127.0.0.1` and serves only allowlisted assets plus the public in-memory dataset, but other local processes and browser extensions remain outside its trust boundary. Read `SECURITY_MODEL.md` before extending the benchmark.

## 10. Known limitations

- Automatic graders cannot fully judge code taste or explanation quality.
- Manual rubrics are review aids; the runner does not collect or aggregate human scores.
- Timing depends on hardware, quantization, memory pressure, and thermals.
- The runner currently targets Ollama and does not include a Codex control adapter.
- Synthetic tasks should evolve with your actual workflow.
- The Linux backend depends on unprivileged user/network namespaces; restrictive kernel or AppArmor policies make its probe fail, and `required` then stops the run.
- AppContainer grants read access to the Pi runtime and applies/removes ACLs and its profile on a best-effort basis; an abnormal launcher exit may require manual cleanup or diagnosis.
- The broker forwards only to the configured Ollama destination, but it does not authenticate or semantically filter request content.
- Dynamic or obfuscated commands may still evade the audit when no enforced backend is active.
- `sandbox-exec` is deprecated and may disappear from future macOS versions; `required` prevents silent fallback.
- POSIX child metrics may not fully include every descendant; RAPL is host-wide and may be unreadable without additional privileges.
- The dashboard grader checks transformations and observable requirements, but responsive behavior, visual rendering, keyboard use, and absence of remote requests still require a real-browser review and the manual rubric on each candidate workspace.
- The official dashboard does not anonymize or publish exports; review names, scores, and hashes before sharing a snapshot or `dashboard-data.json`.
- The preflight verifies observable endpoint behavior, not internal processes hidden by Ollama or the model. An active model that exposes no reasoning signal is excluded as unverifiable.
- Guided launchers are source scripts rather than signed installers or native apps; Linux double-click behavior depends on the file manager, and the Python distribution must include Tkinter.
- A cancelled or failed guided session is preserved but cannot resume from its interrupted stage; the dashboard can still reopen one to three available runs without starting a new benchmark.
