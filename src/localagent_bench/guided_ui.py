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

from .config import ConfigError, load_config
from .guided import GuidedError, GuidedOrchestrator, find_latest_manifest


ROOT = Path(__file__).resolve().parents[2]

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
        "size": "Dimensione",
        "thinking": "Thinking",
        "yes": "sì",
        "no": "no",
        "unknown": "?",
        "settings": "Impostazioni effettive",
        "thinking_toggle": "Thinking attivo (medium)",
        "sandbox_toggle": "Sandbox OS obbligatoria (required)",
        "sandbox_note_off": "Solo audit: nessun isolamento OS.",
        "sandbox_note_on": "Sandbox OS obbligatoria: l'avvio fallisce se il backend non è disponibile.",
        "settings_line": "thinking: {thinking} · sandbox: {sandbox} · timeout: {timeout}s · warmup: {warmup} · promozione: {first} → {second}",
        "select_all": "Seleziona tutti",
        "select_none": "Deseleziona tutti",
        "refresh": "Rileva di nuovo",
        "start": "Avvia percorso",
        "cancel": "Annulla",
        "reopen": "Riapri dashboard",
        "status": "Stato e avanzamento",
        "detecting": "Controllo prerequisiti e rilevamento modelli…",
        "ready": "Pronto. Controlla modelli e impostazioni, poi avvia.",
        "running": "Fase {index}/3: {profile} · {count} modelli",
        "task": "{model} · {case} · task {current}/{total}",
        "preflight": "Controllo thinking: {model}",
        "pi_compatibility": "Compatibilità Pi verificata",
        "warmup": "Warmup: {model}",
        "confirm_title": "Conferma avvio",
        "confirm": "Il benchmark può richiedere molto tempo e userà i modelli selezionati in tre fasi. Avviare ora?",
        "confirm_cancel": "Interrompere il processo corrente? Gli artefatti già prodotti saranno conservati.",
        "choose_model": "Seleziona almeno un modello.",
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
        "size": "Size",
        "thinking": "Thinking",
        "yes": "yes",
        "no": "no",
        "unknown": "?",
        "settings": "Effective settings",
        "thinking_toggle": "Enable thinking (medium)",
        "sandbox_toggle": "Require OS sandbox (required)",
        "sandbox_note_off": "Audit only: no OS isolation.",
        "sandbox_note_on": "OS sandbox required: startup fails if the backend is unavailable.",
        "settings_line": "thinking: {thinking} · sandbox: {sandbox} · timeout: {timeout}s · warmup: {warmup} · promotion: {first} → {second}",
        "select_all": "Select all",
        "select_none": "Select none",
        "refresh": "Detect again",
        "start": "Start quick path",
        "cancel": "Cancel",
        "reopen": "Reopen dashboard",
        "status": "Status and progress",
        "detecting": "Checking prerequisites and detecting models…",
        "ready": "Ready. Review models and settings, then start.",
        "running": "Stage {index}/3: {profile} · {count} models",
        "task": "{model} · {case} · task {current}/{total}",
        "preflight": "Thinking check: {model}",
        "pi_compatibility": "Pi compatibility verified",
        "warmup": "Warmup: {model}",
        "confirm_title": "Confirm start",
        "confirm": "The benchmark can take a long time and will use the selected models in three stages. Start now?",
        "confirm_cancel": "Stop the current process? Existing diagnostic artifacts will be preserved.",
        "choose_model": "Select at least one model.",
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
        lines.append(
            f"{phase.get('profile')}: ranking {ranked}; promoted {promoted}; excluded {excluded}"
        )
    dashboard = payload.get("dashboard", {})
    if isinstance(dashboard, dict):
        lines.extend(["", "Run / Runs:"])
        lines.extend(f"• {path}" for path in dashboard.get("run_directories", []))
    return "\n".join(lines)


class GuidedWindow:
    def __init__(self, tk_root: Any, config_path: Path) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk_root
        self.config_path = config_path.resolve()
        self.config = load_config(self.config_path)
        self.orchestrator = GuidedOrchestrator(self.config, self.config_path)
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.discovery: dict[str, Any] | None = None
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
        self.thinking_enabled = tk.BooleanVar(value=self.config.defaults.thinking != "off")
        self.sandbox_enabled = tk.BooleanVar(value=self.config.defaults.sandbox == "required")
        self.title_var = tk.StringVar()
        self.subtitle_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.detail_var = tk.StringVar()
        self.results_var = tk.StringVar()
        self.settings_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
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
        self.root.minsize(760, 620)
        self.root.geometry("900x720")
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
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
        self.models_frame.pack(fill="both", expand=True, pady=(18, 10))
        columns = ("name", "size", "thinking")
        self.model_tree = ttk.Treeview(
            self.models_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=5,
        )
        self.model_tree.column("name", width=430, minwidth=180)
        self.model_tree.column("size", width=110, minwidth=80, anchor="e")
        self.model_tree.column("thinking", width=100, minwidth=80, anchor="center")
        scrollbar = ttk.Scrollbar(self.models_frame, orient="vertical", command=self.model_tree.yview)
        self.model_tree.configure(yscrollcommand=scrollbar.set)
        self.model_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        selection = ttk.Frame(outer)
        selection.pack(fill="x")
        self.all_button = ttk.Button(selection, command=self._select_all)
        self.all_button.pack(side="left")
        self.none_button = ttk.Button(selection, command=self._select_none)
        self.none_button.pack(side="left", padx=6)
        self.refresh_button = ttk.Button(selection, command=self.refresh)
        self.refresh_button.pack(side="left")

        self.settings_frame = ttk.LabelFrame(outer, padding=12)
        self.settings_frame.pack(fill="x", pady=10)
        toggles = ttk.Frame(self.settings_frame)
        toggles.pack(fill="x")
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
        self.status_frame.pack(fill="x")
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
        actions.pack(fill="x", pady=(14, 0))
        self.start_button = ttk.Button(actions, command=self.start)
        self.start_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.reopen_button = ttk.Button(actions, command=self.reopen)
        self.reopen_button.pack(side="right")

    def _apply_preferences(self, *, save: bool = True) -> None:
        ttk = self.ttk
        dark = self.theme == "dark"
        palette = {
            "background": "#0b1623" if dark else "#f4f7fb",
            "surface": "#122235" if dark else "#ffffff",
            "foreground": "#edf4fb" if dark else "#17283a",
            "muted": "#a9bacb" if dark else "#53677a",
            "accent": "#5fd0c2" if dark else "#087f73",
        }
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=palette["background"], foreground=palette["foreground"], fieldbackground=palette["surface"])
        style.configure("TFrame", background=palette["background"])
        style.configure("TLabelframe", background=palette["background"], foreground=palette["foreground"])
        style.configure("TLabelframe.Label", background=palette["background"], foreground=palette["accent"])
        style.configure("TLabel", background=palette["background"], foreground=palette["foreground"])
        style.configure("TCheckbutton", background=palette["background"], foreground=palette["foreground"])
        style.map("TCheckbutton", background=[("active", palette["background"])], foreground=[("disabled", palette["muted"])])
        style.configure("Title.TLabel", font=("TkDefaultFont", 20, "bold"), foreground=palette["accent"])
        style.configure("Subtitle.TLabel", font=("TkDefaultFont", 11), foreground=palette["muted"])
        style.configure("Note.TLabel", foreground=palette["muted"])
        style.configure("Treeview", background=palette["surface"], fieldbackground=palette["surface"], foreground=palette["foreground"], rowheight=26)
        style.configure("Treeview.Heading", background=palette["background"], foreground=palette["foreground"])
        style.map("Treeview", background=[("selected", palette["accent"])], foreground=[("selected", "#07120f")])
        self.root.configure(background=palette["background"])
        self.root.title(self.text("title"))
        self.title_var.set(self.text("title"))
        self.subtitle_var.set(self.text("subtitle"))
        self.language_label.configure(text=self.text("language"))
        self.theme_label.configure(text=self.text("theme"))
        self.models_frame.configure(text=self.text("models"))
        self._configure_model_headings()
        if self.models:
            self._render_model_rows(set(self._selected_models()))
        self.all_button.configure(text=self.text("select_all"))
        self.none_button.configure(text=self.text("select_none"))
        self.refresh_button.configure(text=self.text("refresh"))
        self.settings_frame.configure(text=self.text("settings"))
        self.thinking_toggle.configure(text=self.text("thinking_toggle"))
        self.sandbox_toggle.configure(text=self.text("sandbox_toggle"))
        self._render_settings()
        self.note_label.configure(text=self.text("long_note"))
        self.status_frame.configure(text=self.text("status"))
        self.start_button.configure(text=self.text("start"))
        self.cancel_button.configure(text=self.text("cancel"))
        self.reopen_button.configure(text=self.text("reopen"))
        if not self.running and self.discovery:
            self.status_var.set(self.text("ready"))
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
        self.start_button.configure(state=normal if self.discovery else "disabled")
        self.refresh_button.configure(state="disabled" if self.detecting else normal)
        self.all_button.configure(state=normal)
        self.none_button.configure(state=normal)
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
        self.discovery = None
        self.models = []
        self.model_tree.delete(*self.model_tree.get_children())
        self.status_var.set(self.text("detecting"))
        self.detail_var.set("")
        self._render_settings()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.refresh_button.configure(state="disabled")

        def work() -> None:
            try:
                payload = self.orchestrator.discover()
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
                self.events.put({"type": "discovery", "payload": payload})

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

    def _populate_models(self, payload: dict[str, Any], *, can_start: bool = True) -> None:
        self.detecting = False
        self.discovery = payload if can_start else None
        self.models = list(payload["models"])
        self._render_model_rows({model["name"] for model in self.models})
        self._render_settings()
        self.status_var.set(self.text("ready"))
        self.detail_var.set(self.text("pi_compatibility") if can_start else "")
        self._set_busy(False)

    def _configure_model_headings(self) -> None:
        labels = {
            "name": self.text("model"),
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
        selected = set(self._selected_models())
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self._render_model_rows(selected)

    def _render_model_rows(self, selected_names: set[str]) -> None:
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
                values=(model["name"], _size_text(model.get("size")), thinking_text),
            )
            if model["name"] in selected_names:
                selected_items.append(str(index))
        self.model_tree.selection_set(selected_items)
        self._configure_model_headings()

    def _select_all(self) -> None:
        children = self.model_tree.get_children()
        self.model_tree.selection_set(children)

    def _select_none(self) -> None:
        self.model_tree.selection_remove(self.model_tree.selection())

    def _selected_models(self) -> list[str]:
        return [self.models[int(item)]["name"] for item in self.model_tree.selection()]

    def start(self) -> None:
        from tkinter import messagebox

        if not self.discovery or self.running:
            return
        selected = self._selected_models()
        if not selected:
            messagebox.showwarning(self.text("confirm_title"), self.text("choose_model"), parent=self.root)
            return
        if not messagebox.askyesno(
            self.text("confirm_title"), self.text("confirm"), parent=self.root
        ):
            return
        self._set_busy(True)
        self.progress_var.set(0)
        self.detail_var.set("")
        discovery = self.discovery
        thinking_mode = "medium" if self.thinking_enabled.get() else "off"
        sandbox_mode = "required" if self.sandbox_enabled.get() else "audit"

        def work() -> None:
            try:
                manifest = self.orchestrator.run(
                    selected, discovery, thinking=thinking_mode, sandbox=sandbox_mode,
                    callback=self.events.put,
                )
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
            self.orchestrator.cancel()
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
        messagebox.showinfo(self.text("summary"), _summary(payload), parent=self.root)

    def _handle(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "discovery":
            self._populate_models(event["payload"])
        elif kind == "phase":
            self.progress_var.set(int(event["index"]) - 1)
            self.status_var.set(
                self.text(
                    "running",
                    index=event["index"],
                    profile=event["profile"],
                    count=len(event["models"]),
                )
            )
            self.results_var.set(self.text("results", path=event["run_directory"]))
        elif kind == "task":
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
                self._populate_models(payload, can_start=False)
            if code == "cancelled":
                self.status_var.set(self.text("cancelled"))
            else:
                self.status_var.set(self.text("failed", code=code, message=message))
                messagebox.showerror(self.text("title"), self.status_var.get(), parent=self.root)
            if not event.get("reopen"):
                self._set_busy(False)
            self.latest_manifest = self.orchestrator.manifest_path or self.latest_manifest
            self._apply_preferences(save=False)
        elif kind == "run_done":
            self.progress_var.set(3)
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
        if self.close_requested and not self.running:
            self.root.destroy()
            return
        self.root.after(100, self._poll)

    def _close(self) -> None:
        from tkinter import messagebox

        if self.running:
            if not messagebox.askyesno(
                self.text("confirm_title"), self.text("confirm_cancel"), parent=self.root
            ):
                return
            self.close_requested = True
            self.orchestrator.cancel()
            return
        self.root.destroy()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LocalAgent Benchmark guided funnel")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
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
        GuidedWindow(root, args.config)
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
