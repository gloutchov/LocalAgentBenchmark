(function () {
  "use strict";

  const i18n = window.LocalAgentSiteI18n;
  const prefs = window.LocalAgentSitePreferences;
  const languageSelect = document.querySelector("[data-language-select]");
  const themeSelect = document.querySelector("[data-theme-select]");
  const languageOptions = Array.from(document.querySelectorAll("[data-language-option]"));
  const themeOptions = Array.from(document.querySelectorAll("[data-theme-option]"));
  const menuToggle = document.querySelector("[data-menu-toggle]");
  const headerPanel = document.querySelector("[data-header-panel]");
  const darkQuery = matchMedia("(prefers-color-scheme: dark)");

  function readPreference(key) {
    try {
      return localStorage.getItem(key);
    } catch (_error) {
      return null;
    }
  }

  function writePreference(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_error) {
      // The page remains usable when storage is disabled by the browser.
    }
  }

  let language = prefs.languagePreference(readPreference(prefs.LANGUAGE_KEY), navigator.language);
  let theme = prefs.themePreference(readPreference(prefs.THEME_KEY));

  function option(value, label) {
    const item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    return item;
  }

  function markSelected(options, value, dataKey) {
    options.forEach((item) => item.setAttribute("aria-pressed", String(item.dataset[dataKey] === value)));
  }

  function applyLanguage(nextLanguage) {
    language = nextLanguage === "it" ? "it" : "en";
    const strings = i18n.getStrings(language);
    document.documentElement.lang = language;
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      const value = strings[node.dataset.i18n];
      if (typeof value === "string") node.textContent = value;
    });
    document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => {
      const key = node.dataset.i18nAriaLabel;
      const resolvedKey = key === "menu_open" && menuToggle && menuToggle.getAttribute("aria-expanded") === "true" ? "menu_close" : key;
      if (strings[resolvedKey]) node.setAttribute("aria-label", strings[resolvedKey]);
    });
    document.querySelectorAll("[data-i18n-alt]").forEach((node) => {
      const value = strings[node.dataset.i18nAlt];
      if (typeof value === "string") node.setAttribute("alt", value);
    });
    document.querySelectorAll("[data-i18n-content]").forEach((node) => {
      const value = strings[node.dataset.i18nContent];
      if (typeof value === "string") node.setAttribute("content", value);
    });
    document.querySelectorAll("[data-i18n-title]").forEach((node) => {
      const value = strings[node.dataset.i18nTitle];
      if (typeof value === "string") node.setAttribute("title", value);
    });
    document.querySelectorAll("[data-language-only]").forEach((node) => {
      node.hidden = !i18n.languageOnlyVisible(node.dataset.languageOnly, language);
    });
    if (languageSelect) {
      languageSelect.replaceChildren(
        option("it", strings.language_it),
        option("en", strings.language_en)
      );
      languageSelect.value = language;
    }
    markSelected(languageOptions, language, "languageOption");
    if (themeSelect) {
      themeSelect.replaceChildren(
        option("auto", strings.theme_auto),
        option("light", strings.theme_light),
        option("dark", strings.theme_dark)
      );
      themeSelect.value = theme;
    }
    markSelected(themeOptions, theme, "themeOption");
  }

  function applyTheme(nextTheme) {
    theme = prefs.themePreference(nextTheme);
    document.documentElement.dataset.themePreference = theme;
    document.documentElement.dataset.theme = prefs.resolveTheme(theme, darkQuery.matches);
    if (themeSelect) themeSelect.value = theme;
    markSelected(themeOptions, theme, "themeOption");
  }

  const navGroups = Array.from(document.querySelectorAll(".nav-group"));
  function closeDropdowns(except) {
    navGroups.forEach((group) => { if (group !== except) group.open = false; });
  }
  navGroups.forEach((group) => group.addEventListener("toggle", () => {
    if (group.open) closeDropdowns(group);
  }));
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".primary-nav")) closeDropdowns();
  });
  document.addEventListener("focusin", (event) => {
    if (!event.target.closest(".primary-nav")) closeDropdowns();
  });

  function setMenu(open) {
    if (!menuToggle || !headerPanel) return;
    if (!open) closeDropdowns();
    menuToggle.setAttribute("aria-expanded", String(open));
    headerPanel.dataset.open = String(open);
    const strings = i18n.getStrings(language);
    menuToggle.setAttribute("aria-label", strings[open ? "menu_close" : "menu_open"]);
  }

  if (languageSelect) languageSelect.addEventListener("change", () => {
    writePreference(prefs.LANGUAGE_KEY, languageSelect.value);
    applyLanguage(languageSelect.value);
  });
  languageOptions.forEach((item) => item.addEventListener("click", () => {
    writePreference(prefs.LANGUAGE_KEY, item.dataset.languageOption);
    applyLanguage(item.dataset.languageOption);
  }));
  if (themeSelect) themeSelect.addEventListener("change", () => {
    writePreference(prefs.THEME_KEY, themeSelect.value);
    applyTheme(themeSelect.value);
  });
  themeOptions.forEach((item) => item.addEventListener("click", () => {
    writePreference(prefs.THEME_KEY, item.dataset.themeOption);
    applyTheme(item.dataset.themeOption);
  }));
  darkQuery.addEventListener("change", () => {
    if (theme === "auto") applyTheme("auto");
  });
  if (menuToggle) menuToggle.addEventListener("click", () => setMenu(menuToggle.getAttribute("aria-expanded") !== "true"));
  document.addEventListener("keydown", (event) => {
    const openGroup = navGroups.find((group) => group.open);
    if (event.key === "Escape" && openGroup) {
      closeDropdowns();
      openGroup.querySelector("summary").focus();
      return;
    }
    if (event.key === "Escape" && menuToggle && menuToggle.getAttribute("aria-expanded") === "true") {
      setMenu(false);
      menuToggle.focus();
    }
  });
  document.querySelectorAll(".primary-nav a").forEach((link) => link.addEventListener("click", () => { closeDropdowns(); setMenu(false); }));

  if ("IntersectionObserver" in window) {
    const navLinks = Array.from(document.querySelectorAll(".primary-nav a[href^='#']"));
    const sections = navLinks.map((link) => document.querySelector(link.getAttribute("href"))).filter(Boolean);
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (!visible) return;
      navLinks.forEach((link) => {
        if (link.getAttribute("href") === `#${visible.target.id}`) link.setAttribute("aria-current", "true");
        else link.removeAttribute("aria-current");
      });
      navGroups.forEach((group) => { group.dataset.active = String(Boolean(group.querySelector("a[aria-current]"))); });
    }, { rootMargin: "-30% 0px -55%", threshold: [0, 0.25, 0.6] });
    sections.forEach((section) => observer.observe(section));
  }

  applyTheme(theme);
  applyLanguage(language);
})();
