"""Direct-provider preliminary execution after the ordinary runner gates."""
from __future__ import annotations

import random
import signal
import threading
from contextlib import contextmanager
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .integrity import changed_paths, repository_fingerprints, verify_snapshot
from .preliminary_stream import measure
from .preliminary_suite import grade_answer, load_suite


PRELIMINARY_POLICY = """
## Preliminary direct-provider probes
Only frozen synthetic prompts may be sent to the configured loopback endpoint.
No tools, generated-code execution, remote endpoints, redirects, proxies, retries,
or reasoning persistence. HTTP probes execute on the host; the selected sandbox
protects the Pi contract probe only. Descriptive outcomes never affect ranking.
"""

@contextmanager
def interruptible():
    """Let POSIX guided cancellation unwind sockets and provider lifecycle."""
    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.getsignal(signal.SIGTERM)
        def interrupt(_signum, _frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def execute(config: Any, provider: Any, policy: Any, manifest: dict[str, Any],
            run_dir: Path, repository_state: dict[str, str], save: Callable[[], None]) -> None:
    options = config.preliminary
    initial_changes = verify_snapshot(run_dir / 'benchmark-context', manifest['inputs'])
    if initial_changes:
        manifest['integrity'].update(status='snapshot_compromised', aborted=True)
        manifest['preliminary'] = {'observations': [], 'contexts': ['short','long']}
        save()
        return
    suite = load_suite(run_dir / 'benchmark-context' / 'extra-0.json')
    randomizer = random.Random(manifest['order_seed'])
    models = list(manifest['models'])
    randomizer.shuffle(models)
    probes = [(p, r, p['id']) for p in suite['performance'] for r in range(1, manifest['repetitions']+1)]
    probes += [(p, 1, 'grounding') for p in suite['questions']]
    randomizer.shuffle(probes)
    excluded = set(manifest['thinking_control']['disqualified_models'])
    settings = asdict(options)
    settings['suite'] = options.suite.relative_to(config.root).as_posix()
    manifest['preliminary'] = {'version': 1, 'settings': settings,
        'contexts': [p['id'] for p in suite['performance']], 'model_order': models,
        'disqualified_models': sorted(excluded),
        'probe_order': [{'id':p['id'],'repetition':r,'context':c} for p,r,c in probes],
        'context_window_requested': config.defaults.context_window,
        'context_window_verification': 'not_observable',
        'cache_policy': 'unique_seeded_prefix_fresh_conversation; runtime_cache_uncontrolled',
        'state': 'post_preflight; no_verified_cold_start',
        'scope': 'host HTTP probes without tools; sandbox applies to Pi contract gate',
        'retries': 0, 'observations': [], 'lifecycle': []}
    data = manifest['preliminary']

    def violation(model: str, kind: str, paths: list[str]) -> None:
        excluded.add(model)
        manifest['integrity']['status'] = 'violations_detected'
        manifest['integrity']['violations'].append({'model':model,'case_id':'__preliminary__','repetition':0,'kind':kind,'details':[{'paths':paths}]})
        data['disqualified_models'] = sorted(excluded)
        if kind == 'thinking_observed_off':
            manifest['thinking_control']['disqualified_models'] = sorted(set(manifest['thinking_control']['disqualified_models']) | {model})

    def verify(model: str) -> bool:
        snapshot = verify_snapshot(run_dir/'benchmark-context', manifest['inputs'])
        if snapshot:
            violation(model, 'snapshot_changed', snapshot)
            manifest['integrity'].update(status='snapshot_compromised', aborted=True)
            return False
        paths = changed_paths(repository_state, repository_fingerprints(config.root,(run_dir,)))
        if paths:
            violation(model, 'source_repository_changed', paths)
            manifest['integrity']['aborted'] = True
            return False
        return True

    save()
    count = 0
    for model in models:
        if model in excluded:
            continue
        try:
            if not verify(model):
                break
            provider.unload(model)
            data['lifecycle'].append({'model':model,'event':'unload_before','status':'not_supported' if provider.kind == 'unsloth' else 'ok'})
            if provider.explicit_load:
                load_started = time.monotonic()
                provider.load(model, timeout=options.timeout_seconds)
                manifest["load_events"].append({"model":model,"status":"preloaded" if provider.kind == 'unsloth' else "loaded","scope":"preliminary","duration_ms":round((time.monotonic()-load_started)*1000)})
                data['lifecycle'].append({'model':model,'event':'load','status':'preloaded' if provider.kind == 'unsloth' else 'ok'})
            if manifest['warmup']:
                metrics = provider.warmup(model,policy,timeout=options.timeout_seconds,context_window=config.defaults.context_window)
                safe_metrics = {key:metrics.get(key) for key in ("total_duration","load_duration","prompt_eval_count","eval_count","eval_duration") if type(metrics.get(key)) in (int,float)} if isinstance(metrics,dict) else {}
                manifest['warmup_events'].append({'model':model,'status':'ok','scope':'preliminary','metrics':safe_metrics})
            for probe, repetition, context in probes:
                if not verify(model):
                    break
                count += 1
                print(f"[{count}/{len(models)*len(probes)}] {model} · {probe['id']} · r{repetition}",flush=True)
                row = {'model':model,'id':probe['id'],'repetition':repetition,'context':context,'status':'error'}
                if context == 'grounding':
                    row['category'] = probe['category']
                try:
                    prompt = f"Probe instance {manifest['order_seed']}-{probe['id']}-{repetition}.\n" + probe['prompt']
                    result = measure(config.ollama_url,model,prompt,policy,options,
                                     temperature=config.defaults.temperature,seed=manifest['order_seed'] % (2**31))
                    if not policy.active and result['thinking_observed']:
                        violation(model,'thinking_observed_off',[])
                    row.update(result,status='ok')
                    if context == 'grounding':
                        row['verdict'] = 'invalid' if result['truncated'] else grade_answer(result['answer'],probe)
                    # Performance output is unnecessary evidence. Never persist reasoning.
                    if context != 'grounding':
                        row.pop('answer',None)
                except Exception as exc:
                    row['error_type'] = type(exc).__name__  # no provider text or traceback
                data['observations'].append(row)
                valid = verify(model)
                save()
                if not valid or model in excluded:
                    break
        except Exception as exc:
            data['lifecycle'].append({'model':model,'event':'prepare','status':'error','error_type':type(exc).__name__})
            violation(model,'provider_load_failed',[])
        finally:
            try:
                provider.unload(model)
                data['lifecycle'].append({'model':model,'event':'unload_after','status':'not_supported' if provider.kind == 'unsloth' else 'ok'})
            except Exception as exc:
                data['lifecycle'].append({'model':model,'event':'unload_after','status':'error','error_type':type(exc).__name__})
                violation(model,'provider_unload_failed',[])
            verify(model)
            save()
        if manifest['integrity']['aborted']:
            break
    thinking_excluded = manifest['thinking_control']['disqualified_models']
    manifest['thinking_control']['status'] = 'failed' if len(thinking_excluded) == len(models) else 'partial' if thinking_excluded else 'passed'
