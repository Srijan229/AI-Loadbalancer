# API Contracts

These are the initial HTTP contracts for Stage 1.

## Gateway

### `POST /work`

Client-facing entrypoint.

Request:

```json
{
  "payload_size": 10,
  "work_units": 5,
  "request_id": "optional-client-id"
}
```

Response:

```json
{
  "request_id": "generated-or-forwarded-id",
  "mode": "predictive",
  "selected_worker": "worker-2",
  "worker_response_ms": 42.3,
  "total_latency_ms": 48.9,
  "result": {
    "status": "ok"
  }
}
```

### `GET /health`

Response:

```json
{
  "status": "ok",
  "service": "gateway",
  "mode": "least_connections",
  "configured_workers": [
    "http://worker-a:8000",
    "http://worker-b:8000"
  ],
  "worker_inflight": {
    "worker-a": 1,
    "worker-b": 0
  }
}
```

### `GET /mode`

Response:

```json
{
  "mode": "least_connections"
}
```

### `POST /mode`

Request:

```json
{
  "mode": "least_connections"
}
```

Response:

```json
{
  "status": "updated",
  "mode": "least_connections",
  "policy_version": 2
}
```

## Worker

### `POST /work`

Request:

```json
{
  "request_id": "req-123",
  "payload_size": 10,
  "work_units": 5
}
```

Response:

```json
{
  "request_id": "req-123",
  "worker_id": "worker-1",
  "processing_time_ms": 37.8,
  "queue_depth": 2,
  "status": "ok"
}
```

### `GET /health`

Response:

```json
{
  "status": "ok",
  "worker_id": "worker-1",
  "fault_state": {
    "artificial_delay_ms": 0
  }
}
```

### `POST /faults/latency`

Request:

```json
{
  "delay_ms": 200,
  "duration_seconds": 30
}
```

Response:

```json
{
  "status": "fault_applied",
  "delay_ms": 200,
  "duration_seconds": 30
}
```

### `POST /faults/clear`

Response:

```json
{
  "status": "fault_cleared"
}
```

## Orchestrator

### `GET /policy`

Response:

```json
{
  "mode": "predictive",
  "version": 3,
  "generated_at": "2026-04-26T15:00:00Z",
  "strategic_forecast": {
    "avg_expected_rps": 61.2,
    "peak_expected_rps": 88.5,
    "peak_recommended_workers": 3,
    "demand_level": "surge"
  },
  "scale_recommendation": {
    "action": "pre_scale_up",
    "current_workers": 2,
    "target_workers": 3
  },
  "workers": [
    {
      "worker_id": "worker-1",
      "weight": 0.55,
      "healthy": true,
      "reason": "low_latency_low_pressure"
    },
    {
      "worker_id": "worker-2",
      "weight": 0.30,
      "healthy": true,
      "reason": "moderate_pressure"
    },
    {
      "worker_id": "worker-3",
      "weight": 0.15,
      "healthy": false,
      "reason": "high_latency_fault_penalty"
    }
  ]
}
```

### `GET /recommendations`

Response:

```json
{
  "generated_at": "2026-05-03T21:00:00Z",
  "effective_time_utc": "2026-05-09T20:00:00Z",
  "strategic_forecast": {
    "avg_expected_rps": 61.2,
    "peak_expected_rps": 88.5,
    "peak_recommended_workers": 3,
    "demand_level": "surge",
    "matched_strategies": ["exact_day_hour_minute_sale_event"]
  },
  "scale_recommendation": {
    "action": "pre_scale_up",
    "current_workers": 2,
    "target_workers": 3,
    "demand_level": "surge"
  }
}
```

### `POST /mode`

Request:

```json
{
  "mode": "predictive"
}
```

Response:

```json
{
  "status": "updated",
  "mode": "predictive"
}
```

### `GET /workers`

Response:

```json
{
  "workers": [
    {
      "worker_id": "worker-1",
      "healthy": true,
      "inflight": 2,
      "queue_depth": 1,
      "latency_ms": 35.4,
      "predicted_pressure": 0.42
    }
  ]
}
```

## Metrics Collector

### `POST /collect`

Optional manual trigger for local testing.

Response:

```json
{
  "status": "collector_runs_automatically"
}
```

### `GET /snapshot`

Response:

```json
{
  "generated_at": "2026-04-28T20:00:00Z",
  "gateways": [
    {
      "gateway_url": "http://gateway:8001",
      "healthy": true,
      "mode": "least_connections",
      "policy_source": "orchestrator",
      "policy_version": 2,
      "worker_inflight": {
        "worker-a:8000": 1,
        "worker-b:8000": 0
      }
    }
  ],
  "workers": [
    {
      "worker_url": "http://worker-a:8000",
      "worker_id": "worker-a",
      "healthy": true,
      "inflight_requests": 1,
      "queue_depth": 0,
      "load_score": 6.2,
      "artificial_delay_ms": 500
    }
  ],
  "summary": {
    "healthy_gateways": 1,
    "healthy_workers": 2,
    "total_worker_inflight": 1,
    "max_worker_load_score": 6.2
  }
}
```

## Predictor

### `GET /forecast`

Response:

```json
{
  "window_seconds": 60,
  "forecast": [
    {
      "worker_id": "worker-1",
      "predicted_rps": 18.2,
      "predicted_latency_ms": 44.1,
      "predicted_pressure": 0.47
    }
  ]
}
```

## Failure Injector

### `POST /workers/slow-random`

Request:

```json
{
  "delay_ms": 250,
  "duration_seconds": 20
}
```

### `POST /workers/kill-random`

Request:

```json
{
  "grace_period_seconds": 0
}
```

## Experiment Runner

### `POST /scenarios/run`

Request:

```json
{
  "mode": "predictive",
  "traffic_pattern": "bursty",
  "duration_seconds": 120,
  "inject_failure": true
}
```

Response:

```json
{
  "run_id": "exp-001",
  "status": "started"
}
```
