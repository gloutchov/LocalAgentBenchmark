(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) {
    root.LocalAgentDashboardCore = api;
    root.LocalAgentDashboard = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SCHEMA_VERSION = 3;
  const SUPPORTED_SCHEMA_VERSIONS = new Set([1, 2, 3]);
  const EXCLUSION_REASONS = new Set([
    "thinking_observed_off", "thinking_unverified", "workspace_boundary",
    "repository_mutation", "snapshot_mutation", "integrity_other",
  ]);
  const PROFILE_ORDER = ["smoke", "standard", "full", "thinking", "showcase"];
  const FUNNEL_PIPELINE = ["smoke", "standard", "full"];
  const SORT_FIELDS = new Set([
    "rank",
    "overall_score",
    "quality_score",
    "completion_rate",
    "speed_score",
    "token_efficiency_score",
    "median_duration_seconds",
    "median_output_tokens",
  ]);

  function fail(message) {
    throw new Error(message);
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isText(value) {
    return typeof value === "string" && value.trim().length > 0;
  }

  function isNullableNumber(value) {
    return value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0);
  }

  function isNullableInteger(value) {
    return value === null || (Number.isInteger(value) && value >= 0);
  }

  function isNullableText(value) {
    return value === null || isText(value);
  }

  function exactKeys(value, keys, label) {
    if (!isObject(value)) fail(`Invalid ${label}`);
    const actual = Object.keys(value).sort();
    const expected = [...keys].sort();
    if (JSON.stringify(actual) !== JSON.stringify(expected)) fail(`Invalid fields in ${label}`);
  }

  function uniqueTextList(value, label) {
    if (!Array.isArray(value) || value.some((item) => !isText(item))) fail(`${label} must be a string list`);
    if (new Set(value).size !== value.length) fail(`${label} contains duplicates`);
  }

  function validateLeaderboard(row, runId) {
    exactKeys(
      row,
      [
        "rank",
        "model",
        "overall_score",
        "quality_score",
        "completion_rate",
        "speed_score",
        "token_efficiency_score",
        "median_duration_seconds",
        "median_output_tokens",
        "median_cpu_seconds",
        "median_energy_joules",
        "score_stddev",
        "successful_tasks",
        "total_tasks",
        "case_scores",
      ],
      `leaderboard row in ${runId}`
    );
    if (!isObject(row) || !isText(row.model)) fail(`Invalid leaderboard row in ${runId}`);
    if (
      !Number.isInteger(row.rank) ||
      row.rank < 1 ||
      !isObject(row.case_scores) ||
      Object.entries(row.case_scores).some(([caseId, score]) => !isText(caseId) || !isNullableNumber(score) || score === null)
    ) {
      fail(`Invalid leaderboard metadata in ${runId}`);
    }
    if (!isNullableInteger(row.successful_tasks) || !isNullableInteger(row.total_tasks)) {
      fail(`Invalid leaderboard task counts in ${runId}`);
    }
    for (const key of [
      "overall_score",
      "quality_score",
      "completion_rate",
      "speed_score",
      "token_efficiency_score",
      "median_duration_seconds",
      "median_output_tokens",
      "median_cpu_seconds",
      "median_energy_joules",
      "score_stddev",
    ]) {
      if (!isNullableNumber(row[key])) fail(`Invalid ${key} in ${runId}`);
    }
  }

  function validateTask(task, runId) {
    exactKeys(
      task,
      [
        "model",
        "case_id",
        "case_title",
        "case_title_en",
        "category",
        "repetition",
        "status",
        "state",
        "score",
        "max_score",
        "duration_seconds",
        "output_tokens",
        "tool_calls",
        "tool_errors",
        "cpu_seconds",
        "energy_joules",
        "integrity_valid",
      ],
      `task in ${runId}`
    );
    if (
      !isObject(task) ||
      !isText(task.model) ||
      !isText(task.case_id) ||
      !isText(task.case_title) ||
      !isText(task.case_title_en) ||
      !isText(task.category) ||
      !isText(task.status)
    ) {
      fail(`Invalid task in ${runId}`);
    }
    if (
      !["passed", "below_threshold", "timeout", "error", "missing_score", "integrity_excluded"].includes(task.state) ||
      !Number.isInteger(task.repetition) ||
      task.repetition < 1 ||
      !isNullableInteger(task.output_tokens) ||
      !isNullableInteger(task.tool_calls) ||
      !isNullableInteger(task.tool_errors) ||
      (task.integrity_valid !== null && typeof task.integrity_valid !== "boolean")
    ) {
      fail(`Invalid task metadata in ${runId}`);
    }
    if (!isText(task.state) || !isText(task.status)) fail(`Invalid task state in ${runId}`);
    for (const key of ["score", "max_score", "duration_seconds", "cpu_seconds", "energy_joules"]) {
      if (!isNullableNumber(task[key])) fail(`Invalid task ${key} in ${runId}`);
    }
  }

  function validateDashboardData(dataset) {
    if (!isObject(dataset) || !SUPPORTED_SCHEMA_VERSIONS.has(dataset.schema_version)) {
      fail("Unsupported dashboard schema");
    }
    exactKeys(dataset, ["schema_version", "profile_order", "runs", "funnel"], "dashboard dataset");
    uniqueTextList(dataset.profile_order, "profile_order");
    if (dataset.profile_order.length === 0) fail("profile_order cannot be empty");
    if (!Array.isArray(dataset.runs) || dataset.runs.length === 0) fail("runs cannot be empty");
    if (!Array.isArray(dataset.funnel)) fail("funnel must be a list");

    const profiles = new Set(dataset.profile_order);
    const runIds = new Set();
    for (const run of dataset.runs) {
      const runFields = [
        "id",
        "profile",
        "benchmark_version",
        "started_at",
        "finished_at",
        "provenance",
        "sandbox",
        "integrity",
        "participants",
        "leaderboard",
        "tasks",
      ];
      if (dataset.schema_version >= 2) runFields.push("thinking_control");
      if (dataset.schema_version >= 3) runFields.push("exclusions");
      exactKeys(
        run,
        runFields,
        "dashboard run"
      );
      if (!isObject(run) || !isText(run.id) || !profiles.has(run.profile)) fail("Invalid dashboard run");
      if (!isText(run.benchmark_version) || !isNullableText(run.started_at) || !isNullableText(run.finished_at)) {
        fail(`Invalid dashboard run metadata in ${run.id}`);
      }
      if (runIds.has(run.id)) fail(`Duplicate run id: ${run.id}`);
      runIds.add(run.id);
      uniqueTextList(run.participants, `participants in ${run.id}`);
      if (!Array.isArray(run.leaderboard) || !Array.isArray(run.tasks)) fail(`Invalid lists in ${run.id}`);
      run.leaderboard.forEach((row) => validateLeaderboard(row, run.id));
      run.tasks.forEach((task) => validateTask(task, run.id));
      if (!isObject(run.integrity) || !Array.isArray(run.integrity.disqualified_models)) {
        fail(`Invalid integrity in ${run.id}`);
      }
      exactKeys(run.integrity, ["status", "disqualified_models"], `integrity in ${run.id}`);
      uniqueTextList(run.integrity.disqualified_models, `disqualified_models in ${run.id}`);
      if (dataset.schema_version >= 3) {
        if (!Array.isArray(run.exclusions)) fail(`Invalid exclusions in ${run.id}`);
        run.exclusions.forEach((exclusion) => {
          exactKeys(exclusion, ["model", "reason", "case_id"], `exclusion in ${run.id}`);
          if (!run.integrity.disqualified_models.includes(exclusion.model) ||
              !EXCLUSION_REASONS.has(exclusion.reason) ||
              (exclusion.case_id !== null &&
                (typeof exclusion.case_id !== "string" ||
                 !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(exclusion.case_id)))) {
            fail(`Invalid exclusion in ${run.id}`);
          }
        });
      }
      if (dataset.schema_version >= 2) {
        exactKeys(
          run.thinking_control,
          ["version", "status", "requested", "reasoning_effort", "source"],
          `thinking control in ${run.id}`
        );
        if (
          !Number.isInteger(run.thinking_control.version) ||
          run.thinking_control.version < 0 ||
          !isText(run.thinking_control.status) ||
          !isText(run.thinking_control.requested) ||
          !isNullableText(run.thinking_control.reasoning_effort) ||
          !isText(run.thinking_control.source)
        ) {
          fail(`Invalid thinking control in ${run.id}`);
        }
      }
      exactKeys(
        run.provenance,
        ["run_schema_version", "report_schema_version", "run_sha256", "report_sha256", "repository_commit"],
        `provenance in ${run.id}`
      );
      exactKeys(
        run.sandbox,
        ["backend", "enforced", "filesystem_isolation", "process_isolation", "network_isolation"],
        `sandbox in ${run.id}`
      );
      if (
        ![2, 3, 4].includes(run.provenance.run_schema_version) ||
        ![2, 3, 4].includes(run.provenance.report_schema_version) ||
        !/^[a-f0-9]{64}$/.test(run.provenance.run_sha256) ||
        !/^[a-f0-9]{64}$/.test(run.provenance.report_sha256) ||
        !isNullableText(run.provenance.repository_commit) ||
        !isText(run.sandbox.backend) ||
        ["enforced", "filesystem_isolation", "process_isolation", "network_isolation"].some(
          (key) => typeof run.sandbox[key] !== "boolean"
        ) ||
        !isText(run.integrity.status)
      ) {
        fail(`Invalid metadata in ${run.id}`);
      }
      if (!isObject(run.sandbox) || !isObject(run.provenance)) fail(`Invalid metadata in ${run.id}`);
    }

    const funnelProfiles = dataset.funnel.map((stage) => (isObject(stage) ? stage.profile : null));
    const expectedFunnelProfiles =
      dataset.schema_version === 1
        ? dataset.profile_order
        : FUNNEL_PIPELINE.filter((profile) => profiles.has(profile));
    if (JSON.stringify(funnelProfiles) !== JSON.stringify(expectedFunnelProfiles)) {
      fail("Funnel does not match profile_order");
    }
    for (const stage of dataset.funnel) {
      exactKeys(
        stage,
        [
          "profile",
          "run_ids",
          "participants",
          "new_participants",
          "next_profile",
          "continued_to_next",
          "not_run_in_next",
        ],
        `funnel stage ${stage.profile}`
      );
      for (const key of [
        "run_ids",
        "participants",
        "new_participants",
        "continued_to_next",
        "not_run_in_next",
      ]) {
        uniqueTextList(stage[key], `${key} in ${stage.profile}`);
      }
      if (stage.next_profile !== null && !profiles.has(stage.next_profile)) fail("Invalid next funnel profile");
    }
    return true;
  }

  function canonical(value) {
    if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
    if (isObject(value)) {
      return `{${Object.keys(value)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
        .join(",")}}`;
    }
    return JSON.stringify(value);
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function profileOrder(profiles) {
    const available = new Set(profiles);
    const ordered = PROFILE_ORDER.filter((profile) => available.has(profile));
    const extras = [...available].filter((profile) => !PROFILE_ORDER.includes(profile)).sort();
    return ordered.concat(extras);
  }

  function buildFunnel(runs, order) {
    const funnelOrder = FUNNEL_PIPELINE.filter((profile) => order.includes(profile));
    const runIds = new Map();
    const participants = new Map();
    order.forEach((profile) => {
      runIds.set(profile, []);
      participants.set(profile, new Set());
    });
    for (const run of runs) {
      runIds.get(run.profile).push(run.id);
      run.participants.forEach((model) => participants.get(run.profile).add(model));
    }
    return funnelOrder.map((profile, index) => {
      const current = participants.get(profile);
      const previous = index > 0 ? participants.get(funnelOrder[index - 1]) : new Set();
      const nextProfile = index + 1 < funnelOrder.length ? funnelOrder[index + 1] : null;
      const following = nextProfile ? participants.get(nextProfile) : new Set();
      const sorted = (values) => [...values].sort((a, b) => a.localeCompare(b));
      return {
        profile,
        run_ids: [...runIds.get(profile)].sort(),
        participants: sorted(current),
        new_participants: sorted(index === 0 ? current : new Set([...current].filter((item) => !previous.has(item)))),
        next_profile: nextProfile,
        continued_to_next: nextProfile ? sorted(new Set([...current].filter((item) => following.has(item)))) : [],
        not_run_in_next: nextProfile ? sorted(new Set([...current].filter((item) => !following.has(item)))) : [],
      };
    });
  }

  function normalizeRun(run, schemaVersion) {
    const normalized = clone(run);
    if (schemaVersion < 2) {
      normalized.thinking_control = {
        version: 0,
        status: "unverified",
        requested: "unknown",
        reasoning_effort: null,
        source: "legacy_unverified",
      };
    }
    if (schemaVersion < 3) normalized.exclusions = [];
    return normalized;
  }

  function mergeDashboardData(datasets) {
    if (!Array.isArray(datasets) || datasets.length === 0) fail("Select at least one dashboard dataset");
    const runsById = new Map();
    const profiles = [];
    for (const dataset of datasets) {
      validateDashboardData(dataset);
      dataset.profile_order.forEach((profile) => profiles.push(profile));
      for (const run of dataset.runs) {
        const normalized = normalizeRun(run, dataset.schema_version);
        const existing = runsById.get(run.id);
        if (existing && canonical(existing) !== canonical(normalized)) fail(`Run id collision: ${run.id}`);
        if (!existing) runsById.set(run.id, normalized);
      }
    }
    const order = profileOrder(profiles);
    const index = new Map(order.map((profile, position) => [profile, position]));
    const runs = [...runsById.values()].sort(
      (left, right) => index.get(left.profile) - index.get(right.profile) || left.id.localeCompare(right.id)
    );
    const merged = { schema_version: SCHEMA_VERSION, profile_order: order, runs, funnel: buildFunnel(runs, order) };
    validateDashboardData(merged);
    return merged;
  }

  function collectModels(runs) {
    const models = new Set();
    for (const run of runs) {
      run.participants.forEach((model) => models.add(model));
      run.leaderboard.forEach((row) => models.add(row.model));
      run.tasks.forEach((task) => models.add(task.model));
      run.integrity.disqualified_models.forEach((model) => models.add(model));
      (run.exclusions || []).forEach((exclusion) => models.add(exclusion.model));
    }
    return [...models].sort((a, b) => a.localeCompare(b));
  }

  function compareRows(left, right, field, direction) {
    const a = left[field];
    const b = right[field];
    if (a === null || a === undefined) return b === null || b === undefined ? 0 : 1;
    if (b === null || b === undefined) return -1;
    const comparison = typeof a === "string" ? a.localeCompare(b) : Number(a) - Number(b);
    return direction === "asc" ? comparison : -comparison;
  }

  function buildLogDomain(values) {
    const positive = values.filter((value) => typeof value === "number" && Number.isFinite(value) && value > 0);
    if (!positive.length) return null;
    const minimum = Math.min(...positive);
    const maximum = Math.max(...positive);
    const rawLow = Math.log10(minimum);
    const rawHigh = Math.log10(maximum);
    const span = rawHigh - rawLow;
    const padding = span === 0 ? 0.35 : Math.max(0.06, span * 0.08);
    const low = rawLow - padding;
    const high = rawHigh + padding;
    const ticks = [];
    for (let exponent = Math.floor(low) - 1; exponent <= Math.ceil(high) + 1; exponent += 1) {
      for (const multiplier of [1, 2, 5]) {
        const tick = multiplier * 10 ** exponent;
        if (tick >= 10 ** low && tick <= 10 ** high) ticks.push(tick);
      }
    }
    if (!ticks.length) ticks.push(minimum);
    const uniqueTicks = [...new Set(ticks)].sort((left, right) => left - right);
    const visibleTicks = uniqueTicks.length <= 7
      ? uniqueTicks
      : [...new Set(Array.from({ length: 7 }, (_item, index) => uniqueTicks[Math.round(index * (uniqueTicks.length - 1) / 6)]))];
    return {
      minimum: 10 ** low,
      maximum: 10 ** high,
      ticks: visibleTicks,
    };
  }

  function efficiencyState(row) {
    if (typeof row.completion_rate !== "number" || row.completion_rate <= 0) return "below";
    return row.completion_rate >= 100 ? "complete" : "partial";
  }

  function buildEfficiencyPlot(points, field) {
    const plotted = points.filter((point) => typeof point[field] === "number" && point[field] > 0);
    const domain = buildLogDomain(plotted.map((point) => point[field]));
    return {
      field,
      domain,
      points: plotted,
      omitted_count: points.length - plotted.length,
    };
  }

  function buildEfficiencyCohorts(leaderboard, runOrder) {
    const groups = new Map();
    leaderboard.forEach((row) => {
      if (typeof row.quality_score !== "number") return;
      if (!groups.has(row.run_id)) groups.set(row.run_id, []);
      groups.get(row.run_id).push({
        rank: row.rank,
        model: row.model,
        quality_score: row.quality_score,
        completion_rate: row.completion_rate,
        median_duration_seconds: row.median_duration_seconds,
        median_output_tokens: row.median_output_tokens,
        state: efficiencyState(row),
        profile: row.profile,
        thinking_mode: row.thinking_mode,
      });
    });
    const cohorts = [...groups.entries()].map(([runId, rawPoints]) => {
      const points = rawPoints.sort((left, right) => left.rank - right.rank || left.model.localeCompare(right.model));
      const qualityMaximum = Math.max(100, ...points.map((point) => point.quality_score));
      return {
        run_id: runId,
        profile: points[0].profile,
        thinking_mode: points[0].thinking_mode,
        quality_maximum: Math.ceil(qualityMaximum / 25) * 25,
        duration: buildEfficiencyPlot(points, "median_duration_seconds"),
        tokens: buildEfficiencyPlot(points, "median_output_tokens"),
      };
    });
    if (Array.isArray(runOrder)) {
      const positions = new Map(runOrder.map((runId, index) => [runId, index]));
      cohorts.sort((left, right) => (positions.get(left.run_id) ?? Number.MAX_SAFE_INTEGER) - (positions.get(right.run_id) ?? Number.MAX_SAFE_INTEGER));
    }
    return cohorts;
  }

  function createDashboardView(dataset, filters) {
    validateDashboardData(dataset);
    const options = filters && isObject(filters) ? filters : {};
    const selectedProfile = dataset.profile_order.includes(options.profile) ? options.profile : "all";
    const selectedModel = isText(options.model) ? options.model : "all";
    const query = isText(options.query) ? options.query.trim().toLocaleLowerCase() : "";
    const sortBy = SORT_FIELDS.has(options.sortBy) ? options.sortBy : "overall_score";
    const sortDirection = options.sortDirection === "asc" ? "asc" : "desc";
    const runs = dataset.runs.filter((run) => selectedProfile === "all" || run.profile === selectedProfile);
    const availableModels = collectModels(runs);

    const leaderboard = runs
      .flatMap((run) =>
        run.leaderboard.map((row) => ({
          ...clone(row),
          run_id: run.id,
          profile: run.profile,
          thinking_mode: run.thinking_control ? run.thinking_control.requested : "unknown",
        }))
      )
      .filter((row) => selectedModel === "all" || row.model === selectedModel)
      .sort((left, right) => compareRows(left, right, sortBy, sortDirection) || left.model.localeCompare(right.model));
    const efficiency = buildEfficiencyCohorts(leaderboard, runs.map((run) => run.id));

    const tasks = runs
      .flatMap((run) => run.tasks.map((task) => ({
        ...clone(task),
        run_id: run.id,
        profile: run.profile,
        thinking_mode: run.thinking_control ? run.thinking_control.requested : "unknown",
      })))
      .filter((task) => selectedModel === "all" || task.model === selectedModel)
      .filter((task) => {
        if (!query) return true;
        return [task.model, task.case_id, task.case_title, task.case_title_en, task.category]
          .filter((value) => typeof value === "string")
          .some((value) => value.toLocaleLowerCase().includes(query));
      });

    const exclusions = runs
      .flatMap((run) => (run.exclusions || []).map((exclusion) => ({
        ...clone(exclusion), run_id: run.id, profile: run.profile,
        thinking_mode: run.thinking_control.requested,
        sandbox_backend: run.sandbox.backend,
        sandbox_enforced: run.sandbox.enforced,
      })))
      .filter((exclusion) => selectedModel === "all" || exclusion.model === selectedModel)
      .filter((exclusion) => !query || [exclusion.model, exclusion.case_id, exclusion.reason]
        .filter((value) => typeof value === "string")
        .some((value) => value.toLocaleLowerCase().includes(query)));

    let funnel = dataset.funnel.filter((stage) => selectedProfile === "all" || stage.profile === selectedProfile);
    if (selectedModel !== "all") {
      funnel = funnel.map((stage) => ({
        ...clone(stage),
        participants: stage.participants.filter((model) => model === selectedModel),
        new_participants: stage.new_participants.filter((model) => model === selectedModel),
        continued_to_next: stage.continued_to_next.filter((model) => model === selectedModel),
        not_run_in_next: stage.not_run_in_next.filter((model) => model === selectedModel),
      }));
    } else {
      funnel = clone(funnel);
    }

    const visibleModels = selectedModel === "all" ? collectModels(runs) : availableModels.includes(selectedModel) ? [selectedModel] : [];
    const bestScore = leaderboard.reduce(
      (best, row) => (typeof row.overall_score === "number" && (best === null || row.overall_score > best) ? row.overall_score : best),
      null
    );
    const disqualifiedModels = new Set();
    runs.forEach((run) => {
      run.integrity.disqualified_models
        .filter((model) => selectedModel === "all" || model === selectedModel)
        .forEach((model) => disqualifiedModels.add(model));
    });
    const summary = {
      runCount: runs.length,
      modelCount: visibleModels.length,
      taskCount: tasks.length,
      bestScore,
      passedCount: tasks.filter((task) => task.state === "passed").length,
      belowThresholdCount: tasks.filter((task) => task.state === "below_threshold").length,
      anomalousCount: tasks.filter((task) => ["timeout", "error", "missing_score", "integrity_excluded"].includes(task.state)).length,
      disqualifiedCount: disqualifiedModels.size,
      unverifiedThinkingCount: runs.filter(
        (run) => !run.thinking_control || run.thinking_control.status !== "passed"
      ).length,
    };

    return {
      profiles: [...dataset.profile_order],
      runs: clone(runs),
      leaderboard,
      efficiency,
      funnel,
      tasks,
      exclusions,
      availableModels,
      summary,
      filters: { profile: selectedProfile, model: selectedModel, query, sortBy, sortDirection },
    };
  }

  return {
    SCHEMA_VERSION,
    buildEfficiencyCohorts,
    buildFunnel,
    buildLogDomain,
    createDashboardView,
    mergeDashboardData,
    validateDashboardData,
  };
});
