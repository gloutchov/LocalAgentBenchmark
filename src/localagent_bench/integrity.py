"""Input snapshots and repository-integrity checks for benchmark runs."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .config import CaseSpec


class InputIntegrityError(RuntimeError):
    """Raised when benchmark inputs are not safe to snapshot."""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def _entry_fingerprint(path: Path) -> str:
    if path.is_symlink():
        return f"symlink:{os.readlink(path)}"
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return f"file:{digest.hexdigest()}"
    return "directory"


def fingerprint_tree(root: Path) -> str:
    """Return a deterministic digest for a file or directory tree."""
    root = root.resolve()
    digest = hashlib.sha256()
    if not root.exists():
        digest.update(b"missing")
        return digest.hexdigest()
    if root.is_file() or root.is_symlink():
        digest.update(_entry_fingerprint(root).encode("utf-8"))
        return digest.hexdigest()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_entry_fingerprint(path).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def repository_fingerprints(root: Path, excluded_roots: Iterable[Path] = ()) -> dict[str, str]:
    """Fingerprint tracked and visible untracked repository files."""
    payload = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout
    paths = payload.decode("utf-8", errors="surrogateescape").split("\0")
    excluded = [path.resolve(strict=False) for path in excluded_roots]
    fingerprints: dict[str, str] = {}
    for relative in sorted(path for path in paths if path):
        candidate = root / relative
        resolved = candidate.resolve(strict=False)
        if any(resolved == excluded_root or excluded_root in resolved.parents for excluded_root in excluded):
            continue
        fingerprints[relative] = _entry_fingerprint(candidate) if candidate.exists() or candidate.is_symlink() else "missing"
    return fingerprints


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Return sorted paths whose presence or content changed."""
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def _tracked_paths(repository_root: Path, source: Path) -> list[Path]:
    relative_source = source.relative_to(repository_root)
    payload = subprocess.run(
        ["git", "ls-files", "-z", "--", str(relative_source)],
        cwd=repository_root, capture_output=True, check=True, timeout=30,
    ).stdout
    return [repository_root / path for path in
            payload.decode("utf-8", errors="surrogateescape").split("\0") if path]


def _copy_tracked_tree(repository_root: Path, source: Path, destination: Path) -> None:
    """Copy and verify only Git-tracked files below ``source``."""
    tracked = _tracked_paths(repository_root, source)
    destination.mkdir(parents=True, exist_ok=False)
    for source_path in tracked:
        target_path = destination / source_path.relative_to(source)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_symlink():
            target_path.symlink_to(os.readlink(source_path))
        else:
            shutil.copy2(source_path, target_path)
        if _entry_fingerprint(source_path) != _entry_fingerprint(target_path):
            raise InputIntegrityError(f"Copia snapshot non verificata: {source_path.relative_to(repository_root)}")


def _copy_verified_file(source: Path, destination: Path, label: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if _entry_fingerprint(source) != _entry_fingerprint(destination):
        raise InputIntegrityError(f"La copia di {label} non coincide con la sorgente")


def verify_snapshot_origin(
    root: Path, context: Path, sources: list[CaseSpec], frozen: list[CaseSpec],
    extra_paths: tuple[Path, ...], policy_name: str, execution_policy: str,
) -> None:
    """Anchor a shared subprocess snapshot to the same clean inputs as a solo run."""
    files = [
        (root / "AGENTS.md", context / "AGENTS.snapshot.md"),
        (root / ".gitignore", context / ".gitignore.snapshot"),
        *((source, context / f"extra-{index}.json") for index, source in enumerate(extra_paths)),
    ]
    for source, snapshot in zip(sources, frozen, strict=True):
        for field in ("prompt_path", "grader_path", "manifest_path", "manual_rubric_path"):
            if source_path := getattr(source, field):
                files.append((source_path, getattr(snapshot, field)))
        if snapshot.fixture_path.is_symlink() or context not in snapshot.fixture_path.resolve().parents:
            raise InputIntegrityError("Fixture snapshot non confinata / Unconfined snapshot fixture")
        tracked = {item.relative_to(source.fixture_path): item
                   for item in _tracked_paths(root, source.fixture_path)}
        actual = {item.relative_to(snapshot.fixture_path): item for item in snapshot.fixture_path.rglob("*")
                  if item.is_symlink() or not item.is_dir()}
        allowed_case_files = {getattr(snapshot, field) for field in
                              ("prompt_path", "grader_path", "manifest_path", "manual_rubric_path")}
        allowed_case_files.update(snapshot.fixture_path / key for key in tracked)
        observed_case_files = {item for item in snapshot.directory.rglob("*") if item.is_symlink() or not item.is_dir()}
        if observed_case_files != allowed_case_files - {None} or tracked.keys() != actual.keys() or any(
            _entry_fingerprint(item) != _entry_fingerprint(actual[key]) for key, item in tracked.items()
        ):
            raise InputIntegrityError(f"Fixture condivisa non valida / Invalid shared fixture: {source.id}")
    for source, target in files:
        if target.is_symlink() or not target.is_file() or context not in target.resolve().parents:
            raise InputIntegrityError("File snapshot non confinato / Unconfined snapshot file")
        if _entry_fingerprint(source) != _entry_fingerprint(target):
            raise InputIntegrityError("Snapshot diverso dalla sorgente / Snapshot differs from source")
    policy = context / policy_name
    if policy.is_symlink() or not policy.is_file() or policy.read_bytes() != execution_policy.encode("utf-8"):
        raise InputIntegrityError("Policy snapshot non valida / Invalid snapshot policy")


def require_clean_inputs(root: Path, cases: Iterable[CaseSpec], extra_paths: Iterable[Path] = ()) -> None:
    """Reject dirty instructions, manifests, prompts, graders, rubrics, or fixtures."""
    try:
        repository_root = Path(_git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputIntegrityError(f"Repository Git non disponibile: {exc}") from exc
    if repository_root != root.resolve():
        raise InputIntegrityError(f"La configurazione non punta alla root Git: {root}")
    pathspecs = ["AGENTS.md", ".gitignore", *(str(case.directory.relative_to(root)) for case in cases)]
    for path in extra_paths:
        if path.is_symlink() or root.resolve() not in path.resolve().parents:
            raise InputIntegrityError("Input aggiuntivo non confinato / Unconfined extra input")
        relative = path.relative_to(root).as_posix()
        if not _git(root, "ls-files", "--", relative).stdout.strip():
            raise InputIntegrityError("Input aggiuntivo non tracciato / Untracked extra input")
        pathspecs.append(relative)
    status = _git(root, "status", "--porcelain", "--untracked-files=all", "--", *pathspecs).stdout.strip()
    if status:
        raise InputIntegrityError(
            "Input benchmark modificati o non tracciati; ripristinali o committali prima del run:\n" + status
        )


def repository_metadata(root: Path) -> dict[str, object]:
    """Capture Git provenance without storing file contents."""
    status_lines = _git(root, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return {
        "commit": _git(root, "rev-parse", "HEAD").stdout.strip(),
        "branch": _git(root, "branch", "--show-current").stdout.strip(),
        "dirty": bool(status_lines),
        "dirty_paths": [line[3:] if len(line) > 3 else line for line in status_lines],
    }


def snapshot_cases(
    cases: Iterable[CaseSpec],
    destination: Path,
    agents_path: Path,
    gitignore_path: Path,
    execution_policy: str | None = None,
    extra_paths: Iterable[Path] = (),
) -> tuple[list[CaseSpec], dict[str, object]]:
    """Create one frozen input copy shared by every attempt in a run."""
    destination.mkdir(parents=True, exist_ok=False)
    agents_snapshot = destination / "AGENTS.snapshot.md"
    gitignore_snapshot = destination / ".gitignore.snapshot"
    source_agents_hash = fingerprint_tree(agents_path)
    source_gitignore_hash = fingerprint_tree(gitignore_path)
    shutil.copy2(agents_path, agents_snapshot)
    shutil.copy2(gitignore_path, gitignore_snapshot)
    if fingerprint_tree(agents_snapshot) != source_agents_hash:
        raise InputIntegrityError("La copia congelata di AGENTS.md non coincide con la sorgente")
    if fingerprint_tree(gitignore_snapshot) != source_gitignore_hash:
        raise InputIntegrityError("La copia congelata di .gitignore non coincide con la sorgente")
    policy_hash = ""
    if execution_policy is not None:
        policy_snapshot = destination / "EXECUTION_POLICY.snapshot.md"
        policy_snapshot.write_text(execution_policy, encoding="utf-8")
        policy_hash = fingerprint_tree(policy_snapshot)
    snapshot_specs: list[CaseSpec] = []
    case_manifest: dict[str, dict[str, object]] = {}
    cases_root = destination / "cases"
    cases_root.mkdir()
    repository_root = agents_path.parent
    for case in cases:
        case_root = cases_root / case.id
        case_root.mkdir()
        prompt_relative = case.prompt_path.relative_to(case.directory)
        fixture_relative = case.fixture_path.relative_to(case.directory)
        grader_relative = case.grader_path.relative_to(case.directory)
        prompt = case_root / prompt_relative
        fixture = case_root / fixture_relative
        grader = case_root / grader_relative
        _copy_verified_file(case.prompt_path, prompt, f"prompt {case.id}")
        _copy_verified_file(case.grader_path, grader, f"grader {case.id}")
        _copy_tracked_tree(repository_root, case.fixture_path, fixture)
        manifest_path: Path | None = None
        if case.manifest_path is not None:
            manifest_relative = case.manifest_path.relative_to(case.directory)
            manifest_path = case_root / manifest_relative
            _copy_verified_file(case.manifest_path, manifest_path, f"manifesto {case.id}")
        rubric_path: Path | None = None
        if case.manual_rubric_path is not None:
            rubric_relative = case.manual_rubric_path.relative_to(case.directory)
            rubric_path = case_root / rubric_relative
            _copy_verified_file(case.manual_rubric_path, rubric_path, f"rubrica {case.id}")
        snapshot = CaseSpec(
            id=case.id,
            title=case.title,
            title_en=case.title_en,
            category=case.category,
            weight=case.weight,
            directory=case_root,
            prompt_path=prompt,
            fixture_path=fixture,
            grader_path=grader,
            manifest_path=manifest_path,
            manual_rubric_path=rubric_path,
            manual_rubric_max_score=case.manual_rubric_max_score,
        )
        snapshot_specs.append(snapshot)
        input_hash = fingerprint_tree(snapshot.directory)
        case_manifest[case.id] = {
            "prompt_sha256": fingerprint_tree(snapshot.prompt_path),
            "fixture_sha256": fingerprint_tree(snapshot.fixture_path),
            "grader_sha256": fingerprint_tree(snapshot.grader_path),
            "manifest_sha256": fingerprint_tree(snapshot.manifest_path) if snapshot.manifest_path else None,
            "manual_rubric_sha256": (
                fingerprint_tree(snapshot.manual_rubric_path) if snapshot.manual_rubric_path else None
            ),
            "prompt_path": prompt_relative.as_posix(),
            "fixture_path": fixture_relative.as_posix(),
            "grader_path": grader_relative.as_posix(),
            "manifest_path": (
                snapshot.manifest_path.relative_to(case_root).as_posix() if snapshot.manifest_path else None
            ),
            "manual_rubric_path": (
                snapshot.manual_rubric_path.relative_to(case_root).as_posix()
                if snapshot.manual_rubric_path
                else None
            ),
            "input_sha256": input_hash,
            "effective_input_sha256": hashlib.sha256(
                f"{input_hash}\0{policy_hash}".encode("utf-8")
            ).hexdigest(),
        }
    manifest: dict[str, object] = {
        "agents_sha256": source_agents_hash,
        "gitignore_sha256": source_gitignore_hash,
        "cases": case_manifest,
    }
    if policy_hash:
        manifest["execution_policy_sha256"] = policy_hash
    extras = {}
    for index, source in enumerate(extra_paths):
        name = f"extra-{index}.json"
        _copy_verified_file(source, destination / name, name)
        extras[name] = fingerprint_tree(destination / name)
    if extras:
        manifest["extra_inputs"] = extras
    return snapshot_specs, manifest


def verify_snapshot(destination: Path, manifest: dict[str, object]) -> list[str]:
    """Return snapshot components that no longer match their initial hashes."""
    changed: list[str] = []
    for name, expected in manifest.get("extra_inputs", {}).items():
        if Path(name).name != name or fingerprint_tree(destination / name) != expected:
            changed.append("extra_input")
    agents = destination / "AGENTS.snapshot.md"
    if fingerprint_tree(agents) != manifest.get("agents_sha256"):
        changed.append("AGENTS.snapshot.md")
    gitignore = destination / ".gitignore.snapshot"
    if fingerprint_tree(gitignore) != manifest.get("gitignore_sha256"):
        changed.append(".gitignore.snapshot")
    expected_policy = manifest.get("execution_policy_sha256")
    if expected_policy and fingerprint_tree(destination / "EXECUTION_POLICY.snapshot.md") != expected_policy:
        changed.append("EXECUTION_POLICY.snapshot.md")
    case_manifest = manifest.get("cases", {})
    if not isinstance(case_manifest, dict):
        return ["input-manifest"]
    for case_id, expected in case_manifest.items():
        if not isinstance(expected, dict):
            changed.append(f"cases/{case_id}")
            continue
        case_root = destination / "cases" / case_id
        prompt_relative = str(expected.get("prompt_path") or "prompt.md")
        fixture_relative = str(expected.get("fixture_path") or "fixture")
        grader_relative = str(expected.get("grader_path") or "grader.py")
        checks = {
            prompt_relative: fingerprint_tree(case_root / prompt_relative),
            fixture_relative: fingerprint_tree(case_root / fixture_relative),
            grader_relative: fingerprint_tree(case_root / grader_relative),
            "input": fingerprint_tree(case_root),
        }
        expected_keys = {
            prompt_relative: "prompt_sha256",
            fixture_relative: "fixture_sha256",
            grader_relative: "grader_sha256",
            "input": "input_sha256",
        }
        manifest_relative = expected.get("manifest_path")
        if isinstance(manifest_relative, str) and manifest_relative:
            checks[manifest_relative] = fingerprint_tree(case_root / manifest_relative)
            expected_keys[manifest_relative] = "manifest_sha256"
        rubric_relative = expected.get("manual_rubric_path")
        if isinstance(rubric_relative, str) and rubric_relative:
            checks[rubric_relative] = fingerprint_tree(case_root / rubric_relative)
            expected_keys[rubric_relative] = "manual_rubric_sha256"
        for label, actual in checks.items():
            if actual != expected.get(expected_keys[label]):
                changed.append(f"cases/{case_id}/{label}")
    return sorted(set(changed))
