"""Structured child-process execution for the guided benchmark."""

from __future__ import annotations

import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


class GuidedProcessError(RuntimeError):
    """Raised when a guided child process cannot be started safely."""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    cancelled: bool
    output_tail: tuple[str, ...]


@contextmanager
def interruptible():
    """Map the managed subprocess' POSIX termination request to orderly cleanup."""
    def interrupt(_signum, _frame):
        raise KeyboardInterrupt()

    previous = None
    if threading.current_thread() is threading.main_thread():
        previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def _checked_args(args: Sequence[str]) -> list[str]:
    command = list(args)
    if not command or any(not isinstance(item, str) or not item or "\x00" in item for item in command):
        raise GuidedProcessError("Argomenti del processo non validi")
    return command


def _creation_options() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.terminate()
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return


class ManagedProcessRunner:
    """Run one command without a shell and support cross-platform cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: subprocess.Popen[str] | None = None

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        cancel_event: threading.Event,
        on_line: Callable[[str], None] | None = None,
    ) -> ProcessResult:
        command = _checked_args(args)
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
                **_creation_options(),
            )
        except OSError as exc:
            raise GuidedProcessError(f"Impossibile avviare il processo: {exc}") from exc
        with self._lock:
            self._current = process

        lines: queue.Queue[str | None] = queue.Queue()

        def read_output() -> None:
            assert process.stdout is not None
            try:
                for raw in process.stdout:
                    lines.put(raw.rstrip("\r\n"))
            finally:
                lines.put(None)

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        tail: list[str] = []
        cancelled = False
        stream_finished = False
        try:
            while process.poll() is None or not stream_finished:
                if cancel_event.is_set() and process.poll() is None:
                    cancelled = True
                    _terminate_tree(process)
                try:
                    line = lines.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    stream_finished = True
                    continue
                tail.append(line)
                del tail[:-200]
                if on_line is not None:
                    on_line(line)
            reader.join(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
            return ProcessResult(
                returncode=int(process.returncode or 0),
                cancelled=cancelled,
                output_tail=tuple(tail),
            )
        finally:
            if process.poll() is None:
                _terminate_tree(process)
            with self._lock:
                if self._current is process:
                    self._current = None

    def cancel(self) -> None:
        with self._lock:
            process = self._current
        if process is not None:
            _terminate_tree(process)


def start_detached(args: Sequence[str], *, cwd: Path) -> subprocess.Popen[bytes]:
    """Start the dashboard as an independent structured-argument process."""
    command = _checked_args(args)
    options: dict[str, object]
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        options = {"creationflags": flags}
    else:
        options = {"start_new_session": True}
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            **options,
        )
    except OSError as exc:
        raise GuidedProcessError(f"Impossibile avviare la dashboard: {exc}") from exc
    try:
        returncode = process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        return process
    raise GuidedProcessError(f"La dashboard si è chiusa subito (codice {returncode})")


def prepare_pi_path(pi_command: tuple[str, ...], *, cwd: Path, timeout: float) -> None:
    """Recover the macOS GUI launch when Pi needs the installed Homebrew Node."""
    if sys.platform != "darwin" or pi_command != ("pi",):
        return
    brew = shutil.which("brew")
    if not brew:
        return
    node_directory = Path(brew).parent.parent / "opt" / "node@24" / "bin"
    candidate = node_directory / "node"
    current = shutil.which("node")
    if not os.access(candidate, os.X_OK) or (current and Path(current).resolve() == candidate.resolve()):
        return

    options = {
        "cwd": cwd, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
        "stderr": subprocess.PIPE, "text": True, "timeout": timeout, "check": False,
    }
    command = [*pi_command, "--version"]
    try:
        current_pi = subprocess.run(command, **options)
        if current_pi.returncode == 0 or "does not provide an export named 'enableCompileCache'" not in current_pi.stderr:
            return
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join((str(node_directory), env.get("PATH", os.defpath)))
        alternate_pi = subprocess.run(command, env=env, **options)
    except (OSError, subprocess.TimeoutExpired):
        return
    if alternate_pi.returncode == 0:
        os.environ["PATH"] = env["PATH"]


def python_executable() -> str:
    """Return the interpreter running the GUI, including pythonw on Windows when used."""
    return sys.executable


__all__ = [
    "GuidedProcessError",
    "ManagedProcessRunner",
    "ProcessResult",
    "python_executable",
    "start_detached",
]
