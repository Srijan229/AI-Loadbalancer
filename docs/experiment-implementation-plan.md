# Experiment Comparison Implementation Plan

This document maps the comparison framework into exact repo changes.

## New/Updated Files

### New Service

Add:

```text
services/experiment-runner/
  README.md
  requirements.txt
  Dockerfile
  app/
    __init__.py
    main.py
```

Purpose:
- coordinate scenario runs
- set orchestration mode
- set time presets
- trigger failures
- launch Locust
- persist run artifacts

### New Data Directories

Add:

```text
data/experiments/
  scenarios/
  runs/
  comparisons/
```

### New Docs Already Defined

- `docs/experiment-comparison-architecture.md`
- `docs/experiment-schema.md`
- `docs/dashboard-comparison-section.md`

## API Additions

### Experiment Runner

Implement:

#### `GET /health`

Basic liveness.

#### `GET /scenarios`

Return available scenario definitions from:
- `data/experiments/scenarios`

#### `POST /runs`

Start a run.

Request:

```json
{
  "scenario_id": "sale_day_surge_with_fault",
  "mode": "predictive_rules"
}
```

Response:

```json
{
  "run_id": "run_2026_05_03_001",
  "status": "started"
}
```

#### `GET /runs/{run_id}`

Return run metadata + current status.

#### `GET /runs/{run_id}/summary`

Return persisted `summary.json`.

#### `GET /runs/{run_id}/timeseries`

Return time-series points.

#### `GET /comparisons/{scenario_id}`

Return latest comparison summary across modes for a scenario.

## Scenario Files

Store JSON scenario definitions in:

```text
data/experiments/scenarios/
```

Initial files to add:

- `steady_low.json`
- `burst_traffic.json`
- `worker_slowdown.json`
- `sale_day_surge.json`
- `sale_day_surge_with_fault.json`

## Existing Service Integration

### Orchestrator

Already supports:
- mode changes
- strategic forecasting
- effective time awareness

Needs:
- accept `predictive_rules` as the explicit non-agentic predictive label
- later: support `agentic`

### Dashboard

Currently supports:
- live overview
- strategic forecast
- time controls
- worker fault controls

Needs:
- `Experiment Lab` section
- comparison tables
- run summaries
- multi-run time-series overlays

### Locust Harness

Current:
- `scripts/load/locustfile.py`

Needs:
- programmatic invocation by `experiment-runner`
- scenario parameter handoff
- output capture into per-run folders

## Persistence Model

Per run:

```text
data/experiments/runs/<run_id>/
  metadata.json
  summary.json
  timeseries.jsonl
  worker_timeseries.jsonl
  events.jsonl
  agent_decisions.jsonl
```

## Milestone Order

### Milestone 1: Scenario Artifacts

Build:
- scenario JSON files
- shared run-id naming convention
- output directory structure

Verification:
- scenario list endpoint returns valid scenario definitions

### Milestone 2: Experiment Runner Skeleton

Build:
- FastAPI service
- `GET /scenarios`
- `POST /runs`
- metadata persistence

Verification:
- starting a run creates the folder and `metadata.json`

### Milestone 3: Load + Fault Orchestration

Build:
- invoke Locust programmatically
- apply time preset
- inject scheduled failures
- collect run events

Verification:
- a scenario produces `metadata.json` and `events.jsonl`

### Milestone 4: Metrics Capture

Build:
- sample dashboard/orchestrator/collector state during runs
- persist `timeseries.jsonl`
- persist `worker_timeseries.jsonl`

Verification:
- run folder contains meaningful time-series files

### Milestone 5: Summary + Comparison

Build:
- summary calculation
- scenario-level comparison output
- `GET /comparisons/{scenario_id}`

Verification:
- two or more runs of the same scenario produce a comparison summary

### Milestone 6: Dashboard Experiment Lab

Build:
- scenario selector
- mode selector
- run button
- comparison table
- overlay charts

Verification:
- dashboard can launch and display run comparisons

### Milestone 7: Agentic Extension

Build:
- candidate action schema
- action logs
- decision timeline
- reward/evaluation traces

Verification:
- `agentic` runs produce decision artifacts distinct from baseline runs

## Recommended Immediate Next Build

The next implementation step should be:

1. create `data/experiments/scenarios/*.json`
2. scaffold `services/experiment-runner`
3. implement `GET /scenarios`
4. implement `POST /runs` with metadata persistence only

That is the smallest useful first slice.
