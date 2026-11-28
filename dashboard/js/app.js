(function () {
  "use strict";

  const Core = window.LocalAgentDashboardCore;
  const I18n = window.LocalAgentDashboardI18n;
  const UI = window.LocalAgentDashboardUI;
  const MAX_FILE_BYTES = 32 * 1024 * 1024;
  const LANGUAGE_KEY = "localagent-dashboard-language";
  const THEME_KEY = "localagent-dashboard-theme";

  const state = {
    dataset: null,
    meta: window.LOCALAGENT_DASHBOARD_META || { source: "snapshot", run_count: 0, skipped_runs: 0 },
    filters: {
      profile: "all",
      model: "all",
      query: "",
      sortBy: "overall_score",
      sortDirection: "desc",
    },
    languagePreference: "auto",
    themePreference: "auto",
    status: { key: "", values: {} },
  };

  function storageGet(key, fallback) {
    try {
      return window.localStorage.getItem(key) || fallback;
    } catch (_error) {
      return fallback;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (_error) {
      return;
    }
  }

  function systemLanguage() {
    return String(window.navigator.language || "en").toLocaleLowerCase().startsWith("it") ? "it" : "en";
  }

  function resolvedLanguage() {
    return state.languagePreference === "auto" ? systemLanguage() : state.languagePreference;
  }

  function resolvedTheme() {
    if (state.themePreference !== "auto") return state.themePreference;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyPreferences() {
    I18n.setLanguage(resolvedLanguage());
    document.documentElement.dataset.theme = resolvedTheme();
    document.documentElement.dataset.themePreference = state.themePreference;
    document.getElementById("language").value = state.languagePreference;
    document.getElementById("theme").value = state.themePreference;
  }

  function option(value, label) {
    const node = document.createElement("option");
    node.value = value;
    node.textContent = label;
    return node;
  }

  function populateFilters() {
    const profile = document.getElementById("profile-filter");
    profile.replaceChildren(
      option("all", I18n.translate("all_profiles")),
      ...state.dataset.profile_order.map((name) => option(name, name))
    );
    profile.value = state.filters.profile;

    const profileView = Core.createDashboardView(state.dataset, {
      profile: state.filters.profile,
      model: "all",
    });
    if (state.filters.model !== "all" && !profileView.availableModels.includes(state.filters.model)) {
      state.filters.model = "all";
    }
    const model = document.getElementById("model-filter");
    model.replaceChildren(
      option("all", I18n.translate("all_models")),
      ...profileView.availableModels.map((name) => option(name, name))
    );
    model.value = state.filters.model;
  }

  function renderStatus() {
    const node = document.getElementById("status");
    node.classList.toggle("status-error", state.status.key === "import_error" || state.status.key === "startup_error");
    const main = state.status.key ? I18n.translate(state.status.key, state.status.values) : "";
    const suffix = state.status.suffixKey
      ? I18n.translate(state.status.suffixKey, state.status.suffixValues)
      : "";
    node.textContent = main + suffix;
  }

  function render() {
    if (!state.dataset) return;
    applyPreferences();
    UI.applyStaticTranslations();
    populateFilters();
    document.getElementById("task-search").value = state.filters.query;
    document.getElementById("sort-field").value = state.filters.sortBy;
    const direction = state.filters.sortDirection === "desc" ? "descending" : "ascending";
    const directionButton = document.getElementById("sort-direction");
    directionButton.textContent = `${state.filters.sortDirection === "desc" ? "↓" : "↑"} ${I18n.translate(direction)}`;
    directionButton.setAttribute("aria-label", I18n.translate("sort_direction", { direction: I18n.translate(direction) }));

    const view = Core.createDashboardView(state.dataset, state.filters);
    UI.renderSource(state.meta, view);
    UI.renderKpis(view);
    UI.renderIntegrity(view);
    UI.renderPreliminary(view);
    UI.renderLeaderboard(view);
    UI.renderComparison(view);
    UI.renderEfficiency(view);
    UI.renderFunnel(view);
    UI.renderSession(state.meta.session, view);
    UI.renderTasks(view, UI.showTaskDialog);
    UI.renderRuns(view);
    renderStatus();
  }

  function setInitialStatus() {
    const source = state.meta.source || "snapshot";
    const skipped = Number(state.meta.skipped_runs) || 0;
    const values = { runs: state.dataset.runs.length };
    let key = source === "local" ? "loaded_local" : source === "import" ? "loaded_import" : "loaded_snapshot";
    if (skipped) {
      state.status = {
        key,
        values,
        suffixKey: "skipped_runs",
        suffixValues: { count: skipped },
      };
      return;
    }
    state.status = { key, values };
  }

  async function readDataset(file) {
    if (file.size > MAX_FILE_BYTES) throw new Error(I18n.translate("file_too_large"));
    try {
      const payload = JSON.parse(await file.text());
      Core.validateDashboardData(payload);
      return payload;
    } catch (error) {
      if (error && error.message === I18n.translate("file_too_large")) throw error;
      throw new Error(I18n.translate("invalid_file"));
    }
  }

  async function importDatasets(files) {
    if (!files.length) return;
    try {
      const imported = await Promise.all([...files].map(readDataset));
      state.dataset = Core.mergeDashboardData([state.dataset, ...imported]);
      state.meta = { source: "import", run_count: state.dataset.runs.length, skipped_runs: 0 };
      state.filters.profile = "all";
      state.filters.model = "all";
      state.status = {
        key: "import_success",
        values: { files: imported.length, runs: state.dataset.runs.length },
      };
    } catch (error) {
      const message = error && typeof error.message === "string" ? error.message.slice(0, 180) : I18n.translate("invalid_file");
      state.status = { key: "import_error", values: { message } };
    }
    document.getElementById("dataset-files").value = "";
    render();
  }

  function bindEvents() {
    document.getElementById("language").addEventListener("change", (event) => {
      state.languagePreference = event.target.value;
      storageSet(LANGUAGE_KEY, state.languagePreference);
      render();
    });
    document.getElementById("theme").addEventListener("change", (event) => {
      state.themePreference = event.target.value;
      storageSet(THEME_KEY, state.themePreference);
      render();
    });
    document.getElementById("profile-filter").addEventListener("change", (event) => {
      state.filters.profile = event.target.value;
      render();
    });
    document.getElementById("model-filter").addEventListener("change", (event) => {
      state.filters.model = event.target.value;
      render();
    });
    document.getElementById("task-search").addEventListener("input", (event) => {
      state.filters.query = event.target.value;
      render();
      document.getElementById("task-search").focus();
    });
    document.getElementById("sort-field").addEventListener("change", (event) => {
      state.filters.sortBy = event.target.value;
      render();
    });
    document.getElementById("sort-direction").addEventListener("click", () => {
      state.filters.sortDirection = state.filters.sortDirection === "desc" ? "asc" : "desc";
      render();
    });
    document.getElementById("reset-filters").addEventListener("click", () => {
      state.filters = {
        profile: "all",
        model: "all",
        query: "",
        sortBy: "overall_score",
        sortDirection: "desc",
      };
      render();
    });
    document.getElementById("dataset-files").addEventListener("change", (event) => importDatasets(event.target.files));
    document.getElementById("dialog-close").addEventListener("click", () => document.getElementById("task-dialog").close());
    document.getElementById("task-dialog").addEventListener("click", (event) => {
      if (event.target === event.currentTarget) event.currentTarget.close();
    });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (state.themePreference === "auto") render();
    });
  }

  function start() {
    try {
      I18n.validateDictionaries();
      state.languagePreference = ["auto", "it", "en"].includes(storageGet(LANGUAGE_KEY, "auto"))
        ? storageGet(LANGUAGE_KEY, "auto")
        : "auto";
      state.themePreference = ["auto", "light", "dark"].includes(storageGet(THEME_KEY, "auto"))
        ? storageGet(THEME_KEY, "auto")
        : "auto";
      Core.validateDashboardData(window.LOCALAGENT_DASHBOARD_DATA);
      state.dataset = window.LOCALAGENT_DASHBOARD_DATA;
      bindEvents();
      applyPreferences();
      setInitialStatus();
      render();
    } catch (error) {
      state.languagePreference = "auto";
      applyPreferences();
      UI.applyStaticTranslations();
      const message = error && typeof error.message === "string" ? error.message.slice(0, 180) : "Unknown error";
      state.status = { key: "startup_error", values: { message } };
      renderStatus();
    }
  }

  document.addEventListener("DOMContentLoaded", start);
})();
