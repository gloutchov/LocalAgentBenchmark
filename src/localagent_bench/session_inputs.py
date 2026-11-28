"""One verified input context shared by every subprocess in a benchmark session."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

from .config import BenchmarkConfig, CaseSpec
from .integrity import (
    InputIntegrityError,
    fingerprint_tree,
    require_clean_inputs,
    snapshot_cases,
    verify_snapshot,
    verify_snapshot_origin,
)

SESSION_PREFIX = "guided-multi-"
CONTEXT_NAME = "benchmark-context"
MANIFEST_NAME = "snapshot.json"
PRELIMINARY_POLICY_NAME = "PRELIMINARY_POLICY.snapshot.md"


def freeze_session_inputs(
    config: BenchmarkConfig, session: Path, profiles: tuple[str, ...], execution_policy: str,
) -> str:
    cases = [config.cases[case_id] for case_id in dict.fromkeys(
        case_id for profile in profiles for case_id in config.profiles[profile]
    )]
    extra_paths = (config.preliminary.suite,) if "preliminary" in profiles else ()
    require_clean_inputs(config.root, cases, extra_paths)
    context = session / CONTEXT_NAME
    _, manifest = snapshot_cases(cases, context, config.root / "AGENTS.md",
                                 config.root / ".gitignore", execution_policy, extra_paths)
    if extra_paths:
        from .preliminary import PRELIMINARY_POLICY
        policy = context / PRELIMINARY_POLICY_NAME
        policy.write_bytes((execution_policy + PRELIMINARY_POLICY).encode("utf-8"))
        manifest["preliminary_policy_sha256"] = fingerprint_tree(policy)
    (context / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return fingerprint_tree(context)


def session_context(
    config: BenchmarkConfig, run_dir: Path, expected_hash: str, cases: list[CaseSpec],
    extra_paths: tuple[Path, ...], execution_policy: str,
) -> tuple[Path, list[CaseSpec], dict]:
    results = config.dashboard.results_directory.resolve()
    session = run_dir.parent
    context = session / CONTEXT_NAME
    if (
        session.parent != results or not session.name.startswith(SESSION_PREFIX)
        or not session.is_dir() or context.is_symlink() or not context.is_dir()
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        or fingerprint_tree(context) != expected_hash
    ):
        raise InputIntegrityError("Snapshot condiviso non valido o modificato / Invalid or changed shared snapshot")
    frozen: list[CaseSpec] = []
    for case in cases:
        root = context / "cases" / case.id

        def bind(path: Path | None) -> Path | None:
            return root / path.relative_to(case.directory) if path is not None else None

        frozen.append(replace(case, directory=root, prompt_path=bind(case.prompt_path),
                              fixture_path=bind(case.fixture_path), grader_path=bind(case.grader_path),
                              manifest_path=bind(case.manifest_path), manual_rubric_path=bind(case.manual_rubric_path)))
    policy_name = PRELIMINARY_POLICY_NAME if extra_paths else "EXECUTION_POLICY.snapshot.md"
    verify_snapshot_origin(config.root, context, cases, frozen, extra_paths,
                           policy_name, execution_policy)
    path = context / MANIFEST_NAME
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise InputIntegrityError("Manifesto snapshot non valido / Invalid snapshot manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), dict):
        raise InputIntegrityError("Manifesto snapshot non valido / Invalid snapshot manifest")
    # Re-read only the fields for this phase. Manifest paths are matched against
    # trusted CaseSpecs before any paths from the manifest are dereferenced.
    keys = ("prompt", "fixture", "grader", "manifest", "manual_rubric")
    phase_cases = {}
    for case in frozen:
        entry = manifest["cases"].get(case.id)
        if not isinstance(entry, dict) or any(
            entry.get(f"{key}_path") != (
                path.relative_to(case.directory).as_posix() if (path := getattr(case, f"{key}_path")) else None
            ) for key in keys
        ):
            raise InputIntegrityError("Percorsi snapshot incoerenti / Inconsistent snapshot paths")
        expected_hashes = (entry.get("input_sha256"), manifest.get("execution_policy_sha256"))
        if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in expected_hashes):
            raise InputIntegrityError("Hash del caso non valido / Invalid case hash")
        input_hash, policy_hash = expected_hashes
        if entry.get("effective_input_sha256") != hashlib.sha256(f"{input_hash}\0{policy_hash}".encode()).hexdigest():
            raise InputIntegrityError("Hash effettivo non valido / Invalid effective hash")
        phase_cases[case.id] = entry
    phase_manifest = {
        "agents_sha256": manifest.get("agents_sha256"),
        "gitignore_sha256": manifest.get("gitignore_sha256"),
        "execution_policy_sha256": manifest.get("execution_policy_sha256"),
        "cases": phase_cases,
    }
    if extra_paths:
        phase_manifest["extra_inputs"] = {"extra-0.json": fingerprint_tree(context / "extra-0.json")}
        phase_manifest["preliminary_policy_sha256"] = fingerprint_tree(context / PRELIMINARY_POLICY_NAME)
    if verify_snapshot(context, phase_manifest) or fingerprint_tree(context) != expected_hash:
        raise InputIntegrityError("Contenuto snapshot incoerente / Inconsistent snapshot contents")
    return context, frozen, phase_manifest
