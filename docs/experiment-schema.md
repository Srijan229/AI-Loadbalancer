# Experiment Schema

This file defines the canonical run schema for baseline and agentic comparisons.

## 1. Run Metadata

File:
- `data/experiments/runs/<run_id>/metadata.json`

Example:

```json
{
  "run_id": "run_2026_05_03_001",
  "mode": "predictive_rules",
  "scenario_id": "sale_day_surge_with_fault",
  "started_at": "2026-05-03T22:00:00Z",
  "ended_at": "2026-05-03T22:03:00Z",
  "duration_seconds": 180,
  "status": "completed",
  "time_context": {
    "controller_mode": "frozen",
    "effective_time_utc": "2026-05-30T20:00:00Z",
    "preset": "sale_day_evening"
  },
  "load_profile": {
    "type": "burst",
    "users": 80,
    "spawn_rate": 20,
    "duration_seconds": 180,
    "target_rps": 120
  },
  "failure_plan": [
    {
      "type": "latency_injection",
      "target": "worker-a",
      "delay_ms": 800,
      "at_second": 50,
      "duration_seconds": 60
    }
  ]
}
```

## 2. Time-Series Summary Points

File:
- `data/experiments/runs/<run_id>/timeseries.jsonl`

Each line is a system-level sample at a fixed interval, ideally every `1` or `2` seconds.

Example:

```json
{
  "run_id": "run_2026_05_03_001",
  "timestamp": "2026-05-03T22:00:42Z",
  "mode": "predictive_rules",
  "gateway_rps": 108.2,
  "gateway_p50_ms": 58.1,
  "gateway_p95_ms": 172.4,
  "gateway_p99_ms": 301.7,
  "gateway_error_rate": 0.01,
  "healthy_workers": 2,
  "total_inflight": 14,
  "max_queue_depth": 5,
  "max_load_score": 9.3,
  "max_predicted_pressure": 14.8,
  "strategic_avg_expected_rps": 63.4,
  "strategic_peak_expected_rps": 86.6,
  "target_workers": 3
}
```

## 3. Worker Time-Series Points

File:
- `data/experiments/runs/<run_id>/worker_timeseries.jsonl`

Example:

```json
{
  "run_id": "run_2026_05_03_001",
  "timestamp": "2026-05-03T22:00:42Z",
  "worker_id": "worker-a",
  "healthy": true,
  "inflight": 9,
  "queue_depth": 5,
  "load_score": 9.3,
  "predicted_pressure": 14.8,
  "policy_weight": 0.22,
  "artificial_delay_ms": 800
}
```

## 4. Run Events

File:
- `data/experiments/runs/<run_id>/events.jsonl`

This captures mode changes, fault injections, time jumps, and scenario milestones.

Example:

```json
{
  "run_id": "run_2026_05_03_001",
  "timestamp": "2026-05-03T22:00:50Z",
  "event_type": "fault_injected",
  "target": "worker-a",
  "payload": {
    "delay_ms": 800,
    "duration_seconds": 60
  }
}
```

## 5. Agent Decisions

File:
- `data/experiments/runs/<run_id>/agent_decisions.jsonl`

Only used when `mode = agentic`.

Example:

```json
{
  "run_id": "run_2026_05_03_001",
  "timestamp": "2026-05-03T22:00:40Z",
  "state_id": "state_442",
  "chosen_action": "reduce_weight_worker_a_30pct",
  "candidate_actions": [
    {"action": "hold", "score": 0.41},
    {"action": "reduce_weight_worker_a_30pct", "score": 0.76},
    {"action": "pre_scale_up", "score": 0.63}
  ],
  "reason": "predicted pressure rising on worker-a during elevated demand window"
}
```

## 6. Run Summary

File:
- `data/experiments/runs/<run_id>/summary.json`

Example:

```json
{
  "run_id": "run_2026_05_03_001",
  "mode": "predictive_rules",
  "scenario_id": "sale_day_surge_with_fault",
  "requests_total": 18120,
  "requests_failed": 91,
  "throughput_avg_rps": 100.7,
  "latency_p50_ms": 61.4,
  "latency_p95_ms": 188.3,
  "latency_p99_ms": 301.7,
  "error_rate": 0.005,
  "max_queue_depth": 8,
  "max_load_score": 9.8,
  "max_predicted_pressure": 15.1,
  "recovery_time_seconds": 21,
  "scaling_actions": 1,
  "routing_weight_changes": 12,
  "score": 0.74
}
```

## 7. Shared vs Agentic Fields

### Shared across all modes

- metadata
- timeseries
- worker_timeseries
- events
- summary
- comparison artifacts generated from completed summaries

### Extra fields for `agentic`

- `agent_decisions.jsonl`
- later:
  - `memory_events.jsonl`
  - `reward_trace.jsonl`

This lets baseline and agentic runs live in the same directory layout without introducing separate incompatible models.
