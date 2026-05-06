# Repeatability Findings

Date:
- `2026-05-06`

Purpose:
- continue the flagship comparison work
- test whether the predictive claim stays strong when additional runs are executed
- check whether the earlier predictive win is repeatable

## Context

The previous validation run showed a strong predictive win for `sale_day_surge_with_fault`.

This follow-up looked for repeatability rather than a one-off best case.

## Recovered Flagship Comparison State

During a repeated batch attempt, two modes had already completed before the turn was interrupted:

### `round_robin`
- run id: `run_2026_05_06_192628_f42e12`
- throughput: `66.15 rps`
- p50: `140 ms`
- p95: `1500 ms`
- p99: `2000 ms`
- max queue depth: `55`

### `least_connections`
- run id: `run_2026_05_06_192932_2e5f6e`
- throughput: `76.20 rps`
- p50: `110 ms`
- p95: `1400 ms`
- p99: `1800 ms`
- max queue depth: `29`

## Completed Predictive Continuation Run

To complete the missing third mode, `predictive_rules` was run manually for the same flagship scenario:

### `predictive_rules`
- run id: `run_2026_05_06_193341_d78864`
- throughput: `29.24 rps`
- p50: `1000 ms`
- p95: `2900 ms`
- p99: `5300 ms`
- max queue depth: `46`
- max predicted pressure: `386.43`
- policy shift count: `94`
- target worker shift count: `2`
- scale action shift count: `2`

## Main Finding

This run did **not** confirm the earlier predictive win.

Instead, it showed:

- much worse throughput than both baselines
- much worse tail latency than both baselines
- heavy policy activity
- unstable control behavior relative to the simpler modes

## Interpretation

The predictive layer is currently **not stable enough to claim robust repeatable superiority**.

The most likely explanation is not that predictive orchestration is fundamentally bad, but that the current implementation is too volatile under this scenario.

Possible contributing factors:

- routing weights shifting too aggressively
- insufficient damping or hysteresis
- predictor pressure spikes feeding unstable control updates
- policy updates that overreact during surge-plus-fault windows
- mismatch between predicted pressure and practical traffic steering

## What This Means For The Product Claim

Current status:

- the project has proven that predictive mode **can** outperform a simpler baseline in at least one flagship run
- the project has **not** yet proven that this result is repeatable enough to claim stable product performance

So the honest product state is:

- predictive behavior is real
- predictive signals are real
- strategic forecasting is real
- but predictive control is still **tuning-sensitive and not yet reliably superior**

## Validation Impact

### C1. Short-Horizon Predictor Is Meaningful
- remains `PASS`

### C2. Strategic Forecast Is Meaningful
- remains `PASS`

### C4. Predictive Rules Improve Outcomes Over A Baseline
- should now be downgraded from a confident `PASS` to:
  - `MIXED / NOT YET REPEATABLE`

Why:
- earlier flagship result was strong
- this follow-up flagship run contradicted it
- repeated evidence now shows inconsistency

## Most Important Engineering Conclusion

Do not extend to AWS or agentic mode yet if the goal is a strong product claim.

The highest-value next work is:

1. reduce control instability
2. add damping / hysteresis to predictive policy shifts
3. reduce overreaction in surge windows
4. rerun repeated flagship comparisons until predictive behavior is either:
   - consistently better
   - or honestly shown to be not yet ready

## What To Say If Someone Asks

Honest answer:

The system clearly has predictive and strategic signal flow, but repeated flagship validation showed that the current predictive controller is unstable in some hard scenarios. That means the architecture is promising, but the control policy still needs tuning before I can claim robust repeatable performance improvement over simpler baselines.
