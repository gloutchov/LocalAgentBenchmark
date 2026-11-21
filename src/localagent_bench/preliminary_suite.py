"""Validated, versioned synthetic probes; no model-generated grading code."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PreliminarySettings:
    suite: Path
    repetitions: int = 3
    max_tokens: int = 512
    timeout_seconds: int = 120
    max_response_bytes: int = 1048576
    max_event_bytes: int = 65536


def settings(root: Path, raw: Any) -> PreliminarySettings:
    if not isinstance(raw, dict) or set(raw) - {'suite', 'repetitions', 'max_tokens', 'timeout_seconds', 'max_response_bytes', 'max_event_bytes'}:
        raise ValueError('Configurazione preliminary non valida / Invalid preliminary configuration')
    path = raw.get('suite', 'preliminary/suite.json')
    if not isinstance(path, str) or not path or Path(path).is_absolute() or '..' in Path(path).parts:
        raise ValueError('Suite preliminary fuori progetto / Preliminary suite outside project')
    suite = root / path
    if suite.is_symlink() or root.resolve() not in suite.resolve().parents:
        raise ValueError('Suite preliminary non confinata / Unconfined preliminary suite')
    options = {}
    for key, default, low, high in (
        ('repetitions', 3, 2, 20), ('max_tokens', 512, 64, 8192),
        ('timeout_seconds', 120, 10, 1200), ('max_response_bytes', 1048576, 1024, 4194304),
        ('max_event_bytes', 65536, 1024, 262144),
    ):
        value = raw.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'preliminary.{key}: {low}..{high}')
        options[key] = value
    if options['max_event_bytes'] > options['max_response_bytes']:
        raise ValueError('Limite evento superiore al payload / Event limit exceeds payload')
    return PreliminarySettings(suite=suite, **options)


def load_suite(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.stat().st_size > 262144:
        raise ValueError('Suite preliminary troppo grande o symlink / Invalid preliminary suite')
    suite = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(suite, dict) or set(suite) != {'version', 'performance', 'questions'} or suite['version'] != 1:
        raise ValueError('Schema suite preliminary non valido / Invalid preliminary suite schema')
    performance, questions = suite['performance'], suite['questions']
    if not isinstance(performance, list) or not 2 <= len(performance) <= 8:
        raise ValueError('Richiesti 2..8 contesti preliminary / Expected 2..8 preliminary contexts')
    if not isinstance(questions, list) or not 6 <= len(questions) <= 100:
        raise ValueError('Richieste 6..100 domande / Expected 6..100 questions')
    ids = set()
    for item in performance + questions:
        if not isinstance(item, dict):
            raise ValueError('Sonda non valida / Invalid probe')
        is_question = 'category' in item
        expected = {'id', 'prompt', 'category', 'expected'} if is_question else {'id', 'prompt'}
        if set(item) != expected:
            raise ValueError('Campi sonda non validi / Invalid probe fields')
        for key in ('id', 'prompt'):
            value = item[key]
            if not isinstance(value, str) or not value or len(value) > (64 if key == 'id' else 100000):
                raise ValueError('Testo sonda non valido / Invalid probe text')
        if not item['id'].replace('_', '').isalnum() or item['id'] in ids:
            raise ValueError('ID sonda non valido o duplicato / Invalid or duplicate probe ID')
        ids.add(item['id'])
        if is_question and (item['category'] not in {'answer', 'unknown', 'false_premise'} or not isinstance(item['expected'], str) or len(item['expected']) > 256):
            raise ValueError('Risposta attesa non valida / Invalid expected answer')
    if {q['category'] for q in questions} != {'answer', 'unknown', 'false_premise'}:
        raise ValueError('Mancano categorie di affidabilità / Missing reliability categories')
    return suite


def grade_answer(text: str, question: dict[str, Any]) -> str:
    """Closed-world exact JSON protocol; invalid text is unscorable, not a fabricated fact."""
    try:
        answer = json.loads(text)
    except (ValueError, TypeError):
        return 'invalid'
    if not isinstance(answer, dict) or set(answer) != {'status', 'value'} or not isinstance(answer['status'], str) or answer['status'] not in {'answer', 'unknown', 'false_premise'} or not isinstance(answer['value'], str):
        return 'invalid'
    if answer['status'] == question['category'] and answer['value'].strip().casefold() == question['expected'].strip().casefold():
        return 'correct'
    if question['category'] == 'answer' and answer['status'] == 'unknown':
        return 'unnecessary_abstention'
    if question['category'] != 'answer' and answer['status'] == 'answer':
        return 'unsupported_answer'
    return 'incorrect'
