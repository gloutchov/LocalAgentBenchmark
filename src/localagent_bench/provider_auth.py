"""Host-only credential lookup; never persist secrets or place them in argv/env."""
from __future__ import annotations

import ctypes
import getpass
import re
import shutil
import subprocess
import sys
from typing import Callable


SERVICE = "LocalAgentBenchmark"
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+={0,2}\Z")


class CredentialError(RuntimeError):
    """A credential cannot be resolved; messages contain status, never output."""


def validate_reference(reference: str) -> str:
    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        raise CredentialError("credential_reference_invalid / riferimento credenziale non valido")
    return reference


def validate_secret(value: str) -> str:
    # RFC 6750 bearer syntax also rules out CRLF/header injection and whitespace.
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or not _TOKEN.fullmatch(value):
        raise CredentialError("credential_value_invalid / credenziale non valida")
    return value


def _command_value(command: list[str], *, timeout_seconds: float) -> str:
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=timeout_seconds,
                                check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CredentialError("credential_store_unavailable / archivio credenziali non disponibile") from None
    if result.returncode:
        raise CredentialError("credential_not_found / credenziale non disponibile")
    try:
        # Native command-line stores add a line terminator. Spaces are not stripped.
        value = result.stdout.decode("utf-8").removesuffix("\n").removesuffix("\r")
    except UnicodeError:
        raise CredentialError("credential_value_invalid / credenziale non valida") from None
    return validate_secret(value)


def _windows_value(reference: str) -> str:
    # Generic credentials are read directly with the user token. No secret-bearing
    # command line, PowerShell, temporary file, registry value, or environment.
    from ctypes import wintypes

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                    ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                    ("UserName", wintypes.LPWSTR)]

    pointer = ctypes.POINTER(CREDENTIALW)()
    library = ctypes.WinDLL("advapi32", use_last_error=True)
    library.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    library.CredReadW.restype = wintypes.BOOL
    library.CredFree.argtypes = [ctypes.c_void_p]
    library.CredFree.restype = None
    if not library.CredReadW(f"{SERVICE}:{reference}", 1, 0, ctypes.byref(pointer)):
        raise CredentialError("credential_not_found / credenziale non disponibile")
    try:
        size = pointer.contents.CredentialBlobSize
        if not 2 <= size <= 8192 or size % 2:
            raise CredentialError("credential_value_invalid / credenziale non valida")
        try:
            value = ctypes.string_at(pointer.contents.CredentialBlob, size).decode("utf-16-le")
        except UnicodeError:
            raise CredentialError("credential_value_invalid / credenziale non valida") from None
        return validate_secret(value)
    finally:
        library.CredFree(pointer)


def resolve_credential(reference: str, *, prompt: bool = False,
                       prompt_function: Callable[[str], str] | None = None,
                       timeout_seconds: float = 10) -> str:
    """Read an existing OS credential, or explicitly request a memory-only prompt.

    macOS: service ``LocalAgentBenchmark``, account ``reference``.
    Windows: generic credential target ``LocalAgentBenchmark:reference`` (UTF-16).
    Linux: Secret Service attributes ``service`` and ``account`` as above.
    No store is modified. Prompt mode never reads a real keychain and is opt-in.
    """
    validate_reference(reference)
    if not 0 < timeout_seconds <= 60:
        raise CredentialError("credential_timeout_invalid / timeout credenziale non valido")
    if prompt:
        reader = prompt_function or getpass.getpass
        if prompt_function is None and not sys.stdin.isatty():
            raise CredentialError("credential_prompt_requires_terminal / serve un terminale per la credenziale")
        try:
            return validate_secret(reader("Local provider API key / Chiave API provider locale: "))
        except (EOFError, KeyboardInterrupt):
            raise CredentialError("credential_prompt_cancelled / inserimento credenziale annullato") from None
    if sys.platform == "darwin":
        return _command_value(["/usr/bin/security", "find-generic-password", "-s", SERVICE,
                               "-a", reference, "-w"], timeout_seconds=timeout_seconds)
    if sys.platform == "win32":
        try:
            return _windows_value(reference)
        except (OSError, AttributeError):
            raise CredentialError("credential_store_unavailable / archivio credenziali non disponibile") from None
    executable = shutil.which("secret-tool")
    if not executable:
        raise CredentialError("credential_store_unavailable / archivio credenziali non disponibile")
    return _command_value([executable, "lookup", "service", SERVICE, "account", reference],
                          timeout_seconds=timeout_seconds)
