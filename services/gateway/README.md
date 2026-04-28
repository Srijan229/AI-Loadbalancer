# Gateway Service

Responsibilities:
- receive external requests
- select worker targets
- apply routing modes and orchestrator policy
- export metrics

## Endpoints

- `POST /work`
- `GET /health`
- `GET /mode`
- `POST /mode`
- `GET /metrics`

## Gateway v1 Scope

Current implementation supports:
- static worker list from `WORKER_URLS`
- `round_robin` mode
- `least_connections` mode
- request forwarding to worker `/work`
- Prometheus metrics for request volume and latency
- gateway-side per-worker in-flight tracking
- optional orchestrator policy polling via `ORCHESTRATOR_URL`

## Local Run

```powershell
cd services/gateway
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:WORKER_URLS="http://127.0.0.1:8000,http://127.0.0.1:8002"
$env:ORCHESTRATOR_URL="http://127.0.0.1:8003"
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Verification

Once running:

- `GET http://localhost:8001/health`
- `GET http://localhost:8001/mode`
- `POST http://localhost:8001/mode`
- `POST http://localhost:8001/work`
- `GET http://localhost:8001/metrics`
