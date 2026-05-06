# Dashboard Comparison Section

This document defines the new dashboard section for baseline vs predictive vs agentic comparisons.

## Section Name

Use:
- `Experiment Lab`

This should be a new top-level dashboard area, separate from the current live-control panel.

## Panels

### 1. Run Controls

Purpose:
- choose the scenario and mode
- launch a reproducible run

Controls:
- orchestration mode selector
  - `round_robin`
  - `least_connections`
  - `predictive_rules`
  - `agentic`
- scenario selector
- time preset selector
- `Run Scenario`
- `Stop Run`

## 2. Run Summary

Show:
- run id
- status
- mode
- scenario
- effective time
- elapsed duration
- active fault plan

## 3. Comparison Table

Rows:
- one row per mode for the selected scenario

Columns:
- mode
- p50 latency
- p95 latency
- p99 latency
- throughput
- error rate
- max queue depth
- recovery time
- score

## 4. Comparison Charts

Overlay all selected runs on the same charts.

Required graphs:

- `p95 Latency Over Time`
- `Throughput Over Time`
- `Error Rate Over Time`
- `Queue Depth Over Time`
- `Predicted Pressure Over Time`
- `Recommended Capacity Over Time`

Recommended graphs:

- `Worker Load Distribution`
- `Policy Weight Shifts`
- `Recovery Timeline After Fault`

## 5. Agent Decision Timeline

Only shown for `agentic` runs.

Each decision record should show:
- timestamp
- chosen action
- top alternative actions
- action score
- explanation
- later: realized reward

## 6. Delta Cards

Show improvements versus a selected baseline.

Examples:

- `% p95 improvement vs round_robin`
- `% recovery improvement vs least_connections`
- `% error-rate reduction vs predictive_rules`

## 7. Time Context Visibility

Comparison runs must show their time context clearly:

- realtime or frozen
- effective timestamp
- preset used
- event label if relevant

This is important because historical-forecast-driven scenarios are only meaningful if the time context is visible.

## Implementation Sequence

Build the section in this order:

1. add run summary card
2. add comparison table from persisted summaries
3. add time-series overlay charts
4. add agent decision timeline
5. add delta cards

Do not start with visual polish.
Start with correct, queryable run artifacts.
