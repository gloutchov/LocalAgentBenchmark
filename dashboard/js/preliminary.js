(function (root, factory) {
  "use strict";
  const api = factory(root && root.LocalAgentDashboardI18n);
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.LocalAgentDashboardPreliminary = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (I18n) {
  "use strict";
  const SVG_NS = "http:" + "//www.w3.org/2000/svg";
  const finite = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;

  function formatRange(value, low, high, format, unknown) {
    if (!finite(value)) return unknown;
    const median = format(value);
    return finite(low) && finite(high) ? `${median} [${format(low)}–${format(high)}]` : median;
  }

  function metricSeries(rows, key) {
    return rows.map((row) => ({
      model: row.model, context: row.context, status: row.status,
      value: row.status === "measured" && finite(row[key]) ? row[key] : null,
    }));
  }

  function groundingSeries(rows, prefix) {
    return rows.map((row) => {
      const correct = row[`${prefix}_correct`], total = row[`${prefix}_total`];
      const available = row.status === "measured" && finite(correct) && finite(total) && total > 0;
      return {model: row.model, status: row.status, value: available ? correct / total * 100 : null,
        count: available ? correct : null, total: available ? total : null};
    });
  }

  function sampleSeries(rows) {
    return rows.flatMap((row) => [["completed","preliminary_completed"],["failed","preliminary_failed"],["truncated","preliminary_truncated"]].map(([key,category]) => {
      const available = row.status !== "excluded" && finite(row.samples) && row.samples > 0 && finite(row[key]);
      return {model:row.model,context:row.context,status:row.status,category,
        value:available ? row[key] / row.samples * 100 : null,
        count:available ? row[key] : null,total:available ? row.samples : null};
    }));
  }

  const t = (key) => I18n.translate(key);
  const number = (value, digits = 2) => finite(value)
    ? new Intl.NumberFormat(I18n.getLanguage() === "it" ? "it-IT" : "en-US", {maximumFractionDigits:digits}).format(value)
    : t("unknown");
  function node(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined) result.textContent = text;
    return result;
  }
  function table(headers, title) {
    const wrapper = node("div", "table-scroll");
    const tableNode = node("table", "data-table");
    tableNode.setAttribute("aria-label", t(title));
    const head = node("thead"), row = node("tr"), body = node("tbody");
    headers.forEach((key) => {const th = node("th", "", t(key)); th.scope = "col"; row.append(th);});
    head.append(row); tableNode.append(head, body); wrapper.append(tableNode);
    return {wrapper, body};
  }
  function appendRow(body, values) {
    const row = node("tr"); values.forEach((value) => row.append(node("td", "", String(value)))); body.append(row);
  }

  function chart(title, series, unit, fixedMaximum) {
    const figure = node("figure", "preliminary-chart");
    figure.append(node("figcaption", "", t(title)));
    const list = node("ul", "preliminary-bars");
    const maximum = fixedMaximum || Math.max(0, ...series.map((item) => item.value || 0));
    series.forEach((item) => {
      const row = node("li", "preliminary-bar-row");
      const label = [item.model, item.context, item.category && t(item.category)].filter(Boolean).join(" · ");
      const value = item.value === null ? t(item.status === "excluded" ? "preliminary_excluded" : "unknown")
        : item.total !== undefined ? `${item.count}/${item.total} · ${number(item.value, 1)}%`
          : `${number(item.value, 3)}${unit ? ` ${unit}` : ""}`;
      const copy = node("div", "preliminary-bar-label");
      copy.append(node("span", "", label), node("strong", "", value));
      row.append(copy);
      row.tabIndex = 0;
      row.setAttribute("aria-label", `${t(title)} · ${label}: ${value}`);
      if (item.value !== null) {
        const svg = document.createElementNS(SVG_NS, "svg");
        svg.setAttribute("viewBox", "0 0 100 6"); svg.setAttribute("preserveAspectRatio", "none");
        svg.setAttribute("aria-hidden", "true");
        for (const [className, width] of [["preliminary-bar-track",100],["preliminary-bar-fill",maximum > 0 ? item.value / maximum * 100 : 0]]) {
          const rect = document.createElementNS(SVG_NS, "rect");
          rect.setAttribute("class",className);rect.setAttribute("width",String(width));rect.setAttribute("height","6");svg.append(rect);
        }
        row.append(svg);
      } else row.classList.add("preliminary-bar-unavailable");
      list.append(row);
    });
    figure.append(list);
    if (series.some((item) => item.value !== null)) {
      const axis = node("div", "preliminary-chart-scale");
      axis.setAttribute("aria-hidden", "true");
      axis.append(node("span", "", `0${fixedMaximum ? "%" : unit ? ` ${unit}` : ""}`),
        node("span", "", maximum > 0 ? `${number(maximum,3)}${fixedMaximum ? "%" : unit ? ` ${unit}` : ""}` : ""));
      figure.append(axis);
    }
    return figure;
  }

  function render(view) {
    const panel = document.getElementById("preliminary-panel"), container = document.getElementById("preliminary-results");
    const rows = view.preliminary || [];
    panel.hidden = rows.length === 0;
    container.replaceChildren();
    for (const run of view.runs.filter((item) => item.profile === "preliminary")) {
      const selected = rows.filter((row) => row.run_id === run.id);
      if (!selected.length) continue;
      const group = node("section", "preliminary-run");
      group.append(node("h3", "", `${run.id} · ${t("thinking_control")}: ${run.thinking_control.requested}`));
      const performance = selected.filter((item) => item.context !== "grounding");
      const grounding = selected.filter((item) => item.context === "grounding");
      const perfSection = node("section", "preliminary-section");
      perfSection.append(node("h4", "", t("preliminary_performance_title")));
      const perf = table(["model","preliminary_context","state","preliminary_samples","preliminary_first","duration","preliminary_tps","preliminary_decode","preliminary_gap","preliminary_truncated"], "preliminary_performance_title");
      for (const r of performance) appendRow(perf.body, [r.model,r.context,t(`preliminary_${r.status}`),`${r.completed}/${r.samples}`,
        formatRange(r.first_answer_seconds,r.first_answer_min_seconds,r.first_answer_max_seconds,(n)=>number(n,3),t("unknown")),number(r.duration_seconds,3),
        formatRange(r.output_tokens_per_second,r.output_tokens_min_per_second,r.output_tokens_max_per_second,(n)=>number(n,2),t("unknown")),
        number(r.decode_tokens_per_second,2),number(r.max_chunk_gap_seconds,3),r.truncated]);
      perfSection.append(perf.wrapper,node("p","preliminary-footnote",t("preliminary_performance_note")));
      const perfCharts = node("div", "preliminary-charts");
      for (const [key,title,unit] of [
        ["first_answer_seconds","preliminary_first","s"],["duration_seconds","duration","s"],
        ["output_tokens_per_second","preliminary_tps","token/s"],["decode_tokens_per_second","preliminary_decode","token/s"],
        ["max_chunk_gap_seconds","preliminary_gap","s"],
      ]) perfCharts.append(chart(title,metricSeries(performance,key),unit));
      perfCharts.append(chart("preliminary_sample_counts",sampleSeries(performance),"",100));
      const perfChartSection = node("section", "preliminary-section");
      perfChartSection.append(node("h4", "", t("preliminary_performance_charts")),perfCharts);
      const groundingSection = node("section", "preliminary-section");
      groundingSection.append(node("h4","",t("preliminary_grounding_title")));
      const truth = table(["model","state","preliminary_known","preliminary_missing","preliminary_premise","preliminary_unsupported","preliminary_abstain","preliminary_invalid","preliminary_failed"], "preliminary_grounding_title");
      for (const r of grounding) appendRow(truth.body,[r.model,t(`preliminary_${r.status}`),`${r.known_correct}/${r.known_total}`,`${r.missing_correct}/${r.missing_total}`,`${r.premise_correct}/${r.premise_total}`,r.unsupported_answers,r.unnecessary_abstentions,r.invalid_answers,r.failed]);
      groundingSection.append(truth.wrapper);
      const truthCharts = node("div", "preliminary-charts");
      for (const [prefix,title] of [["known","preliminary_known"],["missing","preliminary_missing"],["premise","preliminary_premise"]]) truthCharts.append(chart(title,groundingSeries(grounding,prefix),"",100));
      const errors = grounding.flatMap((r)=>[ ["unsupported_answers","preliminary_unsupported"],["unnecessary_abstentions","preliminary_abstain"],["invalid_answers","preliminary_invalid"],["failed","preliminary_failed"] ].map(([key,category])=>({model:r.model,status:r.status,value:r.status !== "excluded" && finite(r[key]) ? r[key] : null,context:null,category})));
      truthCharts.append(chart("preliminary_error_counts",errors,""));
      const truthChartSection = node("section", "preliminary-section");
      truthChartSection.append(node("h4", "", t("preliminary_grounding_charts")),truthCharts);
      group.append(perfSection,groundingSection,perfChartSection,truthChartSection);container.append(group);
    }
  }
  return {formatRange, metricSeries, groundingSeries, sampleSeries, render};
});
