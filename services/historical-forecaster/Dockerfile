FROM python:3.12-slim

WORKDIR /app

COPY services/historical-forecaster/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/historical-forecaster/app ./app
COPY data/historical ./data/historical

EXPOSE 8005

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
