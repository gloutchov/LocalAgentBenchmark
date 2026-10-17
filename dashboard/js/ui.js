(function (root, factory) {
  "use strict";
  const api = factory(root.LocalAgentDashboardI18n);
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.LocalAgentDashboardUI = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (I18n) {
  "use strict";

  const t = (key, values) => I18n.translate(key, values);
  const SVG_NS = "http:" + "//www.w3.org/2000/svg";
  let chartSequence = 0;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function svgElement(tag, className, attributes, text) {
    const node = document.createElementNS(SVG_NS, tag);
    if (className) node.setAttribute("class", className);
    Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function formatNumber(value, digits) {
    if (typeof value !== "number" || !Number.isFinite(value)) return t("unknown");
    const locale = I18n.getLanguage() === "it" ? "it-IT" : "en-US";
    return new Intl.NumberFormat(locale, { maximumFractionDigits: digits === undefined ? 1 : digits }).format(value);
  }

  function formatDuration(value) {
    if (typeof value !== "number") return t("unknown");
    if (value < 60) return `${formatNumber(value, 1)} s`;
    const rounded = Math.round(value);
    const minutes = Math.floor(rounded / 60);
    const seconds = rounded % 60;
    return `${minutes} min ${seconds} s`;
  }

  function formatDate(value) {
    if (!value) return t("unknown");
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return new Intl.DateTimeFormat(I18n.getLanguage() === "it" ? "it-IT" : "en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(parsed);
  }

  function stateLabel(state) {
    const labels = {
      passed: "passed",
      below_threshold: "below_threshold",
      timeout: "status_timeout",
      error: "status_error",
      missing_score: "status_missing",
      integrity_excluded: "status_excluded",
    };
    return t(labels[state] || "unknown");
  }

  function badge(text, kind) {
    return element("span", `badge badge-${kind || "neutral"}`, text);
  }

  function emptyState(key) {
    return element("p", "empty-state", t(key));
  }

  function applyStaticTranslations() {
    document.documentElement.lang = I18n.getLanguage();
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
      node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
    });
  }

  function renderSource(meta, view) {
    const source = meta && ["snapshot", "local", "import"].includes(meta.source) ? meta.source : "snapshot";
    document.getElementById("source-value").textContent = t(`source_${source}`);
    const dates = view.runs.map((run) => run.finished_at).filter(Boolean).sort();
    const latest = dates.length ? formatDate(dates[dates.length - 1]) : t("unknown");
    document.getElementById("source-meta").textContent = `${t("updated")}: ${latest} · ${t("source_privacy")}`;
  }

  function renderKpis(view) {
    const container = document.getElementById("kpis");
    const items = [
      ["runs", view.summary.runCount, "accent-blue"],
      ["models", view.summary.modelCount, "accent-cyan"],
      ["tasks", view.summary.taskCount, "accent-orange"],
      ["best_score", view.summary.bestScore === null ? t("unknown") : formatNumber(view.summary.bestScore, 1), "accent-green"],
    ];
    container.replaceChildren(
      ...items.map(([label, value, accent]) => {
        const card = element("article", `kpi-card ${accent}`);
        card.append(element("p", "kpi-label", t(label)), element("p", "kpi-value", value));
        if (label === "best_score" && view.summary.bestScore !== null) card.append(element("p", "kpi-note", t("score_suffix")));
        return card;
      })
    );
  }

  function renderIntegrity(view) {
    const container = document.getElementById("integrity-banner");
    const warning = view.summary.disqualifiedCount > 0 || view.summary.unverifiedThinkingCount > 0;
    container.className = `integrity-banner ${warning ? "integrity-warning" : "integrity-ok"}`;
    const copy = element("div", "integrity-copy");
    const warningDetails = [];
    if (view.summary.disqualifiedCount > 0) {
      warningDetails.push(t("integrity_detail", { count: view.summary.disqualifiedCount }));
    }
    if (view.summary.unverifiedThinkingCount > 0) {
      warningDetails.push(t("thinking_warning_detail", { count: view.summary.unverifiedThinkingCount }));
    }
    copy.append(
      element("strong", "", t(warning ? "integrity_warning" : "integrity_ok")),
      element("span", "", warningDetails.join(" "))
    );
    const counts = element("div", "outcome-counts");
    counts.append(
      badge(`${t("passed")}: ${view.summary.passedCount}`, "passed"),
      badge(`${t("below_threshold")}: ${view.summary.belowThresholdCount}`, "below"),
      badge(`${t("anomalies")}: ${view.summary.anomalousCount}`, "error")
    );
    container.replaceChildren(copy, counts);
  }

  function scoreCell(value) {
    const wrapper = element("div", "score-cell");
    wrapper.append(element("strong", "", formatNumber(value, 1)));
    if (typeof value === "number") {
      const track = element("span", "score-track");
      const fill = element("span", "score-fill");
      fill.style.width = `${Math.max(0, Math.min(100, value))}%`;
      track.append(fill);
      wrapper.append(track);
    }
    return wrapper;
  }

  function tableShell(headers) {
    const wrapper = element("div", "table-scroll");
    const table = element("table", "data-table");
    const head = document.createElement("thead");
    const row = document.createElement("tr");
    headers.forEach((header) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = t(header);
      row.append(cell);
    });
    head.append(row);
    const body = document.createElement("tbody");
    table.append(head, body);
    wrapper.append(table);
    return { wrapper, body };
  }

  function renderLeaderboard(view) {
    const container = document.getElementById("leaderboard");
    if (!view.leaderboard.length) {
      container.replaceChildren(emptyState("no_leaderboard"));
      return;
    }
    const groups = new Map();
    view.leaderboard.forEach((item) => {
      if (!groups.has(item.run_id)) groups.set(item.run_id, []);
      groups.get(item.run_id).push(item);
    });
    const grid = element("div", "cohort-grid");
    groups.forEach((items, runId) => {
      const cohort = element("section", "cohort-section");
      const heading = element("div", "cohort-heading");
      heading.append(
        element("h3", "", `${items[0].profile} · ${t("thinking_control")}: ${items[0].thinking_mode}`),
        element("span", "run-id", runId)
      );
      const { wrapper, body } = tableShell(["rank", "model", "overall", "quality", "completion", "duration"]);
      items.forEach((item) => {
        const row = document.createElement("tr");
        const position = document.createElement("td");
        position.textContent = String(item.rank);
        position.className = "rank-cell";
        const model = document.createElement("td");
        model.append(element("strong", "model-name", item.model));
        const overall = document.createElement("td");
        overall.append(scoreCell(item.overall_score));
        const quality = document.createElement("td");
        quality.textContent = formatNumber(item.quality_score, 1);
        const completion = document.createElement("td");
        completion.textContent = typeof item.completion_rate === "number" ? `${formatNumber(item.completion_rate, 1)}%` : t("unknown");
        const duration = document.createElement("td");
        duration.textContent = formatDuration(item.median_duration_seconds);
        row.append(position, model, overall, quality, completion, duration);
        body.append(row);
      });
      cohort.append(heading, wrapper);
      grid.append(cohort);
    });
    container.replaceChildren(grid);
  }

  function renderComparison(view) {
    const container = document.getElementById("comparison");
    if (!view.leaderboard.length) {
      container.replaceChildren(emptyState("no_leaderboard"));
      return;
    }
    const metrics = [
      ["quality", "quality_score", "bar-blue"],
      ["completion", "completion_rate", "bar-green"],
      ["speed", "speed_score", "bar-orange"],
      ["token_efficiency", "token_efficiency_score", "bar-cyan"],
    ];
    const groups = new Map();
    view.leaderboard.forEach((row) => {
      if (!groups.has(row.run_id)) groups.set(row.run_id, []);
      groups.get(row.run_id).push(row);
    });
    const grid = element("div", "cohort-grid");
    groups.forEach((groupRows, runId) => {
      const cohort = element("section", "cohort-section");
      const cohortHeading = element("div", "cohort-heading");
      cohortHeading.append(
        element("h3", "", `${groupRows[0].profile} · ${t("thinking_control")}: ${groupRows[0].thinking_mode}`),
        element("span", "run-id", runId)
      );
      const list = element("div", "comparison-list");
      [...groupRows]
        .sort((left, right) => (right.overall_score ?? -1) - (left.overall_score ?? -1))
        .slice(0, 6)
        .forEach((row) => {
          const card = element("article", "comparison-row");
          const heading = element("div", "comparison-model");
          heading.append(element("strong", "model-name", row.model));
          card.append(heading);
          metrics.forEach(([label, key, color]) => {
            const metric = element("div", "metric-row");
            const caption = element("span", "metric-label", t(label));
            const track = element("span", "metric-track");
            const fill = element("span", `metric-fill ${color}`);
            const value = typeof row[key] === "number" ? Math.max(0, Math.min(100, row[key])) : 0;
            fill.style.width = `${value}%`;
            track.append(fill);
            metric.append(caption, track, element("span", "metric-value", formatNumber(row[key], 0)));
            card.append(metric);
          });
          list.append(card);
        });
      cohort.append(cohortHeading, list);
      grid.append(cohort);
    });
    container.replaceChildren(grid);
  }

  function efficiencyMetric(plot) {
    return plot.field === "median_duration_seconds"
      ? { title: "efficiency_duration", label: "duration", format: formatDuration }
      : { title: "efficiency_tokens", label: "output_tokens", format: (value) => formatNumber(value, 0) };
  }

  function efficiencyPointText(point, plot) {
    const metric = efficiencyMetric(plot);
    return t("efficiency_point", {
      model: point.model,
      quality: formatNumber(point.quality_score, 1),
      metric: t(metric.label),
      value: metric.format(point[plot.field]),
      completion: formatNumber(point.completion_rate, 1),
    });
  }

  function renderEfficiencyPlot(cohort, plot) {
    const figure = element("figure", "efficiency-figure");
    const metric = efficiencyMetric(plot);
    const titleId = `efficiency-title-${chartSequence += 1}`;
    const header = element("figcaption", "efficiency-figure-heading");
    const copy = element("div", "");
    const title = element("h3", "", t(metric.title));
    title.id = titleId;
    copy.append(title, element("p", "", t("efficiency_scale_note")));
    header.append(copy, badge(t("efficiency_quality_axis"), "profile"));
    figure.append(header);

    if (!plot.domain || !plot.points.length) {
      figure.append(emptyState("no_efficiency"));
      return figure;
    }

    const width = 680;
    const height = 360;
    const margin = { top: 22, right: 22, bottom: 58, left: 66 };
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;
    const logMin = Math.log10(plot.domain.minimum);
    const logMax = Math.log10(plot.domain.maximum);
    const xPosition = (value) => margin.left + ((Math.log10(value) - logMin) / (logMax - logMin)) * chartWidth;
    const yPosition = (value) => margin.top + (1 - Math.max(0, Math.min(cohort.quality_maximum, value)) / cohort.quality_maximum) * chartHeight;
    const svg = svgElement("svg", "efficiency-chart", {
      viewBox: `0 0 ${width} ${height}`,
      role: "img",
      "aria-labelledby": titleId,
      preserveAspectRatio: "xMidYMid meet",
    });
    svg.append(svgElement("rect", "efficiency-plot-background", {
      x: margin.left,
      y: margin.top,
      width: chartWidth,
      height: chartHeight,
    }));

    for (let index = 0; index <= 4; index += 1) {
      const value = cohort.quality_maximum * index / 4;
      const y = yPosition(value);
      svg.append(
        svgElement("line", "efficiency-grid-line", { x1: margin.left, y1: y, x2: width - margin.right, y2: y }),
        svgElement("text", "efficiency-axis-tick", { x: margin.left - 10, y: y + 4, "text-anchor": "end" }, formatNumber(value, 0))
      );
    }
    plot.domain.ticks.forEach((tick) => {
      const x = xPosition(tick);
      svg.append(
        svgElement("line", "efficiency-grid-line", { x1: x, y1: margin.top, x2: x, y2: height - margin.bottom }),
        svgElement("text", "efficiency-axis-tick", { x, y: height - margin.bottom + 24, "text-anchor": "middle" }, metric.format(tick))
      );
    });
    svg.append(
      svgElement("line", "efficiency-axis", { x1: margin.left, y1: margin.top, x2: margin.left, y2: height - margin.bottom }),
      svgElement("line", "efficiency-axis", { x1: margin.left, y1: height - margin.bottom, x2: width - margin.right, y2: height - margin.bottom }),
      svgElement("text", "efficiency-axis-label", { x: margin.left + chartWidth / 2, y: height - 10, "text-anchor": "middle" }, t(metric.label)),
      svgElement("text", "efficiency-axis-label", {
        x: 18,
        y: margin.top + chartHeight / 2,
        transform: `rotate(-90 18 ${margin.top + chartHeight / 2})`,
        "text-anchor": "middle",
      }, t("quality"))
    );

    const detail = element("p", "efficiency-focus-detail", t("efficiency_focus_hint"));
    detail.setAttribute("aria-live", "polite");
    plot.points.forEach((point) => {
      const x = xPosition(point[plot.field]);
      const y = yPosition(point.quality_score);
      const label = efficiencyPointText(point, plot);
      const group = svgElement("g", `efficiency-point efficiency-point-${point.state}`, {
        transform: `translate(${x} ${y})`,
        tabindex: "0",
        role: "img",
        "aria-label": label,
      });
      group.append(
        svgElement("circle", "efficiency-point-marker", { r: 13 }),
        svgElement("text", "efficiency-point-rank", { x: 0, y: 4, "text-anchor": "middle" }, point.rank),
        svgElement("title", "", {}, label)
      );
      const show = () => { detail.textContent = label; };
      const reset = () => {
        if (document.activeElement !== group) detail.textContent = t("efficiency_focus_hint");
      };
      group.addEventListener("mouseenter", show);
      group.addEventListener("mouseleave", reset);
      group.addEventListener("focus", show);
      group.addEventListener("blur", () => { detail.textContent = t("efficiency_focus_hint"); });
      svg.append(group);
    });

    const key = element("ol", "efficiency-model-key");
    plot.points.forEach((point) => {
      const item = element("li", `efficiency-key-item efficiency-key-${point.state}`);
      item.append(
        element("span", "efficiency-key-rank", point.rank),
        element("code", "efficiency-key-model", point.model),
        element("span", "efficiency-key-value", `${formatNumber(point.quality_score, 1)} · ${metric.format(point[plot.field])}`)
      );
      key.append(item);
    });
    const legend = element("div", "efficiency-legend");
    [
      ["complete", "efficiency_complete"],
      ["partial", "efficiency_partial"],
      ["below", "efficiency_below"],
    ].forEach(([state, label]) => {
      const item = element("span", "efficiency-legend-item");
      item.append(element("span", `efficiency-legend-marker efficiency-legend-${state}`), element("span", "", t(label)));
      legend.append(item);
    });
    figure.append(svg, detail, key, legend);
    if (plot.omitted_count > 0) {
      figure.append(element("p", "efficiency-omitted", t("efficiency_omitted", { count: plot.omitted_count })));
    }
    return figure;
  }

  function renderEfficiency(view) {
    const container = document.getElementById("efficiency");
    if (!view.efficiency.length) {
      container.replaceChildren(emptyState("no_efficiency"));
      return;
    }
    const cohorts = element("div", "efficiency-cohorts");
    view.efficiency.forEach((cohort) => {
      const section = element("section", "efficiency-cohort");
      const heading = element("div", "cohort-heading");
      heading.append(
        element("h3", "", `${cohort.profile} · ${t("thinking_control")}: ${cohort.thinking_mode}`),
        element("span", "run-id", cohort.run_id)
      );
      const charts = element("div", "efficiency-chart-grid");
      charts.append(renderEfficiencyPlot(cohort, cohort.duration), renderEfficiencyPlot(cohort, cohort.tokens));
      section.append(heading, charts);
      cohorts.append(section);
    });
    container.replaceChildren(cohorts);
  }

  function modelList(models) {
    const list = element("ul", "model-list");
    models.forEach((model) => list.append(element("li", "", model)));
    return list;
  }

  function renderFunnel(view) {
    const container = document.getElementById("funnel");
    if (!view.funnel.length) {
      container.replaceChildren(emptyState("no_funnel"));
      return;
    }
    const grid = element("div", "funnel-grid");
    view.funnel.forEach((stage, index) => {
      const wrapper = element("div", "funnel-stage-wrap");
      const stageNode = element("article", "funnel-stage");
      const heading = element("div", "stage-heading");
      heading.append(element("span", "stage-number", String(index + 1).padStart(2, "0")), element("h3", "", stage.profile));
      stageNode.append(heading);
      const participantTitle = element("p", "stage-label", `${t("participants")} · ${stage.participants.length}`);
      stageNode.append(participantTitle, modelList(stage.participants));
      if (stage.next_profile) {
        const transition = element("div", "transition-summary");
        transition.append(
          badge(`${t("continued")}: ${stage.continued_to_next.length}`, "passed"),
          badge(`${t("not_run_next")}: ${stage.not_run_in_next.length}`, "neutral")
        );
        stageNode.append(transition);
      } else {
        stageNode.append(element("p", "final-stage", t("final_stage")));
      }
      if (stage.new_participants.length && index > 0) {
        stageNode.append(element("p", "stage-note", `${t("new_participants")}: ${stage.new_participants.join(", ")}`));
      }
      wrapper.append(stageNode);
      if (index < view.funnel.length - 1) wrapper.append(element("span", "funnel-arrow", "→"));
      grid.append(wrapper);
    });
    container.replaceChildren(grid);
  }

  function renderTasks(view, onDetails) {
    const container = document.getElementById("tasks");
    const parts = [];
    if (view.exclusions && view.exclusions.length) {
      parts.push(element("h3", "", t("exclusions")));
      parts.push(element("p", "section-note", t("exclusion_note")));
      const exclusionList = element("div", "exclusion-list");
      view.exclusions.forEach((exclusion) => {
        const card = element("article", "exclusion-card");
        card.append(element("h4", "", exclusion.model));
        const details = element("dl", "exclusion-details");
        const entries = [
          ["profile", `${exclusion.profile} · ${exclusion.run_id}`],
          ["exclusion_scope", exclusion.case_id || t("preflight_or_run")],
          ["exclusion_reason", t(`exclusion_${exclusion.reason}`)],
          ["sandbox", `${exclusion.sandbox_backend} · ${t(exclusion.sandbox_enforced ? "enforced" : "not_enforced")}`],
        ];
        entries.forEach(([label, value]) => details.append(element("dt", "", t(label)), element("dd", "", value)));
        card.append(details);
        exclusionList.append(card);
      });
      parts.push(exclusionList);
    }
    if (!view.tasks.length && !parts.length) {
      container.replaceChildren(emptyState("no_tasks"));
      return;
    }
    if (!view.tasks.length) {
      container.replaceChildren(...parts);
      return;
    }
    const { wrapper, body } = tableShell(["model", "case", "profile", "thinking_control", "state", "overall", "duration", "output_tokens", "actions"]);
    view.tasks.forEach((task) => {
      const row = document.createElement("tr");
      const model = document.createElement("td");
      model.append(element("strong", "model-name", task.model));
      const caseCell = document.createElement("td");
      const title = I18n.getLanguage() === "it" ? task.case_title : task.case_title_en;
      caseCell.append(element("span", "task-title", title), element("span", "run-id", task.case_id));
      const profile = document.createElement("td");
      profile.append(badge(task.profile, "profile"));
      const thinking = document.createElement("td");
      thinking.textContent = task.thinking_mode;
      const state = document.createElement("td");
      const stateKind = task.state === "passed" ? "passed" : task.state === "below_threshold" ? "below" : "error";
      state.append(badge(stateLabel(task.state), stateKind));
      const score = document.createElement("td");
      score.textContent = formatNumber(task.score, 1);
      const duration = document.createElement("td");
      duration.textContent = formatDuration(task.duration_seconds);
      const tokens = document.createElement("td");
      tokens.textContent = formatNumber(task.output_tokens, 0);
      const actions = document.createElement("td");
      const button = element("button", "detail-button", t("details"));
      button.type = "button";
      button.addEventListener("click", () => onDetails(task));
      actions.append(button);
      row.append(model, caseCell, profile, thinking, state, score, duration, tokens, actions);
      body.append(row);
    });
    container.replaceChildren(...parts, wrapper);
  }

  function renderRuns(view) {
    const container = document.getElementById("run-list");
    container.replaceChildren(
      ...view.runs.map((run) => {
        const details = element("details", "run-card");
        const summary = document.createElement("summary");
        const title = element("span", "run-summary-main");
        title.append(element("strong", "", run.id), badge(run.profile, "profile"));
        summary.append(title, element("span", "run-date", formatDate(run.finished_at)));
        const grid = element("dl", "metadata-grid");
        const thinking = run.thinking_control || {
          status: "unverified",
          requested: "unknown",
          reasoning_effort: null,
        };
        const thinkingStatus = thinking.status === "unverified" ? t("thinking_unverified") : thinking.status;
        const thinkingValue = `${thinking.requested} · ${thinkingStatus}${
          thinking.reasoning_effort ? ` · ${thinking.reasoning_effort}` : ""
        }`;
        const entries = [
          ["benchmark_version", run.benchmark_version],
          ["sandbox", `${run.sandbox.backend} · ${t(run.sandbox.enforced ? "enforced" : "not_enforced")}`],
          ["integrity", run.integrity.status],
          ["thinking_control", thinkingValue],
          ["models", run.participants.length],
          ["commit", run.provenance.repository_commit ? run.provenance.repository_commit.slice(0, 12) : t("unknown")],
        ];
        entries.forEach(([label, value]) => {
          grid.append(element("dt", "", t(label)), element("dd", "", value));
        });
        details.append(summary, grid);
        return details;
      })
    );
  }

  function showTaskDialog(task) {
    const dialog = document.getElementById("task-dialog");
    const title = I18n.getLanguage() === "it" ? task.case_title : task.case_title_en;
    document.getElementById("dialog-title").textContent = title;
    const content = document.getElementById("dialog-content");
    const grid = element("dl", "dialog-grid");
    const entries = [
      ["model", task.model],
      ["profile", task.profile],
      ["thinking_control", task.thinking_mode],
      ["run", task.run_id],
      ["state", stateLabel(task.state)],
      ["status", task.status],
      ["overall", formatNumber(task.score, 1)],
      ["max_score", formatNumber(task.max_score, 1)],
      ["repetition", task.repetition],
      ["duration", formatDuration(task.duration_seconds)],
      ["output_tokens", formatNumber(task.output_tokens, 0)],
      ["tool_calls", formatNumber(task.tool_calls, 0)],
      ["tool_errors", formatNumber(task.tool_errors, 0)],
      ["cpu", typeof task.cpu_seconds === "number" ? `${formatNumber(task.cpu_seconds, 2)} s` : t("unknown")],
      ["energy", typeof task.energy_joules === "number" ? `${formatNumber(task.energy_joules, 1)} J` : t("unknown")],
      ["integrity_valid", task.integrity_valid === null ? t("unknown") : t(task.integrity_valid ? "yes" : "no")],
    ];
    entries.forEach(([label, value]) => grid.append(element("dt", "", t(label)), element("dd", "", value)));
    content.replaceChildren(grid);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  return {
    applyStaticTranslations,
    renderComparison,
    renderEfficiency,
    renderFunnel,
    renderIntegrity,
    renderKpis,
    renderLeaderboard,
    renderRuns,
    renderSource,
    renderTasks,
    showTaskDialog,
  };
});
