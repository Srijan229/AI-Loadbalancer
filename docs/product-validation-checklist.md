# Predictive And Agentic Validation Checklist

This document focuses validation on the real claim of the project:

Can predictive and later agentic orchestration outperform simpler routing strategies under bursty load, degraded workers, and forecasted surge windows?

It does not treat generic service bring-up as the main success criterion. Gateway health, worker health, and dashboard rendering are prerequisites, not the product claim.

## Product Claim

The product is:

An adaptive orchestration platform that uses:

- live telemetry
- short-horizon pressure prediction
- long-horizon strategic demand forecasting
- experiment-driven comparison

to make better traffic and capacity decisions than simpler policies.

The strongest version of the claim is:

`predictive_rules` should beat at least one baseline in a meaningful scenario, and `agentic` should later beat `predictive_rules` often enough to justify its extra decision complexity.

## Validation Focus

The validation should answer these questions:

1. Does the predictor detect rising pressure early enough to matter?
2. Does the strategic forecaster change recommendations meaningfully across demand windows?
3. Does `predictive_rules` improve system behavior compared to `round_robin` or `least_connections`?
4. When `agentic` is added, does it improve over `predictive_rules`, not just behave differently?
5. Can we explain why a smarter mode won or lost?

## What Counts As A Prerequisite

These are necessary, but they are not the main success criteria:

- gateway forwards requests correctly
- workers expose health and metrics
- experiment runner executes scenarios
- dashboard reflects stored and live data

If these fail, the experiment is invalid. If they pass, validation still is not complete until predictive behavior is proven.

## Core Evaluation Ladder

Think of validation in four levels:

### Level 0. System Integrity

Question:
- Can the stack run consistently enough to trust experiments?

Needed:
- scenarios execute
- faults inject correctly
- artifacts are stored
- dashboard matches artifacts

### Level 1. Signal Validity

Question:
- Are predictive signals responding to actual system stress?

Needed:
- predicted pressure rises during degradation
- predicted pressure falls during recovery
- strategic forecast changes across time presets

### Level 2. Decision Validity

Question:
- Do predictive decisions change control behavior in a sensible way?

Needed:
- predictive mode changes routing behavior under pressure
- strategic forecast changes target workers / recommendations
- the system can explain those changes

### Level 3. Outcome Validity

Question:
- Do smarter strategies improve measurable results?

Needed:
- better `p95`, queue depth, recovery, or overload avoidance than a simpler baseline

This is the most important level.

## Main Validation Claims

### C1. Short-Horizon Predictor Is Meaningful

Claim:
- the predictor does not just mirror idle state; it identifies rising stress during burst or fault conditions

Why it matters:
- if this fails, `predictive_rules` is mostly theater

Test scenarios:
- `smoke_fault`
- `worker_slowdown`
- `burst_traffic`

Expected evidence:
- affected worker shows higher `predicted_pressure` than unaffected worker
- `max_predicted_pressure` rises materially above idle baseline during slowdown/burst
- pressure falls after recovery

Pass criteria:
- predictive signal increases during stress and is not flat/noisy nonsense

### C2. Strategic Forecast Is Meaningful

Claim:
- historical forecasting distinguishes ordinary and surge windows in a way that changes recommendations

Why it matters:
- if all windows look similar, the long-horizon layer adds little value

Compare:
- normal/realtime window
- `weekday_peak`
- `sale_day_evening`
- `month_end_billing`

Expected evidence:
- `sale_day_evening` and other surge windows produce higher:
  - `avg_expected_rps`
  - `peak_expected_rps`
  - `target_workers`
- `demand_level` changes between `normal`, `elevated`, and `surge`

Pass criteria:
- at least one strategic surge window clearly differs from normal in both forecast and recommendation

### C3. Predictive Rules Change Decisions Before Purely Reactive Policies Would

Claim:
- predictive mode reacts to impending stress, not only current stress

Why it matters:
- otherwise it is just a reactive policy with a nicer name

Test scenario:
- `sale_day_surge_with_fault`

Compare:
- `least_connections`
- `predictive_rules`

Expected evidence:
- predictive mode shifts routing weights or recommendations earlier
- predictive mode shows stronger protective behavior during elevated-demand windows

Pass criteria:
- there is at least one observable control decision in predictive mode that is different from the simpler baseline for a defensible reason

### C4. Predictive Rules Improve Outcomes Over A Baseline

Claim:
- predictive control provides measurable value

Why it matters:
- this is the main product claim

Primary comparison scenarios:
- `worker_slowdown`
- `sale_day_surge_with_fault`

Compare:
- `round_robin`
- `least_connections`
- `predictive_rules`

Primary metrics:
- `latency_p95_ms`
- `latency_p99_ms`
- `max_queue_depth`
- `requests_failed`
- `throughput_avg_rps`
- recovery behavior

Success examples:
- lower `p95` than `round_robin`
- lower queue buildup than `round_robin`
- similar throughput with lower tail latency
- less severe degradation during slowdown

Pass criteria:
- at least one meaningful scenario shows a clear win for `predictive_rules` over one simpler baseline

### C5. The System Can Explain Why Predictive Mode Helped Or Failed

Claim:
- the system is explainable enough for demos and interviews

Why it matters:
- graphs without interpretation are weak proof

Expected evidence:
- run summary
- stored timeseries
- worker timeseries
- event log
- dashboard control-plane state

You should be able to explain:
- what stress entered the system
- what the predictor saw
- what the orchestrator recommended
- how routing or target workers changed
- how the metrics moved afterward

Pass criteria:
- a full run can be explained step by step using stored artifacts

### C6. Agentic Mode Adds Value Beyond Predictive Rules

This is future-facing until `agentic` is implemented.

Claim:
- `agentic` should not only make more decisions; it should improve results enough to justify added complexity

Compare:
- `predictive_rules`
- `agentic`

Expected agentic-only evidence:
- candidate action evaluation
- chosen action history
- post-action outcome evaluation
- fewer bad actions over time

Success examples:
- lower `p95` than `predictive_rules`
- lower queue peaks
- faster recovery
- fewer unstable route-weight oscillations

Pass criteria:
- in at least one hard scenario, `agentic` performs better than `predictive_rules` by a metric that matters

## Primary Validation Scenarios

Use these as the main evaluation suite:

### S1. `smoke_fault`

Purpose:
- prove the signal path and experiment path are alive

What it validates:
- basic predictor response
- fault injection
- artifact creation

### S2. `worker_slowdown`

Purpose:
- compare reactive vs predictive behavior under partial degradation

What it validates:
- whether smart routing helps a slowed worker scenario

### S3. `sale_day_surge`

Purpose:
- validate strategic forecasting and strategic recommendations

What it validates:
- historical forecaster usefulness

### S4. `sale_day_surge_with_fault`

Purpose:
- the main “hard mode” scenario

What it validates:
- interaction of:
  - strategic forecasting
  - tactical prediction
  - degraded worker behavior
  - routing policy quality

This should be the flagship comparison scenario.

## Metrics That Matter Most

Prioritize these:

1. `latency_p95_ms`
2. `latency_p99_ms`
3. `max_queue_depth`
4. `requests_failed`
5. `throughput_avg_rps`
6. `max_predicted_pressure`
7. `target_workers`

Secondary:

- policy weight shifts
- demand level
- action count
- recovery time

## Strong Minimum Acceptance Bar

Before AWS or agentic expansion, the product should meet all of these:

1. predictor responds meaningfully during fault or burst scenarios
2. strategic forecast distinguishes at least one surge window from a normal one
3. predictive mode makes a different control decision than a simpler baseline in at least one hard scenario
4. predictive mode shows at least one measurable improvement over a baseline
5. the stored artifacts are sufficient to explain the win or failure

If these are not true, then the predictive claim is not yet proven.

## Recommended Validation Order

Run validation in this order:

1. `smoke_fault` with `predictive_rules`
   - prove signal path
2. strategic window comparison
   - normal
   - `weekday_peak`
   - `sale_day_evening`
3. `worker_slowdown`
   - compare `round_robin`
   - compare `least_connections`
   - compare `predictive_rules`
4. `sale_day_surge_with_fault`
   - compare `round_robin`
   - compare `least_connections`
   - compare `predictive_rules`
5. later:
   - compare `predictive_rules`
   - compare `agentic`

## Evidence To Keep

For each important validation run, keep:

- scenario
- mode
- summary JSON
- comparison JSON
- event log
- screenshot of dashboard charts
- short interpretation

Suggested interpretation template:

- `Claim tested`
- `Observed result`
- `Why it happened`
- `Pass / Fail / Inconclusive`

## What To Say If Someone Asks

Short answer:

The project is validated around whether predictive and later agentic control actually outperform simpler routing policies, not just whether the services run.

Proof answer:

I use repeatable scenarios with load generation, worker faults, time-window forecasting, stored run artifacts, and comparison charts. The key question is whether predictive or agentic control reduces tail latency, queue buildup, or overload compared to `round_robin` or `least_connections` in the same scenario.
