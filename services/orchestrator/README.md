# Orchestrator Service

Responsibilities:
- manage routing mode
- compute worker weights
- exclude unhealthy workers
- publish current routing policy

## Endpoints

- `GET /health`
- `GET /mode`
- `POST /mode`
- `GET /policy`
- `GET /workers`
- `GET /metrics`

## Orchestrator v1 Scope

Current implementation supports:
- control-plane ownership of active routing mode
- policy publication for gateway polling
- static worker policy output for baseline modes

## Local Run

```powershell
cd services/orchestrator
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:WORKER_URLS="http://127.0.0.1:8010,http://127.0.0.1:8012"
uvicorn app.main:app --host 0.0.0.0 --port 8002
```
