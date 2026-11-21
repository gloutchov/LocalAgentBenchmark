"""Descriptive aggregates, deliberately independent from ranking and promotions."""
from __future__ import annotations

import math
import statistics
from typing import Any

METRICS = ('first_answer_seconds', 'duration_seconds', 'output_tokens_per_second',
           'decode_tokens_per_second', 'max_chunk_gap_seconds',
           'first_answer_min_seconds', 'first_answer_max_seconds',
           'output_tokens_min_per_second', 'output_tokens_max_per_second')
COUNTS = ('samples', 'completed', 'failed', 'truncated', 'known_total', 'known_correct',
          'missing_total', 'missing_correct', 'premise_total', 'premise_correct',
          'unsupported_answers', 'unnecessary_abstentions', 'invalid_answers')
FIELDS = {'model', 'context', 'status', *METRICS, *COUNTS}


def summarize(manifest: dict[str, Any], excluded: set[str]) -> list[dict[str, Any]]:
    if manifest.get('integrity', {}).get('aborted'):
        excluded = set(manifest.get('models', []))
    payload = manifest.get('preliminary', {})
    observations = payload.get('observations', [])
    rows = []
    for model in manifest.get('models', []):
        contexts = list(payload.get('contexts', ['short', 'long'])) + ['grounding']
        for context in contexts:
            items = [x for x in observations if x['model'] == model and x['context'] == context]
            ok = [x for x in items if x['status'] == 'ok']
            row = dict.fromkeys(METRICS)
            row.update(dict.fromkeys(COUNTS, 0))
            row.update(model=model, context=context, status='excluded' if model in excluded else 'measured' if ok else 'unavailable')
            row.update(samples=len(items), completed=len(ok), failed=len(items)-len(ok), truncated=sum(x.get('truncated', False) for x in ok))
            if model not in excluded:
                for metric in METRICS:
                    values = [x[metric] for x in ok if type(x.get(metric)) in (int,float) and math.isfinite(x[metric]) and x[metric] >= 0]
                    row[metric] = round(statistics.median(values), 6) if values else None
                for source, low, high in [('first_answer_seconds','first_answer_min_seconds','first_answer_max_seconds'),('output_tokens_per_second','output_tokens_min_per_second','output_tokens_max_per_second')]:
                    values = [x[source] for x in ok if type(x.get(source)) in (int,float) and math.isfinite(x[source]) and x[source] >= 0]
                    row[low], row[high] = (round(min(values),6), round(max(values),6)) if values else (None,None)
                for category, prefix in [('answer','known'),('unknown','missing'),('false_premise','premise')]:
                    selected = [x for x in items if x.get('category') == category]
                    row[prefix+'_total'] = len(selected)
                    row[prefix+'_correct'] = sum(x.get('verdict') == 'correct' for x in selected)
                for verdict, key in [('unsupported_answer','unsupported_answers'),('unnecessary_abstention','unnecessary_abstentions'),('invalid','invalid_answers')]:
                    row[key] = sum(x.get('verdict') == verdict for x in items)
            rows.append(row)
    return rows


def markdown(rows: list[dict[str, Any]]) -> str:
    lines = ['# Preliminary — reattività e affidabilità / responsiveness and grounding', '',
             'Misure descrittive, senza classifica o promozioni / Descriptive measurements, no ranking or promotion.',
             'Tempi e velocità: mediane; token/sec complessivi includono attesa e reasoning. Decode solo se dichiarato dal provider. Pause fra blocchi ricevuti, non fra singoli token. / Times and rates: medians; overall tokens/sec include waiting and reasoning. Decode only when supplied by the provider. Gaps are between received chunks, not individual tokens.',
             'Ogni campione grezzo è in run.json. N/D indica dati mancanti; gli esclusi non hanno metriche utilizzabili. / Raw samples are in run.json. N/A means missing data; excluded models have no usable metrics.', '',
             '| Modello / Model | Contesto / Context | Stato / Status | Campioni / Samples | Primo testo s / First answer s | Durata s / Duration s | Token/s E2E | Decode token/s | Pausa max s / Max gap s | Troncati / Truncated |',
             '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    def cell(value: Any) -> str:
        return str(value).replace('|','\\|').replace('\n',' ') if value is not None else 'N/D'
    for row in rows:
        lines.append('| '+' | '.join(cell(row[k]) for k in ('model','context','status','samples',*METRICS[:5],'truncated'))+' |')
    lines += ['', '| Modello / Model | Contesto / Context | Primo testo min–max s / First answer range s | Token/s E2E min–max |', '|---|---|---:|---:|']
    for r in rows:
        if r['context'] != 'grounding':
            lines.append(f"| {cell(r['model'])} | {cell(r['context'])} | {cell(r['first_answer_min_seconds'])}–{cell(r['first_answer_max_seconds'])} | {cell(r['output_tokens_min_per_second'])}–{cell(r['output_tokens_max_per_second'])} |")
    lines += ['', '| Modello / Model | Note corrette / Known correct | Mancanti riconosciute / Missing recognized | Premesse corrette / Premises corrected | Risposte non supportate / Unsupported | Astensioni inutili / Unnecessary abstentions | Non valutabili / Invalid |', '|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        if r['context'] == 'grounding':
            lines.append(f"| {cell(r['model'])} | {r['known_correct']}/{r['known_total']} | {r['missing_correct']}/{r['missing_total']} | {r['premise_correct']}/{r['premise_total']} | {r['unsupported_answers']} | {r['unnecessary_abstentions']} | {r['invalid_answers']} |")
    lines += ['', 'Questa batteria misura soltanto la fedeltà ai documenti sintetici forniti, non un tasso universale di allucinazioni. / This suite measures fidelity to the supplied synthetic documents, not a universal hallucination rate.', '']
    return '\n'.join(lines)
