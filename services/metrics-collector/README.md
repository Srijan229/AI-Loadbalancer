# Metrics Collector Service

Responsibilities:
- gather metrics snapshots
- normalize worker and gateway state
- store recent snapshots for orchestration

## Endpoints

- `GET /health`
- `GET /snapshot`
- `POST /collect`
- `GET /metrics`

## Collector v1 Scope

Current implementation supports:
- polling gateway `/health`
- polling worker `/health`
- building a normalized telemetry snapshot
- exposing aggregated summary values for the orchestrator

## Local Run

```powershell
cd services/metrics-collector
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GATEWAY_URLS="http://127.0.0.1:8115"
$env:WORKER_URLS="http://127.0.0.1:8110,http://127.0.0.1:8112"
uvicorn app.main:app --host 0.0.0.0 --port 8004
```
