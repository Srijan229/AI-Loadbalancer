# Predictive Validation Results

Date:
- `2026-05-05`

Validation focus:
- prove whether the predictive part of the product is meaningful
- verify that short-horizon and strategic forecasting produce useful signals
- verify whether `predictive_rules` can beat a simpler baseline in a meaningful scenario

Reference checklist:
- [product-validation-checklist.md](/d:/ai-autoscaller/docs/product-validation-checklist.md)

## Environment

- cluster: `minikube`
- validation surface: dashboard API via `http://127.0.0.1:8710`
- experiment execution path:
  - dashboard
  - experiment-runner
  - orchestrator
  - time-controller
  - gateway
  - workers

## Validation Summary

### C1. Short-Horizon Predictor Is Meaningful

Verdict:
- `PASS`

Scenario:
- `smoke_fault`
- mode: `predictive_rules`

Observed result:
- run id: `run_2026_05_05_134727_a770fb`
- status: `completed`
- requests total: `671`
- requests failed: `0`
- max predicted pressure: `44.21`
- max queue depth: `4`

Interpretation:
- the predictor did not stay flat during the fault run
- pressure rose materially above idle-state behavior during the injected slowdown
- this is enough to say the short-horizon signal path is alive and responsive

### C2. Strategic Forecast Is Meaningful

Verdict:
- `PASS`

Compared windows:
- normal/realtime
- `weekday_peak`
- `sale_day_evening`

Observed result:

| Window | Avg Expected RPS | Peak Expected RPS | Target Workers |
|---|---:|---:|---:|
| normal | 46.242 | 46.267 | 2 |
| weekday_peak | 37.149 | 38.175 | 2 |
| sale_day_evening | 84.176 | 86.569 | 3 |

Interpretation:
- `sale_day_evening` is clearly distinct from the normal window
- target worker recommendation rises from `2` to `3`
- strategic forecasting is not cosmetic; it changes the orchestration posture

Note:
- `weekday_peak` did not exceed the normal snapshot in this validation moment, but `sale_day_evening` still provides a valid strategic-surge distinction

### C3. Predictive Rules Change Decisions In A Meaningful Way

Verdict:
- `INCONCLUSIVE`

Why:
- the outcome differences strongly suggest predictive mode matters in the surge-plus-fault scenario
- however, this validation pass did not yet extract a clean decision-trace proving earlier or more protective control actions than the simpler baselines

What we still need:
- explicit policy-weight or action-delta evidence across modes for the same stress window
- this should come from stored run-detail artifacts and control-plane state over time

### C4. Predictive Rules Improve Outcomes Over A Baseline

Verdict:
- `PASS`, but only for the flagship surge scenario

#### Scenario A: `worker_slowdown`

Verdict:
- `MIXED / INCONCLUSIVE`

Observed result:

| Mode | Status | Failed | Throughput RPS | P95 ms | P99 ms | Max Queue | Max Predicted Pressure |
|---|---|---:|---:|---:|---:|---:|---:|
| round_robin | completed | 0 | 56.56 | 900 | 920 | 18 | 133.58 |
| least_connections | failed | 1 | 79.21 | 860 | 930 | 9 | 93.82 |
| predictive_rules | failed | 1 | 63.54 | 900 | 1200 | 15 | 96.50 |

Interpretation:
- `predictive_rules` was slightly better than `round_robin` on throughput and queue depth
- but it did not beat `least_connections`
- it also did not produce a clean tail-latency improvement over `round_robin`
- this is not strong enough to claim a clear predictive win in this scenario

#### Scenario B: `sale_day_surge_with_fault`

Verdict:
- `PASS`

Observed result:

| Mode | Status | Failed | Throughput RPS | P50 ms | P95 ms | P99 ms | Max Queue | Max Predicted Pressure |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| round_robin | completed | 0 | 63.11 | 190 | 1400 | 2200 | 42 | 264.14 |
| predictive_rules | completed | 0 | 77.08 | 110 | 1300 | 1900 | 18 | 305.27 |

Interpretation:
- this is the strongest result in the validation set
- `predictive_rules` beat `round_robin` on:
  - throughput
  - p50 latency
  - p95 latency
  - p99 latency
  - queue depth
- the queue-depth improvement is especially important:
  - `42 -> 18`
- this is a meaningful win under the kind of surge-plus-fault scenario the product is designed for

### C5. The System Can Explain Why Predictive Mode Helped Or Failed

Verdict:
- `PASS`, at a first useful level

Why:
- the system produced:
  - run ids
  - mode-specific summaries
  - stored time-series
  - worker time-series
  - event logs
  - dashboard comparison outputs

What we can explain now:
- strategic forecast increased capacity posture during sale-day surge
- predictive mode performed much better than round robin when stress was both elevated and asymmetric
- the mixed `worker_slowdown` result shows predictive mode is not automatically better in every simpler case

What is still weak:
- we do not yet have a polished narrative view of exact route-weight/control changes across modes during the run

## Current Product Verdict

The predictive product claim is now partially proven.

What is proven:
- short-horizon predictive signal is meaningful
- strategic forecasting is meaningful
- predictive mode can clearly outperform round robin in the flagship surge-plus-fault scenario

What is not yet fully proven:
- predictive mode is not yet clearly superior in every degradation scenario
- predictive decision traces are not yet surfaced strongly enough for a crisp control-behavior explanation
- agentic mode is not implemented, so no agentic performance claim is proven yet

## Decision

Current decision:
- the predictive part of the product is strong enough to continue
- but the next technical focus should be on:
  - stronger decision-trace visibility
  - repeated comparison runs across modes
  - eventually agentic-mode implementation inside the same comparison framework

## Recommended Next Step

Before AWS integration, strengthen one of these:

1. surface control decisions and policy-weight shifts more explicitly in experiment artifacts and dashboard charts
2. run repeated multi-mode comparisons for the flagship scenario so the predictive win is not based on only one run
