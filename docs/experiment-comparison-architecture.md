# Experiment Comparison Architecture

This document defines the comparison framework for evaluating non-agentic and agentic orchestration strategies in this repo.

The goal is not only to "have an agent", but to prove whether it performs better than simpler orchestration approaches under identical load and failure scenarios.

## Comparison Modes

We will support these orchestration modes:

- `round_robin`
- `least_connections`
- `predictive_rules`
- `agentic`

### Meaning of Each Mode

`round_robin`
- traditional baseline
- no telemetry-driven adaptation

`least_connections`
- simple reactive baseline
- chooses the least busy worker from current in-flight counts

`predictive_rules`
- uses predictor + historical forecaster
- still rule-based
- no multi-action planning, no memory, no post-action evaluation

`agentic`
- explicit objective function
- candidate action generation
- action scoring
- action memory
- post-action evaluation

## Current Repo Mapping

These services already exist and remain core to the comparison framework:

- `gateway`
- `worker`
- `metrics-collector`
- `predictor`
- `historical-forecaster`
- `orchestrator`
- `dashboard`
- `time-controller`

These services/components should be added next for comparison support:

- `experiment-runner`
- `evaluation-engine`
- `policy-memory` (service or Redis-backed module)

## Control Plane Layout

### Shared Control Plane

- `metrics-collector`
  - gathers live state
- `predictor`
  - computes short-horizon pressure signals
- `historical-forecaster`
  - computes long-horizon demand expectations
- `time-controller`
  - controls simulation time
- `orchestrator`
  - applies the active strategy

### Comparison Layer

- `experiment-runner`
  - executes scenarios consistently across modes
- `evaluation-engine`
  - computes metrics and comparison summaries
- `policy-memory`
  - stores state/action/outcome records for `agentic`

## Execution Flow

For every experiment run:

1. select `scenario`
2. select `mode`
3. reset time/fault state
4. set time preset if required
5. set orchestrator mode
6. launch load profile
7. inject failures on schedule
8. collect live metrics during the run
9. persist run artifacts
10. compute summary metrics
11. compare against prior runs for the same scenario

## Scenario Catalog

The comparison layer should treat scenarios as reusable artifacts, not hardcoded test flows.

Recommended initial scenarios:

- `steady_low`
- `steady_high`
- `ramp_up`
- `burst_traffic`
- `spike_and_drop`
- `worker_slowdown`
- `worker_termination`
- `sale_day_surge`
- `sale_day_surge_with_fault`

## Data Sources Used During Comparison

### Data Plane Signals

- request latency
- request throughput
- error rate
- in-flight request count
- queue depth

### Short-Horizon Predictive Signals

- predicted pressure
- current load score
- pressure trend

### Long-Horizon Strategic Signals

- avg expected RPS
- peak expected RPS
- recommended workers
- demand level
- event label / sale-day label

## Success Criteria

The framework should make it possible to answer:

- Does `predictive_rules` outperform traditional baselines?
- Does `agentic` outperform `predictive_rules`?
- Under which scenarios does `agentic` help most?
- When does the extra decision complexity not help enough to justify itself?

Strong success cases for `agentic`:

- lower `p95` and `p99` latency under burst/fault conditions
- faster recovery after slowdown/termination
- lower peak queue depth
- fewer overload events
- better pre-scaling recommendations in surge windows
- less routing instability than naive reactive policies

## Recommended Storage Layout

```text
data/
  experiments/
    scenarios/
      steady_low.json
      burst_traffic.json
      sale_day_surge_with_fault.json
    runs/
      run_2026_05_03_001/
        metadata.json
        summary.json
        timeseries.jsonl
        worker_timeseries.jsonl
        events.jsonl
        agent_decisions.jsonl
    comparisons/
      sale_day_surge_with_fault_latest.json
```

Use:

- `json` for metadata and summaries
- `jsonl` for time-series/event streams

This is simple, diffable, and easy to visualize later.
