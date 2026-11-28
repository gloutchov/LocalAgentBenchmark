"""Local-only launcher and static server for the official results dashboard."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import webbrowser
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

from .config import BenchmarkConfig, ConfigError, load_config
from .dashboard_data import (
    MAX_SOURCE_BYTES,
    DashboardDataError,
    build_dashboard_data,
    validate_dashboard_data,
)


ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_SCRIPT = Path("data/snapshot.js")
STATIC_ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "favicon.svg": "image/svg+xml",
    "js/core.js": "text/javascript; charset=utf-8",
    "js/i18n.js": "text/javascript; charset=utf-8",
    "js/preliminary.js": "text/javascript; charset=utf-8",
    "js/ui.js": "text/javascript; charset=utf-8",
    "js/app.js": "text/javascript; charset=utf-8",
}
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class DashboardAppError(ValueError):
    """Raised for invalid launcher inputs or unsafe local-server state."""


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _confined_path(path: Path, *, root: Path, expected: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    if candidate.is_symlink():
        raise DashboardAppError(f"{expected} non può essere un symlink: {path}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise DashboardAppError(f"{expected} non disponibile: {path}") from exc
    if not _inside(resolved, root.resolve()):
        raise DashboardAppError(f"{expected} deve restare nella root del progetto")
    return resolved


def load_dashboard_dataset(path: Path, *, root: Path) -> dict[str, Any]:
    """Load one already-sanitized dashboard dataset from within the repository."""
    source = _confined_path(path, root=root, expected="Dataset dashboard")
    if not source.is_file():
        raise DashboardAppError(f"Dataset dashboard non disponibile: {path}")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise DashboardAppError(f"Dataset dashboard troppo grande: massimo {MAX_SOURCE_BYTES} byte")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        validate_dashboard_data(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, DashboardDataError) as exc:
        raise DashboardAppError(f"Dataset dashboard non valido: {source.name}") from exc
    return payload


def discover_run_directories(results_directory: Path, *, root: Path) -> tuple[list[Path], list[str]]:
    """Return valid immediate run children and basename-only skip notices."""
    if not results_directory.exists():
        return [], []
    directory = _confined_path(results_directory, root=root, expected="Directory risultati")
    if not directory.is_dir():
        raise DashboardAppError("La directory risultati configurata non è una directory")
    valid: list[Path] = []
    skipped: list[str] = []
    for candidate in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not candidate.is_dir() or candidate.is_symlink():
            continue
        if not (candidate / "run.json").is_file() or not (candidate / "report.json").is_file():
            continue
        try:
            build_dashboard_data([candidate])
        except DashboardDataError:
            skipped.append(candidate.name)
        else:
            valid.append(candidate.resolve())
    return valid, skipped


def resolve_run_directories(paths: Iterable[Path], *, root: Path) -> list[Path]:
    """Resolve explicit run directories without allowing paths outside the project."""
    output: list[Path] = []
    for path in paths:
        resolved = _confined_path(path, root=root, expected="Directory di run")
        if not resolved.is_dir():
            raise DashboardAppError(f"Directory di run non valida: {path}")
        output.append(resolved)
    if len(set(output)) != len(output):
        raise DashboardAppError("Le directory di run devono essere distinte")
    return output


def render_dataset_script(dataset: dict[str, Any], *, source: str, skipped_runs: int = 0,
                          session: dict[str, Any] | None = None) -> bytes:
    """Serialize validated public data as a classic script that also works under file://."""
    validate_dashboard_data(dataset)
    metadata = {
        "source": source if source in {"snapshot", "local", "import"} else "snapshot",
        "run_count": len(dataset["runs"]),
        "skipped_runs": max(0, int(skipped_runs)),
    }
    if session is not None:
        metadata["session"] = session
    payload = json.dumps(dataset, ensure_ascii=True, separators=(",", ":"))
    meta = json.dumps(metadata, ensure_ascii=True, separators=(",", ":"))
    return (
        "window.LOCALAGENT_DASHBOARD_DATA="
        + payload
        + ";\nwindow.LOCALAGENT_DASHBOARD_META="
        + meta
        + ";\n"
    ).encode("utf-8")


def write_snapshot_script(
    dataset: dict[str, Any],
    output_path: Path,
    *,
    root: Path,
    overwrite: bool = False,
) -> None:
    """Write the reviewed file:// payload atomically and only when explicitly requested."""
    output = output_path.resolve()
    if not _inside(output, root.resolve()):
        raise DashboardAppError("Lo snapshot deve restare nella root del progetto")
    if output.exists() and not overwrite:
        raise DashboardAppError("Snapshot già esistente; usare --force per sostituirlo")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(render_dataset_script(dataset, source="snapshot"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, output)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serve only known dashboard assets and an in-memory sanitized dataset."""

    server_version = "LocalAgentDashboard/1"

    def __init__(
        self,
        *args: Any,
        assets_directory: Path,
        dataset_script: bytes,
        **kwargs: Any,
    ) -> None:
        self.assets_directory = assets_directory
        self.dataset_script = dataset_script
        super().__init__(*args, **kwargs)

    def _asset(self) -> tuple[bytes, str] | None:
        path = unquote(urlsplit(self.path).path)
        if path in {"", "/"}:
            path = "/index.html"
        relative = path.removeprefix("/")
        if relative == SNAPSHOT_SCRIPT.as_posix():
            return self.dataset_script, "text/javascript; charset=utf-8"
        content_type = STATIC_ASSETS.get(relative)
        if content_type is None:
            return None
        target = (self.assets_directory / relative).resolve()
        if not _inside(target, self.assets_directory) or not target.is_file() or target.is_symlink():
            return None
        try:
            return target.read_bytes(), content_type
        except OSError:
            return None

    def _send(self, include_body: bool) -> None:
        asset = self._asset()
        if asset is None:
            self._send_error(HTTPStatus.NOT_FOUND, include_body=include_body)
            return
        body, content_type = asset
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, *, include_body: bool = True) -> None:
        body = f"{status.value} {status.phrase}\n".encode("ascii")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._send(include_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self._send(include_body=False)

    def do_POST(self) -> None:  # noqa: N802
        self._send_error(HTTPStatus.METHOD_NOT_ALLOWED)

    def log_message(self, _format: str, *args: Any) -> None:
        return


def create_dashboard_server(
    *,
    dataset: dict[str, Any],
    assets_directory: Path,
    host: str,
    port: int,
    source: str,
    skipped_runs: int = 0,
    session: dict[str, Any] | None = None,
) -> ThreadingHTTPServer:
    """Create, but do not start, a loopback-only dashboard server."""
    if host != "127.0.0.1":
        raise DashboardAppError("Il server dashboard può usare soltanto 127.0.0.1")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise DashboardAppError("La porta dashboard deve essere tra 0 e 65535")
    assets = assets_directory.resolve()
    if not assets.is_dir() or not _inside(assets, ROOT):
        raise DashboardAppError("Directory asset dashboard non valida")
    handler = partial(
        DashboardRequestHandler,
        assets_directory=assets,
        dataset_script=render_dataset_script(dataset, source=source, skipped_runs=skipped_runs, session=session),
    )
    try:
        return ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise DashboardAppError(f"Impossibile aprire la porta dashboard {port}: {exc}") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashboard.py",
        description="Apre la dashboard ufficiale dei risultati LocalAgent Benchmark",
    )
    parser.add_argument("run_dirs", nargs="*", type=Path, help="Directory di run; default: run compatibili in results/")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.json")
    parser.add_argument("--session", type=Path, help="Manifesto di sessione multiprovider / Multi-provider session manifest")
    parser.add_argument("--dataset", type=Path, help="Usa un dashboard-data.json già esportato")
    parser.add_argument("--port", type=int, help="Porta loopback; 0 sceglie automaticamente")
    parser.add_argument("--no-open", action="store_true", help="Non apre automaticamente il browser")
    parser.add_argument(
        "--refresh-snapshot",
        action="store_true",
        help="Rigenera data/snapshot.js dalla sorgente revisionata configurata, senza avviare il server",
    )
    parser.add_argument("--force", action="store_true", help="Consente di sostituire lo snapshot revisionato")
    return parser


def _dataset_for_launch(args: argparse.Namespace, config: BenchmarkConfig) -> tuple[dict[str, Any], str, int]:
    if args.dataset and args.run_dirs:
        raise DashboardAppError("--dataset non può essere combinato con directory di run")
    if args.dataset:
        return load_dashboard_dataset(args.dataset, root=config.root), "import", 0
    if args.run_dirs:
        runs = resolve_run_directories(args.run_dirs, root=config.root)
        return build_dashboard_data(runs), "local", 0
    runs, skipped = discover_run_directories(config.dashboard.results_directory, root=config.root)
    if runs:
        return build_dashboard_data(runs), "local", len(skipped)
    return load_dashboard_dataset(config.dashboard.snapshot_source, root=config.root), "snapshot", len(skipped)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.refresh_snapshot:
            if args.session or args.dataset or args.run_dirs or args.no_open or args.port is not None:
                raise DashboardAppError("--refresh-snapshot non accetta opzioni di avvio o sorgenti alternative")
            dataset = load_dashboard_dataset(config.dashboard.snapshot_source, root=config.root)
            target = config.dashboard.assets_directory / SNAPSHOT_SCRIPT
            write_snapshot_script(dataset, target, root=config.root, overwrite=args.force)
            print(f"Snapshot dashboard aggiornato: {target.relative_to(config.root)}")
            return 0

        session = None
        if args.session:
            if args.dataset or args.run_dirs:
                raise DashboardAppError("--session richiede una sorgente esclusiva / --session requires an exclusive source")
            from .session_dashboard import load_session_dashboard
            dataset, session = load_session_dashboard(args.session, root=config.root,
                                                      results=config.dashboard.results_directory)
            source, skipped = "local", 0
        else:
            dataset, source, skipped = _dataset_for_launch(args, config)
        port = config.dashboard.port if args.port is None else args.port
        server = create_dashboard_server(
            dataset=dataset,
            assets_directory=config.dashboard.assets_directory,
            host=config.dashboard.host,
            port=port,
            source=source,
            skipped_runs=skipped,
            session=session,
        )
        actual_port = int(server.server_address[1])
        url = f"http://127.0.0.1:{actual_port}/"
        print(f"Dashboard: {url}")
        print(f"Run caricati: {len(dataset['runs'])}; Ctrl+C per terminare")
        if skipped:
            print(f"Run incompatibili ignorati: {skipped}")
        should_open = config.dashboard.open_browser and not args.no_open
        if should_open:
            try:
                opened = webbrowser.open(url, new=2)
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                print("Apertura automatica non disponibile; aprire manualmente l'URL indicato.", file=sys.stderr)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            print("\nDashboard terminata.")
        finally:
            server.server_close()
        return 0
    except (ConfigError, DashboardDataError, DashboardAppError, OSError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 2


__all__ = [
    "DashboardAppError",
    "create_dashboard_server",
    "discover_run_directories",
    "load_dashboard_dataset",
    "main",
    "render_dataset_script",
    "resolve_run_directories",
    "write_snapshot_script",
]
