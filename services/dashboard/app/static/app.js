const modeValue = document.getElementById("modeValue");
const policyVersionValue = document.getElementById("policyVersionValue");
const healthyWorkersValue = document.getElementById("healthyWorkersValue");
const timeModeValue = document.getElementById("timeModeValue");
const effectiveTimeValue = document.getElementById("effectiveTimeValue");
const simulatedTimeValue = document.getElementById("simulatedTimeValue");
const modeStatus = document.getElementById("modeStatus");
const servicesGrid = document.getElementById("servicesGrid");
const summaryGrid = document.getElementById("summaryGrid");
const workersGrid = document.getElementById("workersGrid");
const timeEventsList = document.getElementById("timeEventsList");
const refreshButton = document.getElementById("refreshButton");
const freezeTimeButton = document.getElementById("freezeTimeButton");
const resumeTimeButton = document.getElementById("resumeTimeButton");
const strategicRecommendation = document.getElementById("strategicRecommendation");
const previewRecommendation = document.getElementById("previewRecommendation");
const previewSaleButton = document.getElementById("previewSaleButton");
const previewWeekdayButton = document.getElementById("previewWeekdayButton");
const scenarioSelect = document.getElementById("scenarioSelect");
const experimentModeSelect = document.getElementById("experimentModeSelect");
const experimentRepeatCountSelect = document.getElementById("experimentRepeatCountSelect");
const runExperimentButton = document.getElementById("runExperimentButton");
const runBatchExperimentButton = document.getElementById("runBatchExperimentButton");
const refreshComparisonButton = document.getElementById("refreshComparisonButton");
const experimentStatus = document.getElementById("experimentStatus");
const latestRunSummary = document.getElementById("latestRunSummary");
const comparisonTableWrap = document.getElementById("comparisonTableWrap");
const experimentEventsList = document.getElementById("experimentEventsList");
const batchAggregateSummary = document.getElementById("batchAggregateSummary");

const chartTargets = {
  trafficChart: document.getElementById("trafficChart"),
  predictionChart: document.getElementById("predictionChart"),
  loadChart: document.getElementById("loadChart"),
  weightChart: document.getElementById("weightChart"),
  faultChart: document.getElementById("faultChart"),
  queueChart: document.getElementById("queueChart"),
  strategicBandChart: document.getElementById("strategicBandChart"),
  capacityChart: document.getElementById("capacityChart"),
  comparisonLatencyChart: document.getElementById("comparisonLatencyChart"),
  comparisonThroughputChart: document.getElementById("comparisonThroughputChart"),
  experimentPressureChart: document.getElementById("experimentPressureChart"),
  experimentWorkerLoadChart: document.getElementById("experimentWorkerLoadChart"),
  experimentPolicyWeightChart: document.getElementById("experimentPolicyWeightChart"),
};

const palette = [
  "#c6552d",
  "#1d6b45",
  "#2059a8",
  "#9b6a12",
  "#93348f",
  "#127f96",
];

let experimentScenarios = [];
let latestExperimentArtifacts = null;
let latestExperimentEvents = null;
let latestExperimentBatch = null;

function statusPill(status) {
  const normalized = status === "ok" ? "good" : status === "degraded" ? "warn" : "bad";
  return `<span class="pill ${normalized}">${status}</span>`;
}

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? `${value}` : value.toFixed(2);
  }
  return `${value}`;
}

function formatTimestamp(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function renderServices(services) {
  servicesGrid.innerHTML = Object.values(services)
    .map(
      (service) => `
        <article class="service-card">
          <h3>${service.service}</h3>
          <p>${statusPill(service.status)}</p>
          <p><strong>Generated</strong>: ${service.generated_at || "-"}</p>
        </article>
      `
    )
    .join("");
}

function renderSummary(summary) {
  const rows = [
    ["Healthy Gateways", summary.healthy_gateways],
    ["Healthy Workers", summary.healthy_workers],
    ["Total Inflight", summary.total_worker_inflight],
    ["Max Load Score", summary.max_worker_load_score],
    ["Max Predicted Pressure", summary.max_predicted_pressure],
    ["Prediction Count", summary.prediction_count],
  ];
  summaryGrid.innerHTML = rows
    .map(
      ([label, value]) => `
        <dt>${label}</dt>
        <dd>${formatNumber(value)}</dd>
      `
    )
    .join("");
}

function renderRecommendationCard(target, title, payload) {
  if (!payload) {
    target.innerHTML = '<div class="chart-empty">Recommendation unavailable.</div>';
    return;
  }

  const strategic = payload.strategic_forecast;
  const scale = payload.scale_recommendation;
  if (!strategic || !scale) {
    target.innerHTML = '<div class="chart-empty">No strategic recommendation available.</div>';
    return;
  }

  target.innerHTML = `
    <article class="strategic-card">
      <h3>${title}</h3>
      <p><strong>Demand Level</strong>: ${strategic.demand_level}</p>
      <p><strong>Peak Expected RPS</strong>: ${formatNumber(strategic.peak_expected_rps)}</p>
      <p><strong>Avg Expected RPS</strong>: ${formatNumber(strategic.avg_expected_rps)}</p>
      <p><strong>Target Workers</strong>: ${formatNumber(scale.target_workers)}</p>
      <p><strong>Action</strong>: ${scale.action}</p>
      <p><strong>Matched Strategy</strong>: ${(strategic.matched_strategies || []).join(", ") || "-"}</p>
      <p><strong>Event Types</strong>: ${(strategic.event_types || []).join(", ") || "-"}</p>
    </article>
  `;
}

function renderLatestRunSummary(runPayload, executionPayload, artifactsPayload = null) {
  if (!runPayload || !executionPayload) {
    latestRunSummary.innerHTML = '<div class="chart-empty">No experiment run executed yet.</div>';
    return;
  }
  const summary = artifactsPayload?.summary || executionPayload.summary || {};
  latestRunSummary.innerHTML = `
    <article class="strategic-card">
      <h3>${runPayload.scenario_id}</h3>
      <p><strong>Run Id</strong>: ${runPayload.run_id}</p>
      <p><strong>Mode</strong>: ${runPayload.mode}</p>
      <p><strong>Status</strong>: ${runPayload.status}</p>
      <p><strong>P95 Latency</strong>: ${formatNumber(summary.latency_p95_ms)} ms</p>
      <p><strong>Throughput</strong>: ${formatNumber(summary.throughput_avg_rps)} rps</p>
      <p><strong>Failures</strong>: ${formatNumber(summary.requests_failed)}</p>
      <p><strong>Policy Shifts</strong>: ${formatNumber(summary.policy_shift_count)}</p>
      <p><strong>Target Worker Shifts</strong>: ${formatNumber(summary.target_worker_shift_count)}</p>
      <p><strong>Scale Action Shifts</strong>: ${formatNumber(summary.scale_action_shift_count)}</p>
    </article>
  `;
}

function renderComparisonTable(comparisonPayload) {
  const runs = comparisonPayload?.runs || [];
  if (!runs.length) {
    comparisonTableWrap.innerHTML = '<div class="chart-empty">No comparison runs for this scenario yet.</div>';
    return;
  }
  comparisonTableWrap.innerHTML = `
    <table class="comparison-table">
      <thead>
        <tr>
          <th>Mode</th>
          <th>P50</th>
          <th>P95</th>
          <th>P99</th>
          <th>RPS</th>
          <th>Error</th>
          <th>Queue</th>
        </tr>
      </thead>
      <tbody>
        ${runs
          .map(
            (run) => `
              <tr>
                <td>${run.mode}</td>
                <td>${formatNumber(run.latency_p50_ms)}</td>
                <td>${formatNumber(run.latency_p95_ms)}</td>
                <td>${formatNumber(run.latency_p99_ms)}</td>
                <td>${formatNumber(run.throughput_avg_rps)}</td>
                <td>${formatNumber(run.error_rate)}</td>
                <td>${formatNumber(run.max_queue_depth)}</td>
              </tr>
            `
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderBatchAggregateSummary(batchPayload) {
  const aggregates = batchPayload?.aggregates || [];
  if (!aggregates.length) {
    batchAggregateSummary.innerHTML = '<div class="chart-empty">No repeated batch executed yet.</div>';
    return;
  }

  batchAggregateSummary.innerHTML = aggregates
    .map(
      (aggregate) => `
        <article class="strategic-card">
          <h3>${aggregate.mode}</h3>
          <p><strong>Run Count</strong>: ${formatNumber(aggregate.run_count)}</p>
          <p><strong>Avg P95</strong>: ${formatNumber(aggregate.avg_latency_p95_ms)} ms</p>
          <p><strong>Best P95</strong>: ${formatNumber(aggregate.best_latency_p95_ms)} ms</p>
          <p><strong>Worst P95</strong>: ${formatNumber(aggregate.worst_latency_p95_ms)} ms</p>
          <p><strong>Avg Throughput</strong>: ${formatNumber(aggregate.avg_throughput_avg_rps)} rps</p>
          <p><strong>Avg Queue</strong>: ${formatNumber(aggregate.avg_max_queue_depth)}</p>
          <p><strong>Avg Policy Shifts</strong>: ${formatNumber(aggregate.avg_policy_shift_count)}</p>
        </article>
      `
    )
    .join("");
}

function renderExperimentEventTimeline(eventsPayload) {
  const events = eventsPayload?.events || [];
  if (!events.length) {
    experimentEventsList.innerHTML = '<div class="chart-empty">No run events recorded yet.</div>';
    return;
  }

  const styleMap = {
    policy_weight_shift: "warn",
    target_workers_shift: "good",
    scale_action_shift: "good",
    fault_injected: "bad",
  };

  experimentEventsList.innerHTML = events
    .map((event) => {
      const label = event.event_type.replaceAll("_", " ");
      const style = styleMap[event.event_type] || "good";
      const payload = event.payload || {};
      let detail = "";
      if (event.event_type === "policy_weight_shift") {
        detail = `${payload.worker_id}: ${formatNumber(payload.previous)} -> ${formatNumber(payload.current)}`;
      } else if (event.event_type === "target_workers_shift" || event.event_type === "scale_action_shift") {
        detail = `${formatNumber(payload.previous)} -> ${formatNumber(payload.current)}`;
      }
      return `
        <article class="time-event-card">
          <div>
            <strong>${label}</strong>
            <p>${formatTimestamp(event.timestamp)}</p>
            ${detail ? `<p>${detail}</p>` : ""}
          </div>
          <div class="time-event-meta">
            <span class="pill ${style}">${event.event_type}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function buildComparisonSeries(runs, selector, colorOffset = 0) {
  return runs.map((run, index) => ({
    label: run.mode,
    color: palette[(index + colorOffset) % palette.length],
    values: [selector(run)],
  }));
}

function renderComparisonBarChart(target, chartTitle, runs, selector, colorOffset = 0) {
  if (!runs.length) {
    renderEmptyChart(target);
    return;
  }

  const width = 560;
  const height = 220;
  const leftPad = 44;
  const topPad = 16;
  const bottomPad = 42;
  const chartWidth = width - leftPad - 10;
  const chartHeight = height - topPad - bottomPad;
  const maxValue = Math.max(...runs.map((run) => selector(run) || 0), 1);
  const barWidth = Math.max(36, chartWidth / Math.max(runs.length * 1.8, 2));
  const gap = chartWidth / Math.max(runs.length, 1);

  const gridLines = [];
  for (let tick = 0; tick <= 4; tick += 1) {
    const ratio = tick / 4;
    const y = topPad + (chartHeight * ratio);
    const value = (maxValue * (1 - ratio)).toFixed(maxValue < 10 ? 2 : 1);
    gridLines.push(`<line class="chart-grid-line" x1="${leftPad}" y1="${y}" x2="${width - 10}" y2="${y}" />`);
    gridLines.push(`<text class="chart-label" x="0" y="${y + 4}">${value}</text>`);
  }

  const bars = runs
    .map((run, index) => {
      const value = selector(run) || 0;
      const x = leftPad + (gap * index) + ((gap - barWidth) / 2);
      const barHeight = (value / maxValue) * chartHeight;
      const y = topPad + chartHeight - barHeight;
      const color = palette[(index + colorOffset) % palette.length];
      return `
        <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="10" fill="${color}" class="comparison-bar" />
        <text class="chart-value-label" x="${x + (barWidth / 2) - 12}" y="${Math.max(y - 6, topPad + 10)}">${formatNumber(value)}</text>
        <text class="chart-label" x="${x - 8}" y="${height - 12}">${run.mode}</text>
      `;
    })
    .join("");

  target.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${chartTitle}">
      ${gridLines.join("")}
      <line class="chart-axis-line" x1="${leftPad}" y1="${height - bottomPad}" x2="${width - 10}" y2="${height - bottomPad}" />
      ${bars}
    </svg>
  `;
}

function renderExperimentCharts(comparisonPayload) {
  const runs = comparisonPayload?.runs || [];
  if (!runs.length) {
    renderEmptyChart(chartTargets.comparisonLatencyChart);
    renderEmptyChart(chartTargets.comparisonThroughputChart);
    return;
  }
  renderComparisonBarChart(
    chartTargets.comparisonLatencyChart,
    "Latency Comparison",
    runs,
    (run) => run.latency_p95_ms ?? 0
  );
  renderComparisonBarChart(
    chartTargets.comparisonThroughputChart,
    "Throughput Comparison",
    runs,
    (run) => run.throughput_avg_rps ?? 0,
    2
  );
}

function selectLatestRunFromComparison(comparisonPayload) {
  const runs = comparisonPayload?.runs || [];
  if (!runs.length) {
    return null;
  }
  return [...runs].sort((left, right) => `${right.run_id}`.localeCompare(`${left.run_id}`))[0];
}

function renderExperimentRunCharts(artifactsPayload, eventsPayload) {
  const systemPoints = artifactsPayload?.timeseries || [];
  const workerPoints = artifactsPayload?.worker_timeseries || [];
  const labels = systemPoints.map((point) => formatTimeLabel(point.timestamp));
  const events = eventsPayload?.events || [];
  const markerTimestamps = new Set(
    events
      .filter((event) =>
        [
          "time_preset_applied",
          "orchestrator_mode_applied",
          "fault_injected",
          "load_generator_completed",
          "policy_weight_shift",
          "target_workers_shift",
          "scale_action_shift",
        ].includes(event.event_type)
      )
      .map((event) => event.timestamp)
  );
  const markers = systemPoints
    .map((point, index) => {
      if (!markerTimestamps.has(point.timestamp)) {
        return null;
      }
      const event = events.find((entry) => entry.timestamp === point.timestamp);
      const shortLabelMap = {
        time_preset_applied: "Preset",
        orchestrator_mode_applied: "Mode",
        fault_injected: "Fault",
        load_generator_completed: "Done",
        policy_weight_shift: "Weight",
        target_workers_shift: "Target",
        scale_action_shift: "Scale",
      };
      return {
        index,
        shortLabel: shortLabelMap[event?.event_type] || "Event",
      };
    })
    .filter(Boolean);

  if (!systemPoints.length) {
    renderEmptyChart(chartTargets.experimentPressureChart);
    renderEmptyChart(chartTargets.experimentWorkerLoadChart);
    renderEmptyChart(chartTargets.experimentPolicyWeightChart);
    renderExperimentEventTimeline(eventsPayload);
    return;
  }

  const workerIds = Array.from(new Set(workerPoints.map((point) => point.worker_id).filter(Boolean)));
  const workerSeries = (selector) =>
    workerIds.map((workerId, index) => ({
      label: workerId,
      color: workerColor(workerId, index),
      values: systemPoints.map((systemPoint) => {
        const workerPoint = workerPoints.find(
          (point) => point.worker_id === workerId && point.timestamp === systemPoint.timestamp
        );
        return workerPoint ? selector(workerPoint) : 0;
      }),
    }));

  renderLineChart(
    chartTargets.experimentPressureChart,
    "Run Pressure",
    labels,
    [
      {
        label: "Max Queue Depth",
        color: "#9b6a12",
        values: systemPoints.map((point) => point.max_queue_depth ?? 0),
      },
      {
        label: "Max Predicted Pressure",
        color: "#1d6b45",
        values: systemPoints.map((point) => point.max_predicted_pressure ?? 0),
      },
      {
        label: "Target Workers",
        color: "#93348f",
        values: systemPoints.map((point) => point.target_workers ?? 0),
      },
    ],
    markers
  );

  renderLineChart(
    chartTargets.experimentWorkerLoadChart,
    "Run Worker Load",
    labels,
    workerSeries((point) => point.load_score ?? 0),
    markers
  );

  renderLineChart(
    chartTargets.experimentPolicyWeightChart,
    "Run Policy Weights",
    labels,
    workerSeries((point) => point.policy_weight ?? 0),
    markers
  );

  renderExperimentEventTimeline(eventsPayload);
}

function populateScenarioSelect(scenarios) {
  experimentScenarios = scenarios || [];
  scenarioSelect.innerHTML = experimentScenarios
    .map(
      (scenario) =>
        `<option value="${scenario.scenario_id}">${scenario.scenario_id} - ${scenario.description || "scenario"}</option>`
    )
    .join("");
}

function renderTimeEvents(historyPoints) {
  const events = historyPoints
    .filter((point) => point.time_event)
    .slice(-6)
    .reverse();

  if (!events.length) {
    timeEventsList.innerHTML = '<div class="chart-empty">No time jumps captured yet.</div>';
    return;
  }

  timeEventsList.innerHTML = events
    .map((point) => {
      const event = point.time_event;
      return `
        <article class="time-event-card">
          <div>
            <strong>${event.label}</strong>
            <p>${formatTimestamp(point.control_plane?.effective_time_utc)}</p>
          </div>
          <div class="time-event-meta">
            <span class="pill good">${event.action}</span>
            <span>${formatTimestamp(event.recorded_at)}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function setModeButtons(activeMode) {
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === activeMode);
  });
}

async function setMode(mode) {
  modeStatus.textContent = `Updating mode to ${mode}...`;
  const response = await fetch("/api/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!response.ok) {
    modeStatus.textContent = `Mode update failed: ${await response.text()}`;
    return;
  }
  modeStatus.textContent = `Mode updated to ${mode}.`;
  await refreshAll();
}

async function injectLatency(workerId) {
  modeStatus.textContent = `Injecting latency fault into ${workerId}...`;
  const response = await fetch(`/api/workers/${workerId}/faults/latency`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ delay_ms: 800, duration_seconds: 60 }),
  });
  if (!response.ok) {
    modeStatus.textContent = `Fault injection failed: ${await response.text()}`;
    return;
  }
  modeStatus.textContent = `Injected 800 ms latency into ${workerId}.`;
  await refreshAll();
}

async function clearFaults(workerId) {
  modeStatus.textContent = `Clearing faults on ${workerId}...`;
  const response = await fetch(`/api/workers/${workerId}/faults/clear`, {
    method: "POST",
  });
  if (!response.ok) {
    modeStatus.textContent = `Fault clear failed: ${await response.text()}`;
    return;
  }
  modeStatus.textContent = `Cleared faults on ${workerId}.`;
  await refreshAll();
}

async function freezeTime() {
  modeStatus.textContent = "Freezing simulation time...";
  const response = await fetch("/api/time/freeze", { method: "POST" });
  if (!response.ok) {
    modeStatus.textContent = `Freeze failed: ${await response.text()}`;
    return;
  }
  modeStatus.textContent = "Simulation time frozen.";
  await refreshAll();
}

async function resumeTime() {
  modeStatus.textContent = "Returning to realtime...";
  const response = await fetch("/api/time/resume", { method: "POST" });
  if (!response.ok) {
    modeStatus.textContent = `Resume failed: ${await response.text()}`;
    return;
  }
  modeStatus.textContent = "Simulation time returned to realtime.";
  await refreshAll();
}

async function advanceTime(payload, label) {
  modeStatus.textContent = `Advancing time by ${label}...`;
  const response = await fetch("/api/time/advance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    modeStatus.textContent = `Time advance failed: ${await response.text()}`;
    return;
  }
  modeStatus.textContent = `Advanced time by ${label}.`;
  await refreshAll();
}

async function applyTimePreset(preset) {
  modeStatus.textContent = `Jumping to preset ${preset}...`;
  const response = await fetch("/api/time/preset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preset }),
  });
  if (!response.ok) {
    modeStatus.textContent = `Preset jump failed: ${await response.text()}`;
    return;
  }
  modeStatus.textContent = `Jumped to ${preset}.`;
  await refreshAll();
}

async function loadExperimentScenarios() {
  const response = await fetch("/api/experiments/scenarios");
  if (!response.ok) {
    experimentStatus.textContent = `Scenario load failed: ${await response.text()}`;
    return;
  }
  const payload = await response.json();
  populateScenarioSelect(payload.scenarios || []);
  if ((payload.scenarios || []).length) {
    experimentStatus.textContent = `Loaded ${payload.count} scenarios.`;
  } else {
    experimentStatus.textContent = "No experiment scenarios available.";
  }
}

async function refreshExperimentComparison() {
  const scenarioId = scenarioSelect.value;
  if (!scenarioId) {
    experimentStatus.textContent = "Select a scenario first.";
    return;
  }
  const response = await fetch(`/api/experiments/comparisons/${scenarioId}`);
  if (!response.ok) {
    experimentStatus.textContent = `Comparison refresh failed: ${await response.text()}`;
    return;
  }
  const comparison = await response.json();
  renderComparisonTable(comparison);
  renderExperimentCharts(comparison);
  const latestRun = selectLatestRunFromComparison(comparison);
  if (latestRun?.run_id) {
    await loadExperimentRunArtifacts(latestRun.run_id);
  }
  experimentStatus.textContent = `Comparison refreshed for ${scenarioId}.`;
}

async function loadExperimentRunArtifacts(runId) {
  const response = await fetch(`/api/experiments/runs/${runId}/artifacts`);
  if (!response.ok) {
    experimentStatus.textContent = `Run artifact load failed: ${await response.text()}`;
    return;
  }
  latestExperimentArtifacts = await response.json();
  latestExperimentEvents = {
    run_id: runId,
    count: (latestExperimentArtifacts.events || []).length,
    events: latestExperimentArtifacts.events || [],
  };
  renderLatestRunSummary(latestExperimentArtifacts.metadata, { summary: latestExperimentArtifacts.summary }, latestExperimentArtifacts);
  renderExperimentRunCharts(latestExperimentArtifacts, latestExperimentEvents);
}

async function runExperiment() {
  const scenarioId = scenarioSelect.value;
  const mode = experimentModeSelect.value;
  if (!scenarioId) {
    experimentStatus.textContent = "Select a scenario first.";
    return;
  }
  experimentStatus.textContent = `Running ${scenarioId} in ${mode}...`;
  runExperimentButton.disabled = true;
  try {
    const response = await fetch("/api/experiments/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_id: scenarioId, mode }),
    });
    if (!response.ok) {
      experimentStatus.textContent = `Experiment run failed: ${await response.text()}`;
      return;
    }
    const payload = await response.json();
    latestExperimentEvents = payload.events;
    latestExperimentArtifacts = payload.artifacts;
    renderLatestRunSummary(payload.run, payload.execution, latestExperimentArtifacts);
    renderComparisonTable(payload.comparison);
    renderExperimentCharts(payload.comparison);
    renderExperimentRunCharts(latestExperimentArtifacts, latestExperimentEvents);
    experimentStatus.textContent = `Completed ${scenarioId} in ${mode}.`;
  } finally {
    runExperimentButton.disabled = false;
  }
}

async function runExperimentBatch() {
  const scenarioId = scenarioSelect.value;
  const repeatCount = Number(experimentRepeatCountSelect.value || 2);
  if (!scenarioId) {
    experimentStatus.textContent = "Select a scenario first.";
    return;
  }
  experimentStatus.textContent = `Running repeated batch for ${scenarioId}...`;
  runBatchExperimentButton.disabled = true;
  try {
    const response = await fetch("/api/experiments/batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: scenarioId,
        modes: ["round_robin", "least_connections", "predictive_rules"],
        repeat_count: repeatCount,
      }),
    });
    if (!response.ok) {
      experimentStatus.textContent = `Batch run failed: ${await response.text()}`;
      return;
    }
    latestExperimentBatch = await response.json();
    renderBatchAggregateSummary(latestExperimentBatch);
    await refreshExperimentComparison();
    experimentStatus.textContent = `Completed repeated batch for ${scenarioId}.`;
  } finally {
    runBatchExperimentButton.disabled = false;
  }
}

function nextWeekdayPeakTimestamp() {
  const now = new Date();
  const target = new Date(now);
  target.setUTCDate(target.getUTCDate() + 1);
  while (target.getUTCDay() === 0 || target.getUTCDay() === 6) {
    target.setUTCDate(target.getUTCDate() + 1);
  }
  target.setUTCHours(18, 0, 0, 0);
  return target.toISOString();
}

function nextSaleDayEveningTimestamp() {
  const target = new Date();
  target.setUTCDate(target.getUTCDate() + 7);
  target.setUTCHours(20, 0, 0, 0);
  return target.toISOString();
}

async function previewRecommendationWindow(payload, title) {
  modeStatus.textContent = `Previewing ${title}...`;
  const response = await fetch("/api/recommendations/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    modeStatus.textContent = `Preview failed: ${await response.text()}`;
    return;
  }
  const previewPayload = await response.json();
  renderRecommendationCard(previewRecommendation, title, previewPayload);
  modeStatus.textContent = `Preview updated for ${title}.`;
}

function renderWorkers(workers) {
  workersGrid.innerHTML = workers
    .map(
      (worker) => `
        <article class="worker-card">
          <h3>${worker.worker_id}</h3>
          <p>${statusPill(worker.healthy ? "ok" : "degraded")}</p>
          <div class="worker-metrics">
            <div class="metric">
              <span>Load Score</span>
              <strong>${formatNumber(worker.load_score)}</strong>
            </div>
            <div class="metric">
              <span>Predicted Pressure</span>
              <strong>${formatNumber(worker.predicted_pressure)}</strong>
            </div>
            <div class="metric">
              <span>Inflight</span>
              <strong>${formatNumber(worker.inflight_requests)}</strong>
            </div>
            <div class="metric">
              <span>Queue Depth</span>
              <strong>${formatNumber(worker.queue_depth)}</strong>
            </div>
            <div class="metric">
              <span>Delay Fault</span>
              <strong>${formatNumber(worker.artificial_delay_ms)} ms</strong>
            </div>
            <div class="metric">
              <span>Policy Weight</span>
              <strong>${formatNumber(worker.policy_weight)}</strong>
            </div>
          </div>
          <p><strong>Policy Reason</strong>: ${worker.policy_reason || "-"}</p>
          <div class="worker-actions">
            <button class="worker-action accent" data-action="fault" data-worker="${worker.worker_id}">Inject 800 ms Fault</button>
            <button class="worker-action" data-action="clear" data-worker="${worker.worker_id}">Clear Faults</button>
          </div>
        </article>
      `
    )
    .join("");

  document.querySelectorAll(".worker-action").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.dataset.action === "fault") {
        await injectLatency(button.dataset.worker);
      } else {
        await clearFaults(button.dataset.worker);
      }
    });
  });
}

function formatTimeLabel(timestamp) {
  if (!timestamp) {
    return "";
  }
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour12: false, minute: "2-digit", second: "2-digit" });
}

function workerColor(workerId, index) {
  const hash = Array.from(workerId || "").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return palette[(hash + index) % palette.length];
}

function buildWorkerSeries(historyPoints, selector) {
  const workerIds = Array.from(
    new Set(historyPoints.flatMap((point) => (point.workers || []).map((worker) => worker.worker_id)).filter(Boolean))
  );
  return workerIds.map((workerId, index) => ({
    label: workerId,
    color: workerColor(workerId, index),
    values: historyPoints.map((point) => {
      const worker = (point.workers || []).find((entry) => entry.worker_id === workerId);
      return worker ? selector(worker) : 0;
    }),
  }));
}

function renderEmptyChart(target) {
  target.innerHTML = '<div class="chart-empty">Waiting for enough live samples.</div>';
}

function linePath(values, width, height, leftPad, topPad, bottomPad, maxValue) {
  const chartWidth = width - leftPad - 10;
  const chartHeight = height - topPad - bottomPad;
  return values
    .map((value, index) => {
      const x = leftPad + (chartWidth * (values.length === 1 ? 0 : index / (values.length - 1)));
      const y = topPad + chartHeight - ((value / maxValue) * chartHeight);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function bandPath(lowerValues, upperValues, width, height, leftPad, topPad, bottomPad, maxValue) {
  const chartWidth = width - leftPad - 10;
  const chartHeight = height - topPad - bottomPad;
  const upperPoints = upperValues.map((value, index) => {
    const x = leftPad + (chartWidth * (upperValues.length === 1 ? 0 : index / (upperValues.length - 1)));
    const y = topPad + chartHeight - ((value / maxValue) * chartHeight);
    return `${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  const lowerPoints = lowerValues
    .map((value, index) => {
      const x = leftPad + (chartWidth * (lowerValues.length === 1 ? 0 : index / (lowerValues.length - 1)));
      const y = topPad + chartHeight - ((value / maxValue) * chartHeight);
      return `${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .reverse();
  return `M ${upperPoints.join(" L ")} L ${lowerPoints.join(" L ")} Z`;
}

function renderLineChart(target, chartTitle, labels, series, markers = []) {
  if (!labels.length || !series.length || labels.length < 2) {
    renderEmptyChart(target);
    return;
  }

  const width = 560;
  const height = 200;
  const leftPad = 44;
  const topPad = 14;
  const bottomPad = 28;
  const allValues = series.flatMap((entry) => entry.values);
  const maxValue = Math.max(...allValues, 1);
  const yTicks = 4;

  const gridLines = [];
  for (let tick = 0; tick <= yTicks; tick += 1) {
    const ratio = tick / yTicks;
    const y = topPad + ((height - topPad - bottomPad) * ratio);
    const value = (maxValue * (1 - ratio)).toFixed(maxValue < 10 ? 2 : 1);
    gridLines.push(`<line class="chart-grid-line" x1="${leftPad}" y1="${y}" x2="${width - 10}" y2="${y}" />`);
    gridLines.push(`<text class="chart-label" x="0" y="${y + 4}">${value}</text>`);
  }

  const paths = series
    .map((entry) => {
      const path = linePath(entry.values, width, height, leftPad, topPad, bottomPad, maxValue);
      const lastValue = entry.values[entry.values.length - 1];
      const lastX = leftPad + ((width - leftPad - 10) * ((entry.values.length - 1) / (entry.values.length - 1 || 1)));
      const lastY = topPad + (height - topPad - bottomPad) - ((lastValue / maxValue) * (height - topPad - bottomPad));
      return `
        <path class="chart-path" d="${path}" style="stroke:${entry.color}" />
        <circle class="chart-dot" cx="${lastX}" cy="${lastY}" r="3.5" fill="${entry.color}" />
        <text class="chart-value-label" x="${Math.min(lastX + 6, width - 36)}" y="${Math.max(lastY - 6, topPad + 10)}">${formatNumber(lastValue)}</text>
      `;
    })
    .join("");

  const labelStep = Math.max(Math.floor(labels.length / 5), 1);
  const xLabels = labels
    .map((label, index) => {
      if (index % labelStep !== 0 && index !== labels.length - 1) {
        return "";
      }
      const x = leftPad + ((width - leftPad - 10) * (labels.length === 1 ? 0 : index / (labels.length - 1)));
      return `<text class="chart-label" x="${x - 14}" y="${height - 6}">${label}</text>`;
    })
    .join("");

  const markerElements = markers
    .map((marker) => {
      const x = leftPad + ((width - leftPad - 10) * (labels.length === 1 ? 0 : marker.index / (labels.length - 1)));
      return `
        <line class="chart-marker-line" x1="${x}" y1="${topPad}" x2="${x}" y2="${height - bottomPad}" />
        <text class="chart-marker-label" x="${Math.min(x + 4, width - 80)}" y="${topPad + 12}">${marker.shortLabel}</text>
      `;
    })
    .join("");

  const legend = `
    <div class="chart-legend">
      ${series
        .map(
          (entry) => `
            <span class="chart-legend-item">
              <span class="chart-swatch" style="background:${entry.color}"></span>
              ${entry.label}
            </span>
          `
        )
        .join("")}
    </div>
  `;

  target.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${chartTitle}">
      ${gridLines.join("")}
      <line class="chart-axis-line" x1="${leftPad}" y1="${height - bottomPad}" x2="${width - 10}" y2="${height - bottomPad}" />
      ${markerElements}
      ${paths}
      ${xLabels}
    </svg>
    ${legend}
  `;
}

function renderBandChart(target, chartTitle, labels, lowerSeries, upperSeries, bandColor, markers = []) {
  if (!labels.length || labels.length < 2) {
    renderEmptyChart(target);
    return;
  }

  const width = 560;
  const height = 200;
  const leftPad = 44;
  const topPad = 14;
  const bottomPad = 28;
  const maxValue = Math.max(...lowerSeries.values, ...upperSeries.values, 1);
  const yTicks = 4;

  const gridLines = [];
  for (let tick = 0; tick <= yTicks; tick += 1) {
    const ratio = tick / yTicks;
    const y = topPad + ((height - topPad - bottomPad) * ratio);
    const value = (maxValue * (1 - ratio)).toFixed(maxValue < 10 ? 2 : 1);
    gridLines.push(`<line class="chart-grid-line" x1="${leftPad}" y1="${y}" x2="${width - 10}" y2="${y}" />`);
    gridLines.push(`<text class="chart-label" x="0" y="${y + 4}">${value}</text>`);
  }

  const band = bandPath(lowerSeries.values, upperSeries.values, width, height, leftPad, topPad, bottomPad, maxValue);
  const lowerPath = linePath(lowerSeries.values, width, height, leftPad, topPad, bottomPad, maxValue);
  const upperPath = linePath(upperSeries.values, width, height, leftPad, topPad, bottomPad, maxValue);

  const labelStep = Math.max(Math.floor(labels.length / 5), 1);
  const xLabels = labels
    .map((label, index) => {
      if (index % labelStep !== 0 && index !== labels.length - 1) {
        return "";
      }
      const x = leftPad + ((width - leftPad - 10) * (labels.length === 1 ? 0 : index / (labels.length - 1)));
      return `<text class="chart-label" x="${x - 14}" y="${height - 6}">${label}</text>`;
    })
    .join("");

  const markerElements = markers
    .map((marker) => {
      const x = leftPad + ((width - leftPad - 10) * (labels.length === 1 ? 0 : marker.index / (labels.length - 1)));
      return `
        <line class="chart-marker-line" x1="${x}" y1="${topPad}" x2="${x}" y2="${height - bottomPad}" />
        <text class="chart-marker-label" x="${Math.min(x + 4, width - 80)}" y="${topPad + 12}">${marker.shortLabel}</text>
      `;
    })
    .join("");

  target.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${chartTitle}">
      ${gridLines.join("")}
      <line class="chart-axis-line" x1="${leftPad}" y1="${height - bottomPad}" x2="${width - 10}" y2="${height - bottomPad}" />
      ${markerElements}
      <path class="chart-band" d="${band}" fill="${bandColor}" />
      <path class="chart-path" d="${lowerPath}" style="stroke:${lowerSeries.color}" />
      <path class="chart-path" d="${upperPath}" style="stroke:${upperSeries.color}" />
      ${xLabels}
    </svg>
    <div class="chart-legend">
      <span class="chart-legend-item">
        <span class="chart-swatch" style="background:${lowerSeries.color}"></span>
        ${lowerSeries.label}
      </span>
      <span class="chart-legend-item">
        <span class="chart-swatch" style="background:${upperSeries.color}"></span>
        ${upperSeries.label}
      </span>
    </div>
  `;
}

function renderCharts(historyPayload) {
  const historyPoints = historyPayload.points || [];
  const labels = historyPoints.map((point) => formatTimeLabel(point.dashboard_recorded_at || point.generated_at));
  const markers = historyPoints
    .map((point, index) => {
      const event = point.time_event;
      if (!event) {
        return null;
      }
      const actionLabelMap = {
        freeze: "Freeze",
        resume: "Resume",
        advance: "Jump",
        preset: "Preset",
      };
      return {
        index,
        shortLabel: actionLabelMap[event.action] || event.action,
      };
    })
    .filter(Boolean);

  renderLineChart(chartTargets.trafficChart, "Traffic Pressure", labels, [
    {
      label: "Total Inflight",
      color: "#2059a8",
      values: historyPoints.map((point) => point.summary?.total_worker_inflight ?? 0),
    },
    {
      label: "Max Queue Depth",
      color: "#9b6a12",
      values: historyPoints.map((point) =>
        Math.max(0, ...(point.workers || []).map((worker) => worker.queue_depth ?? 0))
      ),
    },
  ], markers);

  renderLineChart(chartTargets.predictionChart, "Prediction Signals", labels, [
    {
      label: "Max Load Score",
      color: "#c6552d",
      values: historyPoints.map((point) => point.summary?.max_worker_load_score ?? 0),
    },
    {
      label: "Max Predicted Pressure",
      color: "#1d6b45",
      values: historyPoints.map((point) => point.summary?.max_predicted_pressure ?? 0),
    },
  ], markers);

  renderLineChart(
    chartTargets.loadChart,
    "Worker Load Scores",
    labels,
    buildWorkerSeries(historyPoints, (worker) => worker.load_score ?? 0),
    markers
  );

  renderLineChart(
    chartTargets.weightChart,
    "Policy Weights",
    labels,
    buildWorkerSeries(historyPoints, (worker) => worker.policy_weight ?? 0),
    markers
  );

  renderLineChart(
    chartTargets.faultChart,
    "Fault Delay",
    labels,
    buildWorkerSeries(historyPoints, (worker) => worker.artificial_delay_ms ?? 0),
    markers
  );

  renderLineChart(
    chartTargets.queueChart,
    "Queue Depth",
    labels,
    buildWorkerSeries(historyPoints, (worker) => worker.queue_depth ?? 0),
    markers
  );

  renderBandChart(
    chartTargets.strategicBandChart,
    "Strategic Forecast Band",
    labels,
    {
      label: "Avg Expected RPS",
      color: "#127f96",
      values: historyPoints.map((point) => point.summary?.strategic_avg_expected_rps ?? 0),
    },
    {
      label: "Peak Expected RPS",
      color: "#c6552d",
      values: historyPoints.map((point) => point.summary?.strategic_peak_expected_rps ?? 0),
    },
    "rgba(18, 127, 150, 0.18)",
    markers
  );

  renderLineChart(chartTargets.capacityChart, "Recommended Capacity", labels, [
    {
      label: "Target Workers",
      color: "#93348f",
      values: historyPoints.map((point) => point.summary?.strategic_target_workers ?? 0),
    },
  ], markers);
}

async function refreshAll() {
  const [overviewResponse, historyResponse, recommendationResponse] = await Promise.all([
    fetch("/api/overview"),
    fetch("/api/history"),
    fetch("/api/recommendations"),
  ]);

  if (!overviewResponse.ok) {
    modeStatus.textContent = `Overview refresh failed: ${await overviewResponse.text()}`;
    return;
  }
  if (!historyResponse.ok) {
    modeStatus.textContent = `History refresh failed: ${await historyResponse.text()}`;
    return;
  }
  if (!recommendationResponse.ok) {
    modeStatus.textContent = `Recommendation refresh failed: ${await recommendationResponse.text()}`;
    return;
  }

  const overview = await overviewResponse.json();
  const historyPayload = await historyResponse.json();
  const recommendationPayload = await recommendationResponse.json();
  const timeState = overview.control_plane.time || {};

  const mode = overview.control_plane.mode || "-";
  modeValue.textContent = mode;
  policyVersionValue.textContent = overview.control_plane.policy_version ?? "-";
  healthyWorkersValue.textContent = overview.summary.healthy_workers ?? "-";
  timeModeValue.textContent = timeState.mode || "-";
  effectiveTimeValue.textContent = formatTimestamp(overview.control_plane.effective_time_utc);
  simulatedTimeValue.textContent = formatTimestamp(timeState.simulated_time_utc);
  setModeButtons(mode);
  renderServices(overview.services);
  renderSummary(overview.summary);
  renderWorkers(overview.workers);
  renderTimeEvents(historyPayload.points || []);
  renderCharts(historyPayload);
  renderRecommendationCard(strategicRecommendation, "Current Strategic Window", recommendationPayload);
  modeStatus.textContent = `Last refresh: ${overview.generated_at || "unknown"}`;
}

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

freezeTimeButton.addEventListener("click", freezeTime);
resumeTimeButton.addEventListener("click", resumeTime);
document.querySelectorAll("[data-advance-hours], [data-advance-days]").forEach((button) => {
  button.addEventListener("click", () => {
    const hours = Number(button.dataset.advanceHours || 0);
    const days = Number(button.dataset.advanceDays || 0);
    const label = days ? `${days} day${days === 1 ? "" : "s"}` : `${hours} hour${hours === 1 ? "" : "s"}`;
    advanceTime({ days, hours, minutes: 0 }, label);
  });
});
document.querySelectorAll("[data-preset]").forEach((button) => {
  button.addEventListener("click", () => applyTimePreset(button.dataset.preset));
});
refreshButton.addEventListener("click", refreshAll);
runExperimentButton.addEventListener("click", runExperiment);
runBatchExperimentButton.addEventListener("click", runExperimentBatch);
refreshComparisonButton.addEventListener("click", refreshExperimentComparison);
previewSaleButton.addEventListener("click", () =>
  previewRecommendationWindow(
    {
      target_start_utc: nextSaleDayEveningTimestamp(),
      interval_count: 4,
      is_sale_day: true,
      event_type: "sale_day",
    },
    "Sale-Day Evening Preview"
  )
);
previewWeekdayButton.addEventListener("click", () =>
  previewRecommendationWindow(
    {
      target_start_utc: nextWeekdayPeakTimestamp(),
      interval_count: 4,
      is_sale_day: false,
      event_type: "none",
    },
    "Weekday Peak Preview"
  )
);

loadExperimentScenarios();
refreshAll();
renderExperimentRunCharts(null, null);
renderBatchAggregateSummary(null);
setInterval(refreshAll, 5000);
