# Experiment Runner Service

This service is the entrypoint for reproducible comparison runs across:

- `round_robin`
- `least_connections`
- `predictive_rules`
- `agentic`

## Current Scope

The first implementation slice supports:

- loading scenario definitions from `data/experiments/scenarios`
- listing scenarios
- creating run folders
- persisting `metadata.json` for new runs
- applying time presets or resuming realtime
- setting the orchestrator mode for executable runs
- writing `events.jsonl`
- running a headless Locust scenario
- injecting scheduled latency faults
- writing a basic `summary.json`
- writing `timeseries.jsonl`
- writing `worker_timeseries.jsonl`
- retrieving stored run metadata

It does not yet:

- package scenario data into a Kubernetes deployment

## Endpoints

- `GET /health`
- `GET /scenarios`
- `POST /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/prepare`
- `POST /runs/{run_id}/execute`
- `GET /runs/{run_id}/events`
- `GET /comparisons/{scenario_id}`

## Local Run

```powershell
cd services/experiment-runner
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PROJECT_ROOT="D:\\ai-autoscaller"
uvicorn app.main:app --host 127.0.0.1 --port 8007
```

This first slice is intentionally local-first.
The service reads scenarios directly from the repo under `data/experiments/scenarios`.

## Example Usage

List scenarios:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8007/scenarios
```

Create a run:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8007/runs -ContentType "application/json" -Body '{"scenario_id":"sale_day_surge_with_fault","mode":"predictive_rules"}'
```

Prepare a run:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8007/runs/<run_id>/prepare
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8007/runs/<run_id>/events
```

Execute a run:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8007/runs/<run_id>/execute
```

Useful local env vars for execution:

- `DASHBOARD_URL`
- `GATEWAY_URL`
- `WORKER_ENDPOINTS`
- `ORCHESTRATOR_URL`
- `TIME_CONTROLLER_URL`

Example:

```powershell
$env:DASHBOARD_URL="http://127.0.0.1:8510"
$env:GATEWAY_URL="http://127.0.0.1:8301"
$env:WORKER_ENDPOINTS="worker-a=http://127.0.0.1:8220,worker-b=http://127.0.0.1:8221"
```
