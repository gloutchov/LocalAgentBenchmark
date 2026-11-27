"""Explicit, local model-file provenance for resident Colibrì models."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ModelBundleError(ValueError):
    """A bundle cannot be validated or no longer matches the run fingerprint."""


_SHA256 = re.compile(r"[0-9a-f]{64}")


def _relative_file(value: Any) -> bool:
    return (
        isinstance(value, str) and 0 < len(value) <= 1024
        and not any(part in {"", ".", ".."} for part in value.split("/"))
        and not any(char in "\\:" or ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _unique_files(files: list[str]) -> bool:
    return len({file.casefold() for file in files}) == len(files)


@dataclass(frozen=True)
class ModelBundle:
    root: Path
    files: tuple[str, ...]

    @classmethod
    def parse(cls, raw: Any) -> ModelBundle:
        if not isinstance(raw, dict) or set(raw) != {"root", "files"}:
            raise ModelBundleError("Bundle modello non valido / Invalid model bundle")
        root, files = raw["root"], raw["files"]
        if not isinstance(root, str) or not root or "\x00" in root:
            raise ModelBundleError("Root del bundle non valida / Invalid bundle root")
        try:
            root_path = Path(root).expanduser()
        except RuntimeError:
            raise ModelBundleError("Root del bundle non valida / Invalid bundle root") from None
        if not root_path.is_absolute() or ".." in root_path.parts:
            raise ModelBundleError("Root del bundle deve essere assoluta / Bundle root must be absolute")
        if (not isinstance(files, list) or not 1 <= len(files) <= 512
                or not all(_relative_file(file) for file in files) or not _unique_files(files)):
            raise ModelBundleError("File del bundle non validi o duplicati / Invalid or duplicate bundle files")
        return cls(root_path, tuple(sorted(files)))

    def _entry(self, name: str) -> tuple[Path, os.stat_result]:
        try:
            if self.root.resolve(strict=True) != self.root or not self.root.is_dir():
                raise ModelBundleError("Root del bundle non canonica / Noncanonical bundle root")
            path = self.root / name
            if path.resolve(strict=True) != path:
                raise ModelBundleError("Symlink nel bundle rifiutato / Bundle symlink rejected")
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ModelBundleError("Il bundle richiede file regolari / Bundle requires regular files")
            return path, info
        except (OSError, RuntimeError) as exc:
            raise ModelBundleError("File del bundle non accessibile / Bundle file unavailable") from None

    def fingerprint(self) -> tuple[dict[str, Any], dict[str, tuple[int, ...]]]:
        files = []
        identity: dict[str, tuple[int, ...]] = {}
        seen: set[tuple[int, int]] = set()
        for name in self.files:
            path, before = self._entry(name)
            key = (before.st_dev, before.st_ino)
            if key in seen:
                raise ModelBundleError("File del bundle duplicato / Duplicate bundle file")
            seen.add(key)
            expected = _identity(before)
            try:
                flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
                         | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(os.open(path, flags), "rb") as handle:
                    if _identity(os.fstat(handle.fileno())) != expected:
                        raise ModelBundleError("File del bundle cambiato / Bundle file changed")
                    hasher = hashlib.sha256()
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        hasher.update(block)
                    digest = hasher.hexdigest()
                    if _identity(os.fstat(handle.fileno())) != expected:
                        raise ModelBundleError("File del bundle cambiato / Bundle file changed")
            except OSError:
                raise ModelBundleError("File del bundle non leggibile / Bundle file unreadable") from None
            identity[name] = expected
            files.append({"path": name, "size_bytes": before.st_size, "sha256": digest})
        self.verify(identity)
        return {"association": "declared", "files": files, "fingerprint_sha256": bundle_digest(files)}, identity

    def verify(self, identity: dict[str, tuple[int, ...]]) -> None:
        if any(_identity(self._entry(name)[1]) != expected for name, expected in identity.items()):
            raise ModelBundleError("File del bundle cambiato / Bundle file changed")


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def bundle_digest(files: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def valid_bundle_manifest(value: Any, expected: Any) -> bool:
    if not isinstance(value, dict) or value.get("association") != "declared":
        return False
    files = value.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 512:
        return False
    for file in files:
        if (not isinstance(file, dict) or set(file) != {"path", "size_bytes", "sha256"}
                or not _relative_file(file["path"]) or type(file["size_bytes"]) is not int or file["size_bytes"] < 0
                or not isinstance(file["sha256"], str) or not _SHA256.fullmatch(file["sha256"])):
            return False
    names = [file["path"] for file in files]
    return names == sorted(names) and _unique_files(names) and value.get("fingerprint_sha256") == expected == bundle_digest(files)
