# Predictor Service

Responsibilities:
- consume recent metrics
- forecast short-term load
- emit predicted pressure scores

## Endpoints

- `GET /health`
- `GET /predictions`
- `GET /metrics`

## Predictor v1 Scope

Current implementation supports:
- polling the metrics collector snapshot
- computing short-horizon per-worker pressure scores
- exposing normalized predictions for the orchestrator

## Local Run

```powershell
cd services/predictor
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:METRICS_COLLECTOR_URL="http://127.0.0.1:8004"
uvicorn app.main:app --host 0.0.0.0 --port 8003
```
