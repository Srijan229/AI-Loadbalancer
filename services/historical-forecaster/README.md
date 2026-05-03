# Historical Forecaster Service

Responsibilities:
- load synthetic historical workload data
- forecast long-horizon demand using seasonal/event patterns
- explain what historical pattern bucket was matched

## Endpoints

- `GET /health`
- `GET /summary`
- `POST /forecast`

## Local Run

```powershell
cd services/historical-forecaster
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8005
```
