FROM python:3.12-slim

WORKDIR /app

COPY services/experiment-runner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/experiment-runner/app ./app
COPY scripts/load ./scripts/load
COPY data/experiments ./data/experiments

ENV PROJECT_ROOT=/app

EXPOSE 8007

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]
