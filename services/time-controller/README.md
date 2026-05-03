# Time Controller Service

Responsibilities:
- maintain simulation time for strategic forecasting
- support fast-forward and jump-to actions
- provide preset scenario jumps for demos

## Endpoints

- `GET /health`
- `GET /time`
- `GET /presets`
- `POST /time/freeze`
- `POST /time/resume`
- `POST /time/set`
- `POST /time/advance`
- `POST /time/preset`

## Local Run

```powershell
cd services/time-controller
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8006
```
