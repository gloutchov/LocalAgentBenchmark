"""Tkinter interface for the guided benchmark funnel."""

from __future__ import annotations

import argparse
import json
import locale
import os
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from .config import BenchmarkConfig, ConfigError, load_config, select_provider
from .guided import GuidedError, GuidedOrchestrator, discover_provider_catalog, find_latest_manifest
from .guided_process import prepare_pi_path
from .multi_provider import ModelSelection, MultiProviderSession, declared_models


ROOT = Path(__file__).resolve().parents[2]
PROVIDER_NAMES = {"ollama": "Ollama", "lmstudio": "LM Studio", "llama_cpp": "llama.cpp", "unsloth": "Unsloth", "colibri": "Colibrì"}

THEME_PALETTES = {
    "dark": {
        "background": "#0b1623",
        "surface": "#122235",
        "foreground": "#edf4fb",
        "muted": "#a9bacb",
        "accent": "#5fd0c2",
        "border": "#5e7c90",
        "selection": "#176b65",
        "selection_text": "#ffffff",
        "disabled_background": "#223345",
        "disabled_foreground": "#a9bacb",
        "progress_track": "#294558",
    },
    "light": {
        "background": "#f4f7fb",
        "surface": "#ffffff",
        "foreground": "#17283a",
        "muted": "#53677a",
        "accent": "#087f73",
        "border": "#9eafbb",
        "selection": "#087f73",
        "selection_text": "#ffffff",
        "disabled_background": "#e2eaf0",
        "disabled_foreground": "#53677a",
        "progress_track": "#c5dbe3",
    },
}

TEXT = {
    "it": {
        "title": "LocalAgent Benchmark · Percorso rapido",
        "subtitle": "Confronta i modelli locali con il funnel smoke → standard → full.",
        "language": "Lingua",
        "theme": "Tema",
        "auto": "Automatico",
        "light": "Chiaro",
        "dark": "Scuro",
        "models": "Modelli locali",
        "model": "Modello",
        "provider": "Provider",
        "size": "Dimensione",
        "thinking": "Thinking",
        "yes": "sì",
        "no": "no",
        "unknown": "?",
        "settings": "Impostazioni effettive",
        "preliminary_toggle": "Preliminary: reattività e affidabilità",
        "thinking_toggle": "Thinking attivo (medium)",
        "sandbox_toggle": "Sandbox OS obbligatoria (required)",
        "sandbox_note_off": "Solo audit: nessun isolamento OS.",
        "sandbox_note_on": "Sandbox OS obbligatoria: l'avvio fallisce se il backend non è disponibile.",
        "settings_line": "thinking: {thinking} · sandbox: {sandbox} · timeout: {timeout}s · warmup: {warmup} · promozione: {first} → {second}",
        "select_all": "Seleziona tutti",
        "select_provider_models": "Tutti del provider",
        "select_none": "Deseleziona tutti",
        "refresh": "Rileva di nuovo",
        "start": "Avvia percorso",
        "cancel": "Annulla",
        "reopen": "Riapri dashboard",
        "status": "Stato e avanzamento",
        "detecting": "Controllo prerequisiti e rilevamento modelli…",
        "ready": "Pronto. Controlla modelli e impostazioni, poi avvia.",
        "running": "Fase {index}/{total}: {profile} · {count} modelli",
        "task": "{model} · {case} · task {current}/{total}",
        "preflight": "Controllo thinking: {model}",
        "pi_compatibility": "Compatibilità Pi verificata",
        "warmup": "Warmup: {model}",
        "confirm_title": "Conferma avvio",
        "confirm": "Avviare il benchmark con {provider}? Il percorso può richiedere molto tempo.",
        "confirm_cancel": "Interrompere il processo corrente? Gli artefatti già prodotti saranno conservati.",
        "choose_model": "Seleziona almeno un modello.",
        "choose_provider": "Per accodare un modello da caricare, seleziona anche un altro provider.",
        "confirm_multi": "Avviare la sessione con {providers}? I provider verranno eseguiti in sequenza.",
        "model_state": "Disponibilità",
        "ready_model": "Pronto",
        "pending_model": "Da caricare",
        "resume_model": "Verifica e riprendi",
        "model_wait": "Carica {model} in {provider}, poi scegli Verifica e riprendi (entro {seconds} s).",
        "model_check": "Verifica di {model} in {provider}…",
        "multi_running": "Fase {index}/{total} · {provider} · {profile}",
        "partial": "Sessione conclusa con esclusioni.",
        "stage_completed": "Completato",
        "stage_excluded": "Escluso",
        "stage_cancelled": "Annullato",
        "stage_failed": "Fallito",
        "stage_model_unavailable": "Modello non disponibile",
        "stage_model_wait_timeout": "Attesa di caricamento scaduta",
        "stage_timeout": "Task scaduta",
        "stage_task_failed": "Task fallita",
        "stage_thinking_control": "Thinking non verificato",
        "stage_integrity": "Integrità non verificata",
        "stage_provider_or_preflight_failed": "Provider o controllo preliminare non disponibile",
        "provider_unavailable": "Provider non disponibili: {providers}",
        "cancelled": "Percorso annullato; gli artefatti diagnosticabili sono stati conservati.",
        "failed": "Percorso interrotto ({code}): {message}",
        "completed": "Percorso completato. La dashboard ufficiale è stata aperta.",
        "dashboard_opened": "Apertura dashboard richiesta.",
        "long_note": "Durata non garantita: dipende da modelli, hardware e casi. I risultati restano locali.",
        "results": "Risultati: {path}",
        "no_models": "Nessun modello disponibile",
        "summary": "Riepilogo bilingue / Bilingual summary",
    },
    "en": {
        "title": "LocalAgent Benchmark · Quick path",
        "subtitle": "Compare local models through the smoke → standard → full funnel.",
        "language": "Language",
        "theme": "Theme",
        "auto": "Automatic",
        "light": "Light",
        "dark": "Dark",
        "models": "Local models",
        "model": "Model",
        "provider": "Provider",
        "size": "Size",
        "thinking": "Thinking",
        "yes": "yes",
        "no": "no",
        "unknown": "?",
        "settings": "Effective settings",
        "preliminary_toggle": "Preliminary: responsiveness and grounding",
        "thinking_toggle": "Enable thinking (medium)",
        "sandbox_toggle": "Require OS sandbox (required)",
        "sandbox_note_off": "Audit only: no OS isolation.",
        "sandbox_note_on": "OS sandbox required: startup fails if the backend is unavailable.",
        "settings_line": "thinking: {thinking} · sandbox: {sandbox} · timeout: {timeout}s · warmup: {warmup} · promotion: {first} → {second}",
        "select_all": "Select all",
        "select_provider_models": "All from provider",
        "select_none": "Select none",
        "refresh": "Detect again",
        "start": "Start quick path",
        "cancel": "Cancel",
        "reopen": "Reopen dashboard",
        "status": "Status and progress",
        "detecting": "Checking prerequisites and detecting models…",
        "ready": "Ready. Review models and settings, then start.",
        "running": "Stage {index}/{total}: {profile} · {count} models",
        "task": "{model} · {case} · task {current}/{total}",
        "preflight": "Thinking check: {model}",
        "pi_compatibility": "Pi compatibility verified",
        "warmup": "Warmup: {model}",
        "confirm_title": "Confirm start",
        "confirm": "Start the benchmark with {provider}? The benchmark may take a long time.",
        "confirm_cancel": "Stop the current process? Existing diagnostic artifacts will be preserved.",
        "choose_model": "Select at least one model.",
        "choose_provider": "To queue a model that needs loading, also select another provider.",
        "confirm_multi": "Start a session with {providers}? Providers will run in sequence.",
        "model_state": "Availability",
        "ready_model": "Ready",
        "pending_model": "Needs loading",
        "resume_model": "Verify and resume",
        "model_wait": "Load {model} in {provider}, then choose Verify and resume (within {seconds} s).",
        "model_check": "Checking {model} in {provider}…",
        "multi_running": "Stage {index}/{total} · {provider} · {profile}",
        "partial": "Session finished with exclusions.",
        "stage_completed": "Completed",
        "stage_excluded": "Excluded",
        "stage_cancelled": "Cancelled",
        "stage_failed": "Failed",
        "stage_model_unavailable": "Model unavailable",
        "stage_model_wait_timeout": "Loading wait timed out",
        "stage_timeout": "Task timed out",
        "stage_task_failed": "Task failed",
        "stage_thinking_control": "Thinking unverified",
        "stage_integrity": "Integrity check failed",
        "stage_provider_or_preflight_failed": "Provider or preflight unavailable",
        "provider_unavailable": "Unavailable providers: {providers}",
        "cancelled": "Quick path cancelled; diagnostic artifacts have been preserved.",
        "failed": "Quick path stopped ({code}): {message}",
        "completed": "Quick path completed. The official dashboard was opened.",
        "dashboard_opened": "Dashboard launch requested.",
        "long_note": "Duration is not guaranteed: it depends on models, hardware and cases. Results stay local.",
        "results": "Results: {path}",
        "no_models": "No models available",
        "summary": "Riepilogo bilingue / Bilingual summary",
    },
}


def detect_language() -> str:
    language = locale.getlocale()[0] or os.environ.get("LANG", "")
    return "it" if language.lower().startswith("it") else "en"


def detect_theme() -> str:
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2,
            )
            if "dark" in result.stdout.lower():
                return "dark"
        except (OSError, subprocess.TimeoutExpired):
            pass
    elif os.name == "nt":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value else "dark"
        except (ImportError, OSError):
            pass
    elif "dark" in os.environ.get("GTK_THEME", "").lower():
        return "dark"
    return "light"


def _preferences_path(path: Path, root: Path | None) -> Path:
    resolved = path.resolve()
    if root is not None:
        project = root.resolve()
        if resolved != project and project not in resolved.parents:
            raise ValueError("Il file preferenze deve restare nella root del progetto")
    if path.is_symlink():
        raise ValueError("Il file preferenze non può essere un symlink")
    return resolved


def load_preferences(path: Path, *, root: Path | None = None) -> dict[str, str]:
    try:
        source = _preferences_path(path, root)
        if source.stat().st_size > 4096:
            return {}
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, allowed in (("language", {"auto", "it", "en"}), ("theme", {"auto", "light", "dark"}))
        if isinstance((value := raw.get(key)), str) and value in allowed
    }


def save_preferences(
    path: Path, preferences: dict[str, str], *, root: Path | None = None
) -> None:
    allowed = {"language": {"auto", "it", "en"}, "theme": {"auto", "light", "dark"}}
    if set(preferences) != set(allowed) or any(
        not isinstance(preferences[key], str) or preferences[key] not in values
        for key, values in allowed.items()
    ):
        raise ValueError("Preferenze lingua/tema non valide")
    target = _preferences_path(path, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _preferences_path(target, root)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(preferences, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _size_text(value: Any) -> str:
    if isinstance(value, int) and value >= 0:
        return f"{value / (1024 ** 3):.1f} GiB"
    return "—"


def _completed_task_progress(phase: int, current: int, total: int) -> float:
    if phase < 1 or total < 1:
        return 0.0
    return min(4.0, phase - 1 + max(0, min(current - 1, total)) / total)


def _sorted_model_indices(
    models: list[dict[str, Any]], column: str, descending: bool
) -> tuple[int, ...]:
    indexed = list(enumerate(models))
    if column == "name":
        indexed.sort(
            key=lambda item: (str(item[1].get("name", "")).casefold(), item[0]),
            reverse=descending,
        )
        return tuple(index for index, _model in indexed)
    if column == "provider":
        indexed.sort(
            key=lambda item: (
                PROVIDER_NAMES[item[1]["provider"]].casefold(),
                item[1]["name"].casefold(),
            ),
            reverse=descending,
        )
        return tuple(index for index, _model in indexed)
    if column == "size":
        known = [
            item
            for item in indexed
            if isinstance(item[1].get("size"), int) and item[1]["size"] >= 0
        ]
        unknown = [item for item in indexed if item not in known]
        known.sort(
            key=lambda item: (
                int(item[1]["size"]),
                str(item[1].get("name", "")).casefold(),
            ),
            reverse=descending,
        )
        unknown.sort(key=lambda item: str(item[1].get("name", "")).casefold())
        return tuple(index for index, _model in (*known, *unknown))
    if column == "thinking":
        known = [
            item
            for item in indexed
            if isinstance(item[1].get("thinking_capable"), bool)
        ]
        unknown = [item for item in indexed if item not in known]
        known.sort(
            key=lambda item: (
                bool(item[1]["thinking_capable"]),
                str(item[1].get("name", "")).casefold(),
            ),
            reverse=descending,
        )
        unknown.sort(key=lambda item: str(item[1].get("name", "")).casefold())
        return tuple(index for index, _model in (*known, *unknown))
    raise ValueError(f"Colonna modello non supportata: {column}")


def _summary(payload: dict[str, Any]) -> str:
    lines = ["Italiano", ""]
    for phase in payload.get("phases", []):
        if not isinstance(phase, dict):
            continue
        ranked = ", ".join(
            f"{row.get('model')} ({row.get('overall_score')})"
            for row in phase.get("leaderboard", [])
            if isinstance(row, dict)
        ) or "nessun classificato"
        promoted = ", ".join(phase.get("promoted", [])) or "—"
        excluded = ", ".join(
            f"{item.get('model')} [{item.get('reason')}]"
            for item in phase.get("exclusions", [])
            if isinstance(item, dict)
        ) or "—"
        if phase.get("profile") == "preliminary":
            lines.append(f"Preliminary: risultati descrittivi; controlli validi: {', '.join(phase.get('eligible_models', []))}; esclusi {excluded}")
            continue
        lines.append(
            f"{phase.get('profile')}: classifica {ranked}; promossi {promoted}; esclusi {excluded}"
        )
    lines.extend(["", "English", ""])
    for phase in payload.get("phases", []):
        if not isinstance(phase, dict):
            continue
        ranked = ", ".join(
            f"{row.get('model')} ({row.get('overall_score')})"
            for row in phase.get("leaderboard", [])
            if isinstance(row, dict)
        ) or "no ranked models"
        promoted = ", ".join(phase.get("promoted", [])) or "—"
        excluded = ", ".join(
            f"{item.get('model')} [{item.get('reason')}]"
            for item in phase.get("exclusions", [])
            if isinstance(item, dict)
        ) or "—"
        if phase.get("profile") == "preliminary":
            lines.append(f"Preliminary: descriptive results; valid controls: {', '.join(phase.get('eligible_models', []))}; excluded {excluded}")
            continue
        lines.append(
            f"{phase.get('profile')}: ranking {ranked}; promoted {promoted}; excluded {excluded}"
        )
    dashboard = payload.get("dashboard", {})
    if isinstance(dashboard, dict):
        lines.extend(["", "Run / Runs:"])
        lines.extend(f"• {path}" for path in dashboard.get("run_directories", []))
    return "\n".join(lines)


class GuidedWindow:
    def __init__(
        self, tk_root: Any, config_path: Path, *, config: BenchmarkConfig | None = None,
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk_root
        self.config_path = config_path.resolve()
        self.config = config if config is not None else load_config(self.config_path)
        provider_kinds = (self.config.provider_kind, *self.config.additional_providers)
        self.orchestrators = {
            kind: GuidedOrchestrator(
                select_provider(self.config, kind), self.config_path,
                provider_override=len(provider_kinds) > 1,
            )
            for kind in provider_kinds
        }
        self.orchestrator = self.orchestrators[self.config.provider_kind]
        self.run_orchestrator: GuidedOrchestrator | MultiProviderSession | None = None
        self.waiting_for_model = False
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.discoveries: dict[str, dict[str, Any]] = {}
        self.unavailable_providers: tuple[str, ...] = ()
        self.discovery_cancel = threading.Event()
        self.models: list[dict[str, Any]] = []
        self.running = False
        self.detecting = False
        self.close_requested = False
        self.latest_manifest = find_latest_manifest(self.config)
        self.sort_column = "name"
        self.sort_descending = False
        preferences = load_preferences(
            self.orchestrator.guided.preferences_file, root=self.config.root
        )
        self.language_choice = tk.StringVar(value=preferences.get("language", "auto"))
        self.theme_choice = tk.StringVar(value=preferences.get("theme", "auto"))
        self.preliminary_enabled = tk.BooleanVar(value=self.orchestrator.guided.preliminary)
        self.phase_total = 4 if self.preliminary_enabled.get() else 3
        self.thinking_enabled = tk.BooleanVar(value=self.config.defaults.thinking != "off")
        self.sandbox_enabled = tk.BooleanVar(value=self.config.defaults.sandbox == "required")
        self.title_var = tk.StringVar()
        self.subtitle_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.results_var = tk.StringVar()
        self.settings_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        self.active_phase = 0
        self._build()
        self._apply_preferences(save=False)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(100, self._poll)
        self.refresh()

    @property
    def language(self) -> str:
        choice = self.language_choice.get()
        return detect_language() if choice == "auto" else choice

    @property
    def theme(self) -> str:
        choice = self.theme_choice.get()
        return detect_theme() if choice == "auto" else choice

    def text(self, key: str, **values: Any) -> str:
        return TEXT[self.language][key].format(**values)

    def _build(self) -> None:
        tk, ttk = self.tk, self.ttk
        self.root.minsize(*self.orchestrator.guided.minimum_size)
        width, height = self.orchestrator.guided.window_size
        self.root.geometry(f"{width}x{height}")
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        title_group = ttk.Frame(header)
        title_group.pack(side="left", fill="x", expand=True)
        ttk.Label(title_group, textvariable=self.title_var, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_group, textvariable=self.subtitle_var, style="Subtitle.TLabel", wraplength=600).pack(anchor="w", pady=(4, 0))
        controls = ttk.Frame(header)
        controls.pack(side="right", padx=(16, 0))
        self.language_label = ttk.Label(controls)
        self.language_label.grid(row=0, column=0, sticky="w")
        self.language_box = ttk.Combobox(
            controls,
            state="readonly",
            width=12,
            values=("auto", "it", "en"),
            textvariable=self.language_choice,
        )
        self.language_box.grid(row=1, column=0, padx=(0, 8))
        self.language_box.bind("<<ComboboxSelected>>", self._preference_changed)
        self.theme_label = ttk.Label(controls)
        self.theme_label.grid(row=0, column=1, sticky="w")
        self.theme_box = ttk.Combobox(
            controls,
            state="readonly",
            width=12,
            values=("auto", "light", "dark"),
            textvariable=self.theme_choice,
        )
        self.theme_box.grid(row=1, column=1)
        self.theme_box.bind("<<ComboboxSelected>>", self._preference_changed)

        self.models_frame = ttk.LabelFrame(outer, padding=12)
        self.models_frame.grid(row=1, column=0, sticky="nsew", pady=(18, 10))
        columns = ("name", "provider", "size", "thinking", "model_state")
        self.model_tree = ttk.Treeview(
            self.models_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=5,
        )
        self.model_tree.column("name", width=370, minwidth=180)
        self.model_tree.column("provider", width=105, minwidth=85)
        self.model_tree.column("model_state", width=105, minwidth=85)
        self.model_tree.column("size", width=110, minwidth=80, anchor="e")
        self.model_tree.column("thinking", width=100, minwidth=80, anchor="center")
        scrollbar = ttk.Scrollbar(self.models_frame, orient="vertical", command=self.model_tree.yview)
        self.model_tree.configure(yscrollcommand=scrollbar.set)
        self.model_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        selection = ttk.Frame(outer)
        selection.grid(row=2, column=0, sticky="ew")
        self.all_button = ttk.Button(selection, command=self._select_all)
        self.all_button.pack(side="left")
        self.none_button = ttk.Button(selection, command=self._select_none)
        self.none_button.pack(side="left", padx=6)
        self.refresh_button = ttk.Button(selection, command=self.refresh)
        self.refresh_button.pack(side="left")

        self.settings_frame = ttk.LabelFrame(outer, padding=12)
        self.settings_frame.grid(row=3, column=0, sticky="ew", pady=10)
        toggles = ttk.Frame(self.settings_frame)
        toggles.pack(fill="x")
        self.preliminary_toggle = ttk.Checkbutton(toggles, variable=self.preliminary_enabled)
        self.preliminary_toggle.pack(anchor="w", pady=(0, 6))
        self.thinking_toggle = ttk.Checkbutton(
            toggles, variable=self.thinking_enabled, command=self._render_settings
        )
        self.thinking_toggle.pack(side="left", padx=(0, 24))
        self.sandbox_toggle = ttk.Checkbutton(
            toggles, variable=self.sandbox_enabled, command=self._render_settings
        )
        self.sandbox_toggle.pack(side="left")
        ttk.Label(self.settings_frame, textvariable=self.settings_var, justify="left", wraplength=820).pack(anchor="w")
        self.sandbox_note = ttk.Label(self.settings_frame, style="Note.TLabel", wraplength=820)
        self.sandbox_note.pack(anchor="w", pady=(4, 0))
        self.note_label = ttk.Label(self.settings_frame, style="Note.TLabel", wraplength=820)
        self.note_label.pack(anchor="w", pady=(6, 0))

        self.status_frame = ttk.LabelFrame(outer, padding=12)
        self.status_frame.grid(row=4, column=0, sticky="ew")
        ttk.Label(self.status_frame, textvariable=self.status_var).pack(anchor="w")
        self.progress = ttk.Progressbar(
            self.status_frame,
            maximum=3,
            variable=self.progress_var,
            mode="determinate",
        )
        self.progress.pack(fill="x", pady=7)
        ttk.Label(self.status_frame, textvariable=self.detail_var, wraplength=820).pack(anchor="w")
        ttk.Label(self.status_frame, textvariable=self.results_var, style="Note.TLabel", wraplength=820).pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        self.start_button = ttk.Button(actions, command=self.start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.reopen_button = ttk.Button(actions, command=self.reopen)
        self.reopen_button.pack(side="right")

    def _apply_preferences(self, *, save: bool = True) -> None:
        ttk = self.ttk
        palette = THEME_PALETTES[self.theme]
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=palette["background"], foreground=palette["foreground"], fieldbackground=palette["surface"])
        style.configure("TFrame", background=palette["background"])
        style.configure("TLabelframe", background=palette["background"], foreground=palette["foreground"], bordercolor=palette["border"])
        style.configure("TLabelframe.Label", background=palette["background"], foreground=palette["accent"])
        style.configure("TLabel", background=palette["background"], foreground=palette["foreground"])
        style.configure("TCheckbutton", background=palette["background"], foreground=palette["foreground"])
        style.map("TCheckbutton", background=[("active", palette["background"])], foreground=[("disabled", palette["muted"])])
        style.configure(
            "TCombobox",
            background=palette["surface"],
            fieldbackground=palette["surface"],
            foreground=palette["foreground"],
            arrowcolor=palette["foreground"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            troughcolor=palette["surface"],
            selectbackground=palette["surface"],
            selectforeground=palette["foreground"],
        )
        style.map(
            "TCombobox",
            background=[
                ("disabled", palette["disabled_background"]),
                ("readonly", palette["surface"]),
            ],
            fieldbackground=[
                ("disabled", palette["disabled_background"]),
                ("readonly", palette["surface"]),
            ],
            foreground=[
                ("disabled", palette["disabled_foreground"]),
                ("readonly", palette["foreground"]),
            ],
            arrowcolor=[
                ("disabled", palette["disabled_foreground"]),
                ("readonly", palette["foreground"]),
            ],
            selectbackground=[("readonly", palette["surface"])],
            selectforeground=[("readonly", palette["foreground"])],
        )
        for option, color in {
            "background": palette["surface"],
            "foreground": palette["foreground"],
            "selectBackground": palette["selection"],
            "selectForeground": palette["selection_text"],
        }.items():
            self.root.option_add(f"*TCombobox*Listbox.{option}", color)
        style.configure(
            "TButton",
            background=palette["surface"],
            foreground=palette["foreground"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        style.map(
            "TButton",
            background=[
                ("disabled", palette["disabled_background"]),
                ("pressed", palette["selection"]),
                ("active", palette["progress_track"]),
            ],
            foreground=[
                ("disabled", palette["disabled_foreground"]),
                ("pressed", palette["selection_text"]),
            ],
        )
        style.configure("Title.TLabel", font=("TkDefaultFont", 20, "bold"), foreground=palette["accent"])
        style.configure("Subtitle.TLabel", font=("TkDefaultFont", 11), foreground=palette["muted"])
        style.configure("Note.TLabel", foreground=palette["muted"])
        style.configure("Treeview", background=palette["surface"], fieldbackground=palette["surface"], foreground=palette["foreground"], rowheight=26)
        style.configure(
            "Treeview.Heading",
            background=palette["background"],
            foreground=palette["foreground"],
            bordercolor=palette["border"],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", palette["progress_track"])],
            foreground=[("active", palette["foreground"])],
        )
        style.map(
            "Treeview",
            background=[("selected", palette["selection"])],
            foreground=[("selected", palette["selection_text"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=palette["surface"],
            troughcolor=palette["background"],
            arrowcolor=palette["foreground"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background=palette["accent"],
            troughcolor=palette["progress_track"],
            bordercolor=palette["border"],
            lightcolor=palette["accent"],
            darkcolor=palette["accent"],
            thickness=14,
        )
        self.root.configure(background=palette["background"])
        self.root.title(self.text("title"))
        self.title_var.set(self.text("title"))
        self.subtitle_var.set(self.text("subtitle"))
        self.language_label.configure(text=self.text("language"))
        self.theme_label.configure(text=self.text("theme"))
        self.models_frame.configure(text=self.text("models"))
        self._configure_model_headings()
        if self.models:
            self._render_model_rows(set(self._selected_model_indices()))
        self.all_button.configure(text=self.text("select_all"))
        self.none_button.configure(text=self.text("select_none"))
        self.refresh_button.configure(text=self.text("refresh"))
        self.settings_frame.configure(text=self.text("settings"))
        self.preliminary_toggle.configure(text=self.text("preliminary_toggle"))
        self.thinking_toggle.configure(text=self.text("thinking_toggle"))
        self.sandbox_toggle.configure(text=self.text("sandbox_toggle"))
        self._render_settings()
        self.note_label.configure(text=self.text("long_note"))
        self.status_frame.configure(text=self.text("status"))
        self.start_button.configure(text=self.text("resume_model" if self.waiting_for_model else "start"))
        self.cancel_button.configure(text=self.text("cancel"))
        self.reopen_button.configure(text=self.text("reopen"))
        if not self.running and self.discoveries:
            self._render_ready_status()
        self.reopen_button.configure(
            state="normal" if self.latest_manifest and not self.running else "disabled"
        )
        if save:
            save_preferences(
                self.orchestrator.guided.preferences_file,
                {"language": self.language_choice.get(), "theme": self.theme_choice.get()},
                root=self.config.root,
            )

    def _preference_changed(self, _event: Any = None) -> None:
        self._apply_preferences()

    def _set_busy(self, busy: bool) -> None:
        self.running = busy
        normal = "disabled" if busy else "normal"
        self.start_button.configure(state=normal if self.discoveries else "disabled")
        self.refresh_button.configure(state="disabled" if self.detecting else normal)
        self.all_button.configure(state=normal)
        self.none_button.configure(state=normal)
        self.preliminary_toggle.configure(state=normal if self.config.preliminary is not None and "preliminary" in self.config.profiles else "disabled")
        self.thinking_toggle.configure(state=normal)
        self.sandbox_toggle.configure(state=normal)
        self.cancel_button.configure(state="normal" if busy or self.detecting else "disabled")
        self.reopen_button.configure(
            state="normal" if self.latest_manifest and not busy else "disabled"
        )

    def refresh(self) -> None:
        if self.running or self.detecting:
            return
        self.detecting = True
        self.discoveries = {}
        self.unavailable_providers = ()
        self.discovery_cancel.clear()
        self.models = []
        self.active_phase = 0
        self.progress_var.set(0)
        self.model_tree.delete(*self.model_tree.get_children())
        self.status_var.set(self.text("detecting"))
        self.detail_var.set("")
        self._render_settings()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.refresh_button.configure(state="disabled")

        def work() -> None:
            try:
                prepare_pi_path(
                    self.config.pi_command, cwd=self.config.root,
                    timeout=self.config.defaults.pi_contract_timeout_seconds,
                )
                discoveries, errors = discover_provider_catalog(self.orchestrators, self.discovery_cancel)
            except GuidedError as exc:
                self.events.put(
                    {
                        "type": "error",
                        "code": exc.code,
                        "message": str(exc),
                        "payload": exc.context,
                    }
                )
            except Exception as exc:
                self.events.put({"type": "error", "code": "prerequisites", "message": str(exc)})
            else:
                self.events.put({"type": "discovery", "discoveries": discoveries, "errors": errors})

        threading.Thread(target=work, daemon=True).start()

    def _render_settings(self) -> None:
        settings = self.orchestrator.settings_summary(
            thinking="medium" if self.thinking_enabled.get() else "off",
            sandbox="required" if self.sandbox_enabled.get() else "audit",
        )
        self.sandbox_note.configure(text=self.text(
            "sandbox_note_on" if self.sandbox_enabled.get() else "sandbox_note_off"
        ))
        self.settings_var.set(
            self.text(
                "settings_line",
                thinking=settings["thinking"],
                sandbox=settings["sandbox"],
                timeout=settings["timeout_seconds"],
                warmup=self.text("yes") if settings["warmup"] else self.text("no"),
                first=settings["promotion_limits"][0],
                second=settings["promotion_limits"][1],
            )
        )

    def _render_ready_status(self) -> None:
        self.status_var.set(self.text("ready"))
        if self.unavailable_providers:
            providers = ", ".join(PROVIDER_NAMES[kind] for kind in self.unavailable_providers)
            self.detail_var.set(self.text("provider_unavailable", providers=providers))
        else:
            self.detail_var.set(self.text("pi_compatibility"))

    def _populate_models(self, discoveries: dict[str, dict[str, Any]], *, can_start: bool = True) -> None:
        self.detecting = False
        self.discoveries = discoveries if can_start else {}
        self.models = [
            {**model, "provider": kind}
            for kind, payload in discoveries.items()
            for model in payload["models"]
        ]
        if can_start:
            ready = {(row["provider"], row["name"]) for row in self.models}
            for kind, orchestrator in self.orchestrators.items():
                pending = declared_models(orchestrator.config)
                self.models.extend({"provider": kind, "name": name, "requires_load": True}
                                   for name in pending if (kind, name) not in ready)
        first_kind = next(iter(discoveries), None)
        self._render_model_rows({index for index, model in enumerate(self.models)
                                 if model["provider"] == first_kind and not model.get("requires_load")})
        self._render_settings()
        self._render_ready_status()
        self._set_busy(False)

    def _configure_model_headings(self) -> None:
        labels = {
            "name": self.text("model"),
            "provider": self.text("provider"),
            "size": self.text("size"),
            "thinking": self.text("thinking"),
        }
        for column, label in labels.items():
            arrow = " ▼" if self.sort_descending else " ▲"
            text = f"{label}{arrow}" if column == self.sort_column else label
            self.model_tree.heading(
                column,
                text=text,
                command=lambda selected=column: self._sort_models(selected),
            )

    def _sort_models(self, column: str) -> None:
        selected = set(self._selected_model_indices())
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self._render_model_rows(selected)

    def _render_model_rows(self, selected_indices: set[int]) -> None:
        self.model_tree.delete(*self.model_tree.get_children())
        selected_items: list[str] = []
        for index in _sorted_model_indices(
            self.models, self.sort_column, self.sort_descending
        ):
            model = self.models[index]
            thinking = model.get("thinking_capable")
            thinking_text = (
                self.text("yes")
                if thinking is True
                else self.text("no") if thinking is False else self.text("unknown")
            )
            self.model_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(model["name"], PROVIDER_NAMES[model["provider"]], _size_text(model.get("size")), thinking_text,
                        self.text("pending_model" if model.get("requires_load") else "ready_model")),
            )
            if index in selected_indices:
                selected_items.append(str(index))
        self.model_tree.selection_set(selected_items)
        self._configure_model_headings()
        self.model_tree.heading("model_state", text=self.text("model_state"))

    def _select_all(self) -> None:
        self.model_tree.selection_set(self.model_tree.get_children())

    def _select_none(self) -> None:
        self.model_tree.selection_remove(self.model_tree.selection())

    def _selected_model_indices(self) -> list[int]:
        return [int(item) for item in self.model_tree.selection()]

    def start(self) -> None:
        from tkinter import messagebox

        if self.waiting_for_model and isinstance(self.run_orchestrator, MultiProviderSession):
            self.start_button.configure(state="disabled")
            self.run_orchestrator.resume()
            return
        if not self.discoveries or self.running:
            return
        models = [self.models[index] for index in self._selected_model_indices()]
        if not models:
            messagebox.showwarning(self.text("confirm_title"), self.text("choose_model"), parent=self.root)
            return
        kinds = list(dict.fromkeys(model["provider"] for model in models))
        if len(kinds) > 1:
            confirmation = self.text("confirm_multi", providers=", ".join(PROVIDER_NAMES[kind] for kind in kinds))
            orchestrator = MultiProviderSession(self.orchestrator)
        else:
            if any(model.get("requires_load") for model in models):
                messagebox.showwarning(self.text("confirm_title"), self.text("choose_provider"), parent=self.root)
                return
            confirmation = self.text("confirm", provider=PROVIDER_NAMES[kinds[0]])
            orchestrator = self.orchestrators[kinds[0]]
        if not messagebox.askyesno(self.text("confirm_title"), confirmation, parent=self.root):
            return
        orchestrator.manifest_path = None
        orchestrator.cancel_event.clear()
        self.run_orchestrator = orchestrator
        self._set_busy(True)
        self.active_phase = 0
        self.progress_var.set(0)
        self.detail_var.set("")
        thinking_mode = "medium" if self.thinking_enabled.get() else "off"
        sandbox_mode = "required" if self.sandbox_enabled.get() else "audit"

        include_preliminary = self.preliminary_enabled.get()
        self.phase_total = 4 if include_preliminary else 3
        self.progress.configure(maximum=self.phase_total)

        def work() -> None:
            try:
                settings = dict(thinking=thinking_mode, sandbox=sandbox_mode,
                                preliminary=include_preliminary, callback=self.events.put)
                if isinstance(orchestrator, MultiProviderSession):
                    selected = [ModelSelection(model["provider"], model["name"]) for model in models]
                    manifest = orchestrator.run(selected, **settings)
                else:
                    manifest = orchestrator.run([m["name"] for m in models], self.discoveries[kinds[0]], **settings)
            except GuidedError as exc:
                self.events.put({"type": "error", "code": exc.code, "message": str(exc)})
            except Exception as exc:
                self.events.put({"type": "error", "code": "unexpected", "message": str(exc)})
            else:
                self.events.put({"type": "run_done", "manifest": str(manifest)})

        threading.Thread(target=work, daemon=True).start()

    def cancel(self) -> None:
        from tkinter import messagebox

        if (self.running or self.detecting) and messagebox.askyesno(
            self.text("confirm_title"), self.text("confirm_cancel"), parent=self.root
        ):
            if self.detecting:
                self.discovery_cancel.set()
            elif self.run_orchestrator is not None:
                self.run_orchestrator.cancel()
            self.cancel_button.configure(state="disabled")

    def reopen(self) -> None:
        if not self.latest_manifest or self.running:
            return
        self.reopen_button.configure(state="disabled")

        def work() -> None:
            try:
                self.orchestrator.reopen_dashboard(self.latest_manifest)
            except GuidedError as exc:
                self.events.put({"type": "error", "code": exc.code, "message": str(exc), "reopen": True})
            except Exception as exc:
                self.events.put(
                    {
                        "type": "error",
                        "code": "dashboard_failed",
                        "message": str(exc),
                        "reopen": True,
                    }
                )
            else:
                self.events.put({"type": "dashboard_opened"})

        threading.Thread(target=work, daemon=True).start()

    def _show_summary(self, manifest: Path) -> None:
        from tkinter import messagebox

        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if payload.get("status") == "partial":
            self.status_var.set(self.text("partial"))
        if payload.get("mode") == "multi_provider":
            lines = []
            for row in payload.get("phases", []):
                provider = PROVIDER_NAMES.get(row["provider"], row["provider"])
                exclusions = {item["model"]: item["reason"] for item in row.get("exclusions", [])}
                for model in row["models"]:
                    reason = exclusions.get(model) or row.get("reason") or row["status"]
                    key = f"stage_{reason}"
                    label = self.text(key if key in TEXT[self.language] else "stage_excluded")
                    lines.append(f"{provider} · {row['profile']} · {model} · {label}")
            messagebox.showinfo(self.text("summary"), "\n".join(lines), parent=self.root)
        else:
            messagebox.showinfo(self.text("summary"), _summary(payload), parent=self.root)

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "discovery":
            discoveries = event["discoveries"]
            errors = event["errors"]
            self.unavailable_providers = tuple(errors)
            if discoveries:
                self._populate_models(discoveries)
            else:
                provider, error = next(iter(errors.items()))
                self._handle({"type": "error", "code": error.code, "message": str(error),
                              "payload": error.context, "provider": provider})
        elif kind == "phase":
            if "provider" in event:
                self.phase_total = int(event["total"])
                self.progress.configure(maximum=self.phase_total)
            self.active_phase = int(event["index"])
            self.progress_var.set(self.active_phase - 1)
            self.status_var.set(
                self.text(
                    "multi_running" if "provider" in event else "running",
                    index=event["index"], total=event["total"],
                    provider=PROVIDER_NAMES.get(event.get("provider"), ""),
                    profile=event["profile"],
                    count=len(event["models"]),
                )
            )
            self.results_var.set(self.text("results", path=event["run_directory"]))
        elif kind in {"model_wait", "model_check", "model_wait_done"}:
            self.waiting_for_model = kind == "model_wait"
            self.start_button.configure(text=self.text("resume_model" if self.waiting_for_model else "start"),
                                        state="normal" if self.waiting_for_model else "disabled")
            if self.waiting_for_model:
                self.start_button.focus_set()
            if kind == "model_wait_done":
                self.detail_var.set("")
            else:
                self.detail_var.set(self.text(kind, model=event["model"], seconds=event.get("seconds"),
                                              provider=PROVIDER_NAMES[event["provider"]]))
        elif kind == "task":
            self.progress_var.set(
                max(
                    self.progress_var.get(),
                    _completed_task_progress(
                        self.active_phase, int(event["current"]), int(event["total"])
                    ),
                )
            )
            self.detail_var.set(
                self.text(
                    "task",
                    model=event["model"],
                    case=event["case"],
                    current=event["current"],
                    total=event["total"],
                )
            )
        elif kind in {"preflight", "warmup"}:
            self.detail_var.set(self.text(kind, model=event["model"]))
        elif kind == "error":
            from tkinter import messagebox

            self.detecting = False

            code = str(event.get("code", "unexpected"))
            message = str(event.get("message", ""))
            payload = event.get("payload")
            if isinstance(payload, dict) and isinstance(payload.get("models"), list):
                provider = event.get("provider", self.config.provider_kind)
                self._populate_models({provider: payload}, can_start=False)
            if code == "cancelled":
                self.status_var.set(self.text("cancelled"))
            else:
                self.status_var.set(self.text("failed", code=code, message=message))
                messagebox.showerror(self.text("title"), self.status_var.get(), parent=self.root)
            if not event.get("reopen"):
                self._set_busy(False)
            if self.run_orchestrator is not None:
                self.latest_manifest = self.run_orchestrator.manifest_path or self.latest_manifest
                self.run_orchestrator = None
            self._apply_preferences(save=False)
        elif kind == "run_done":
            self.run_orchestrator = None
            self.progress_var.set(self.phase_total)
            self.status_var.set(self.text("completed"))
            self.detail_var.set("")
            self.latest_manifest = Path(event["manifest"])
            self.results_var.set(self.text("results", path=str(self.latest_manifest.parent.relative_to(self.config.root))))
            self._set_busy(False)
            self._apply_preferences(save=False)
            self._show_summary(self.latest_manifest)
        elif kind == "dashboard_opened":
            self.status_var.set(self.text("dashboard_opened"))
            self._apply_preferences(save=False)

    def _poll(self) -> None:
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        if self.close_requested and not (self.running or self.detecting):
            self.root.destroy()
            return
        self.root.after(100, self._poll)

    def _close(self) -> None:
        from tkinter import messagebox

        if self.running or self.detecting:
            if not messagebox.askyesno(
                self.text("confirm_title"), self.text("confirm_cancel"), parent=self.root
            ):
                return
            self.close_requested = True
            if self.detecting:
                self.discovery_cancel.set()
            elif self.run_orchestrator is not None:
                self.run_orchestrator.cancel()
            return
        self.root.destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LocalAgent Benchmark guided funnel")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except (ConfigError, OSError) as exc:
        print(f"Errore configurazione / Configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print("Errore: Tkinter non è disponibile in questa installazione Python.", file=sys.stderr)
        return 2
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Errore: interfaccia grafica non disponibile: {exc}", file=sys.stderr)
        return 2
    try:
        GuidedWindow(root, args.config, config=config)
    except (ConfigError, GuidedError, OSError) as exc:
        root.withdraw()
        messagebox.showerror("LocalAgent Benchmark", str(exc), parent=root)
        root.destroy()
        return 2
    root.mainloop()
    return 0


__all__ = [
    "GuidedWindow",
    "TEXT",
    "detect_language",
    "detect_theme",
    "load_preferences",
    "main",
    "save_preferences",
]
