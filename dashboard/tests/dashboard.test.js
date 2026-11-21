"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.resolve(__dirname, "../..");
const Core = require(path.join(ROOT, "dashboard/js/core.js"));
const I18n = require(path.join(ROOT, "dashboard/js/i18n.js"));
const fixture = JSON.parse(
  fs.readFileSync(path.join(ROOT, "cases/results_dashboard/fixture/dashboard-data.json"), "utf8")
);

function alternateDataset() {
  const run = JSON.parse(JSON.stringify(fixture.runs[0]));
  run.id = "alternate-run";
  run.profile = "custom";
  run.participants = ["model-unseen"];
  run.leaderboard = [
    {
      ...run.leaderboard[0],
      rank: 1,
      model: "model-unseen",
      overall_score: 77,
      quality_score: 81,
      median_duration_seconds: 55,
    },
  ];
  run.tasks = [
    {
      ...run.tasks[0],
      model: "model-unseen",
      case_id: "new-case",
      case_title: "Caso nuovo",
      case_title_en: "New case",
      category: "alternate",
      score: 81,
      state: "passed",
    },
  ];
  delete run.thinking_control;
  return {
    schema_version: 1,
    profile_order: ["custom"],
    runs: [run],
    funnel: [
      {
        profile: "custom",
        run_ids: [run.id],
        participants: ["model-unseen"],
        new_participants: ["model-unseen"],
        next_profile: null,
        continued_to_next: [],
        not_run_in_next: [],
      },
    ],
  };
}

test("validates the frozen dataset and rejects malformed input", () => {
  assert.equal(Core.validateDashboardData(fixture), true);
  assert.throws(
    () => Core.validateDashboardData({ schema_version: 99, profile_order: [], runs: [], funnel: [] }),
    /schema/i
  );
  const duplicate = JSON.parse(JSON.stringify(fixture));
  duplicate.runs.push(JSON.parse(JSON.stringify(duplicate.runs[0])));
  assert.throws(() => Core.validateDashboardData(duplicate), /duplicate/i);
  const leaked = JSON.parse(JSON.stringify(fixture));
  leaked.runs[0].tasks[0].final_response = "PRIVATE-RESPONSE";
  assert.throws(() => Core.validateDashboardData(leaked), /fields/i);
  const invalidState = JSON.parse(JSON.stringify(fixture));
  invalidState.runs[0].tasks[0].state = "mystery";
  assert.throws(() => Core.validateDashboardData(invalidState), /metadata/i);
});

test("creates filtered and sorted views without mutating the dataset", () => {
  const before = JSON.stringify(fixture);
  const view = Core.createDashboardView(fixture, {
    profile: "smoke",
    model: "qwen3.5:9b-mlx",
    query: "targeted",
    sortBy: "median_duration_seconds",
    sortDirection: "asc",
  });
  assert.deepEqual(view.availableModels.includes("qwen3.5:9b-mlx"), true);
  assert.ok(view.leaderboard.every((row) => row.profile === "smoke" && row.model === "qwen3.5:9b-mlx"));
  assert.ok(view.leaderboard.every((row) => ["off", "medium"].includes(row.thinking_mode)));
  assert.ok(view.tasks.every((row) => row.model === "qwen3.5:9b-mlx"));
  assert.ok(view.tasks.every((row) => ["off", "medium"].includes(row.thinking_mode)));
  assert.ok(view.efficiency.every((cohort) => cohort.duration.points.length === 1));
  assert.ok(view.efficiency.every((cohort) => cohort.tokens.points.length === 1));
  assert.ok(view.efficiency.every((cohort) => cohort.duration.points[0].model === "qwen3.5:9b-mlx"));
  assert.equal(view.funnel[0].profile, "smoke");
  assert.equal(JSON.stringify(fixture), before);
});

test("builds separate efficiency cohorts with logarithmic domains and completion states", () => {
  const view = Core.createDashboardView(fixture, { profile: "all", model: "all" });
  const rankedRuns = fixture.runs.filter((run) => run.leaderboard.length > 0);
  assert.equal(view.efficiency.length, rankedRuns.length);
  assert.deepEqual(view.efficiency.map((cohort) => cohort.run_id), rankedRuns.map((run) => run.id));
  assert.ok(view.efficiency.every((cohort) => cohort.duration.domain.minimum > 0));
  assert.ok(view.efficiency.every((cohort) => cohort.duration.domain.maximum > cohort.duration.domain.minimum));
  assert.ok(view.efficiency.every((cohort) => cohort.tokens.domain.ticks.length <= 7));
  const smoke = view.efficiency.find((cohort) => cohort.profile === "smoke" && cohort.thinking_mode === "off");
  assert.equal(smoke.duration.points.find((point) => point.model === "qwen3.5:9b-mlx").state, "complete");
  assert.equal(smoke.duration.points.find((point) => point.model === "qwen3:14b").state, "below");
});

test("handles degenerate and missing efficiency metrics without inventing points", () => {
  const domain = Core.buildLogDomain([42, 42, 42]);
  assert.ok(domain.minimum < 42 && domain.maximum > 42);
  assert.ok(domain.ticks.length >= 1 && domain.ticks.length <= 7);
  const huge = Core.buildLogDomain([0.001, 1_000_000_000]);
  assert.ok(huge.ticks.length <= 7);
  const cohorts = Core.buildEfficiencyCohorts([
    {
      run_id: "run-a",
      profile: "smoke",
      thinking_mode: "off",
      rank: 1,
      model: "model-a",
      quality_score: 80,
      completion_rate: 50,
      median_duration_seconds: 42,
      median_output_tokens: null,
    },
  ]);
  assert.equal(cohorts[0].duration.points.length, 1);
  assert.equal(cohorts[0].duration.points[0].state, "partial");
  assert.equal(cohorts[0].tokens.points.length, 0);
  assert.equal(cohorts[0].tokens.omitted_count, 1);
  assert.equal(cohorts[0].tokens.domain, null);
});

test("merges alternate datasets, deduplicates identical runs, and rejects collisions", () => {
  const alternate = alternateDataset();
  const merged = Core.mergeDashboardData([fixture, fixture, alternate]);
  assert.equal(merged.schema_version, 4);
  assert.equal(merged.runs.length, fixture.runs.length + 1);
  assert.deepEqual(merged.profile_order, ["smoke", "standard", "full", "custom"]);
  assert.deepEqual(merged.funnel.map((stage) => stage.profile), ["smoke", "standard", "full"]);
  const legacyRun = merged.runs.find((run) => run.id === "alternate-run");
  assert.equal(legacyRun.thinking_control.status, "unverified");
  assert.equal(legacyRun.thinking_control.source, "legacy_unverified");
  assert.deepEqual(legacyRun.exclusions, []);
  assert.ok(merged.runs.filter((run) => run.id !== "alternate-run").every((run) => run.thinking_control.source === "explicit_sampling_parameter"));

  const collision = alternateDataset();
  collision.runs[0].id = fixture.runs[0].id;
  collision.funnel[0].run_ids = [fixture.runs[0].id];
  assert.throws(() => Core.mergeDashboardData([fixture, collision]), /collision/i);
});

test("shows preflight and workspace exclusions without counting them as tasks", () => {
  const dataset = Core.mergeDashboardData([fixture]);
  const run = dataset.runs[0];
  run.participants.push("excluded-thinking", "excluded-boundary");
  run.integrity.disqualified_models.push("excluded-thinking", "excluded-boundary");
  run.exclusions = [
    { model: "excluded-thinking", reason: "thinking_observed_off", case_id: null },
    { model: "excluded-boundary", reason: "workspace_boundary", case_id: "targeted_patch" },
  ];
  assert.equal(Core.validateDashboardData(dataset), true);
  const view = Core.createDashboardView(dataset, { model: "excluded-thinking" });
  assert.equal(view.tasks.length, 0);
  assert.equal(view.summary.taskCount, 0);
  assert.equal(view.exclusions.length, 1);
  assert.equal(view.exclusions[0].reason, "thinking_observed_off");
  assert.equal(Core.createDashboardView(dataset, { query: "workspace_boundary" }).exclusions.length, 1);
  const leaked = JSON.parse(JSON.stringify(dataset));
  leaked.runs[0].exclusions[0].evidence = "PRIVATE-EVIDENCE";
  assert.throws(() => Core.validateDashboardData(leaked), /fields/i);
  const invalidPath = JSON.parse(JSON.stringify(dataset));
  invalidPath.runs[0].exclusions[0].case_id = "/Users/private/file";
  assert.throws(() => Core.validateDashboardData(invalidPath), /exclusion/i);
});

test("keeps thinking and showcase as independent profiles outside the funnel", () => {
  const thinking = alternateDataset();
  thinking.runs[0].id = "thinking-run";
  thinking.runs[0].profile = "thinking";
  thinking.profile_order = ["thinking"];
  thinking.funnel[0].profile = "thinking";
  thinking.funnel[0].run_ids = ["thinking-run"];

  const showcase = alternateDataset();
  showcase.runs[0].id = "showcase-run";
  showcase.runs[0].profile = "showcase";
  showcase.profile_order = ["showcase"];
  showcase.funnel[0].profile = "showcase";
  showcase.funnel[0].run_ids = ["showcase-run"];

  const merged = Core.mergeDashboardData([fixture, thinking, showcase]);
  assert.deepEqual(merged.profile_order, ["smoke", "standard", "full", "thinking", "showcase"]);
  assert.deepEqual(merged.funnel.map((stage) => stage.profile), ["smoke", "standard", "full"]);
  assert.equal(Core.createDashboardView(merged, { profile: "thinking" }).funnel.length, 0);
});

test("rebuilds neutral funnel semantics", () => {
  const merged = Core.mergeDashboardData([fixture]);
  const smoke = merged.funnel.find((stage) => stage.profile === "smoke");
  assert.ok(smoke.continued_to_next.includes("qwen3.5:9b-mlx"));
  assert.ok(smoke.not_run_in_next.includes("cogito:14b"));
  assert.equal(smoke.not_run_in_next.includes("qwen3.5:9b-mlx"), false);
  const view = Core.createDashboardView(merged, {});
  const uniqueDisqualified = new Set(
    merged.runs.flatMap((run) => run.integrity.disqualified_models)
  );
  assert.equal(view.summary.disqualifiedCount, uniqueDisqualified.size);
  assert.equal(
    view.summary.unverifiedThinkingCount,
    fixture.runs.filter((run) => run.thinking_control.status !== "passed").length
  );
});

test("keeps Italian and English dictionaries synchronized", () => {
  assert.equal(I18n.validateDictionaries(), true);
  I18n.setLanguage("it");
  assert.match(I18n.translate("not_run_next"), /eseguit/i);
  I18n.setLanguage("en");
  assert.match(I18n.translate("not_run_next"), /not run/i);
});

test("local snapshot output is loaded by the UI and ignored by Git", () => {
  const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
  const gitignore = fs.readFileSync(path.join(ROOT, ".gitignore"), "utf8");
  assert.match(html, /<script src="data\/snapshot\.js" defer><\/script>/);
  assert.match(gitignore, /^dashboard\/data\/snapshot\.js$/m);
});

test("official assets are semantic and contain no remote runtime hooks", () => {
  const files = ["dashboard/index.html", "dashboard/styles.css", "dashboard/js/app.js", "dashboard/js/ui.js", "dashboard/js/preliminary.js"];
  const source = files.map((file) => fs.readFileSync(path.join(ROOT, file), "utf8")).join("\n");
  const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8").toLowerCase();
  for (const token of ["<main", "<section", "<h1", "<label", 'type="file"', "aria-live", "skip-link", "<dialog"]) {
    assert.ok(html.includes(token), `missing ${token}`);
  }
  assert.doesNotMatch(source, /https?:\/\/|websocket|sendbeacon|xmlhttprequest|\bfetch\s*\(/i);
  assert.match(source, /@media/);
  assert.match(source, /:focus-visible/);
  assert.match(source, /prefers-color-scheme/);
  assert.match(source, /localStorage/);
  assert.match(source, /cohort-grid/);
  assert.match(source, /renderEfficiency/);
  assert.match(source, /createElementNS/);
  assert.match(html, /id="efficiency"/);
});

test("preliminary schema 4 stays descriptive and rejects raw content", () => {
  const data = Core.mergeDashboardData([fixture]);
  const run = structuredClone(data.runs[0]);
  run.id = "synthetic-preliminary";
  run.profile = "preliminary";
  run.leaderboard = [];
  run.tasks = [];
  run.exclusions = [];
  const row = {model: run.participants[0], context: "short", status: "measured"};
  const metrics = ["first_answer_seconds","duration_seconds","output_tokens_per_second","decode_tokens_per_second","max_chunk_gap_seconds","first_answer_min_seconds","first_answer_max_seconds","output_tokens_min_per_second","output_tokens_max_per_second"];
  const counts = ["samples","completed","failed","truncated","known_total","known_correct","missing_total","missing_correct","premise_total","premise_correct","unsupported_answers","unnecessary_abstentions","invalid_answers"];
  metrics.forEach((key) => {row[key] = null;});
  counts.forEach((key) => {row[key] = 0;});
  row.samples = row.completed = 3;
  run.preliminary = [row];
  data.runs.push(run);
  data.profile_order.unshift("preliminary");
  const merged = Core.mergeDashboardData([data]);
  const view = Core.createDashboardView(merged, {profile: "preliminary"});
  assert.equal(view.preliminary.length, 1);
  assert.deepEqual(view.leaderboard, []);
  assert.deepEqual(view.efficiency, []);
  assert.deepEqual(view.funnel, []);
  assert.equal(view.preliminary[0].decode_tokens_per_second, null);
  const leaked = structuredClone(merged);
  leaked.runs.find((r) => r.profile === "preliminary").preliminary[0].answer = "private text";
  assert.throws(() => Core.validateDashboardData(leaked));
});

test("preliminary ranges preserve missing data and chart series preserve source order", () => {
  const Preliminary = require(path.join(ROOT, "dashboard/js/preliminary.js"));
  const format = (n) => String(n);
  assert.equal(Preliminary.formatRange(null, null, null, format, "Non disponibile"), "Non disponibile");
  assert.equal(Preliminary.formatRange(NaN, 1, 2, format, "N/A"), "N/A");
  assert.equal(Preliminary.formatRange(2, null, null, format, "N/A"), "2");
  assert.equal(Preliminary.formatRange(2, 1, 3, format, "N/A"), "2 [1–3]");
  const rows = [
    {model:"slow",context:"short",status:"measured",duration_seconds:20,known_correct:0,known_total:8},
    {model:"missing",context:"long",status:"unavailable",duration_seconds:null,known_correct:0,known_total:0},
    {model:"excluded",context:"short",status:"excluded",duration_seconds:3,known_correct:8,known_total:8},
  ];
  const original = JSON.stringify(rows);
  const series = Preliminary.metricSeries(rows, "duration_seconds");
  assert.deepEqual(series.map((r) => r.model), ["slow","missing","excluded"]);
  assert.deepEqual(series.map((r) => r.value), [20,null,null]);
  assert.deepEqual(Preliminary.groundingSeries(rows,"known").map((r) => r.value), [0,null,null]);
  assert.equal(JSON.stringify(rows), original);
  const source = fs.readFileSync(path.join(ROOT, "dashboard/js/preliminary.js"), "utf8");
  assert.doesNotMatch(source, /innerHTML|\bfetch\s*\(|XMLHttpRequest|WebSocket/);
});

test("preliminary sample charts distinguish failures, zero success and missing evidence", () => {
  const P = require(path.join(ROOT, "dashboard/js/preliminary.js"));
  const rows = [
    {model:"failed",context:"short",status:"unavailable",samples:3,completed:0,failed:3,truncated:0},
    {model:"absent",context:"long",status:"unavailable",samples:0,completed:0,failed:0,truncated:0},
    {model:"excluded",context:"long",status:"excluded",samples:3,completed:3,failed:0,truncated:2},
  ];
  const series = P.sampleSeries(rows);
  assert.deepEqual(series.slice(0,3).map((r) => r.value), [0,100,0]);
  assert.deepEqual(series.slice(3).map((r) => r.value), [null,null,null,null,null,null]);
  assert.equal(series[1].count, 3);
  assert.equal(series[1].total, 3);
});
