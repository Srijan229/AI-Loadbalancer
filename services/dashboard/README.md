# Dashboard Service

This service provides a thin demo dashboard for the project.

It is intentionally not a product frontend. Its job is to make the distributed system easier to demo and reason about by combining:

- live system overview
- worker and predictor state
- orchestrator mode controls
- worker fault injection controls

## Endpoints

- `GET /`
- `GET /health`
- `GET /api/overview`
- `POST /api/mode`
- `POST /api/workers/{worker_id}/faults/latency`
- `POST /api/workers/{worker_id}/faults/clear`

## Environment Variables

- `GATEWAY_URL`
- `ORCHESTRATOR_URL`
- `METRICS_COLLECTOR_URL`
- `PREDICTOR_URL`
- `WORKER_URLS`

## Local Run

```powershell
cd services/dashboard
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GATEWAY_URL="http://127.0.0.1:8301"
$env:ORCHESTRATOR_URL="http://127.0.0.1:8302"
$env:METRICS_COLLECTOR_URL="http://127.0.0.1:8304"
$env:PREDICTOR_URL="http://127.0.0.1:8303"
$env:WORKER_URLS="http://127.0.0.1:8220,http://127.0.0.1:8221"
uvicorn app.main:app --host 127.0.0.1 --port 8010
```
