# Worker Service

Responsibilities:
- simulate request processing
- expose health and Prometheus metrics
- support injected latency faults

## Endpoints

- `POST /work`
- `GET /health`
- `POST /faults/latency`
- `POST /faults/clear`
- `GET /metrics`

## Local Run

```powershell
cd services/worker
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:WORKER_ID="worker-local"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Verification

Once running:

- `GET http://localhost:8000/health`
- `POST http://localhost:8000/work`
- `POST http://localhost:8000/faults/latency`
- `GET http://localhost:8000/metrics`
