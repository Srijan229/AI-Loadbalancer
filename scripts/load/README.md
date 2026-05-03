# Load Testing With Locust

This directory contains the first reproducible load-generation harness for the project.

## Why Locust

Locust gives us:
- realistic concurrency
- reusable traffic scenarios
- reproducible benchmarks
- an industry-recognized tool that fits the Python stack

## Files

- `locustfile.py`: traffic user and load shape definitions
- `requirements.txt`: Locust dependency

## Target

Locust should target the `gateway`, not workers directly.

That keeps the benchmark aligned with how the system is meant to behave.

## Supported Scenarios

- `constant`
- `burst`
- `spike`

Select a scenario with `LOAD_SCENARIO`.

## Local Setup

```powershell
cd scripts/load
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Web UI Mode

```powershell
$env:LOAD_SCENARIO="burst"
locust -f locustfile.py --host http://127.0.0.1:8301
```

Open `http://127.0.0.1:8089`.

## Headless Mode

```powershell
$env:LOAD_SCENARIO="constant"
locust -f locustfile.py --host http://127.0.0.1:8301 --headless
```

## Example Scenarios

### Constant

```powershell
$env:LOAD_SCENARIO="constant"
$env:CONSTANT_USERS="12"
$env:CONSTANT_DURATION_SECONDS="60"
locust -f locustfile.py --host http://127.0.0.1:8301 --headless
```

### Burst

```powershell
$env:LOAD_SCENARIO="burst"
$env:BURST_BASELINE_USERS="10"
$env:BURST_USERS="35"
$env:BURST_DURATION_SECONDS="120"
locust -f locustfile.py --host http://127.0.0.1:8301 --headless
```

### Spike

```powershell
$env:LOAD_SCENARIO="spike"
$env:SPIKE_USERS="50"
locust -f locustfile.py --host http://127.0.0.1:8301 --headless
```

## What To Compare

Run the same scenario against:
- `round_robin`
- `least_connections`
- later: `predictive`

Track:
- average latency
- p95 latency
- request throughput
- failures

