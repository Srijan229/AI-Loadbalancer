import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response


PREDICTOR_POLL_SECONDS = float(os.getenv("PREDICTOR_POLL_SECONDS", "2"))
TREND_WEIGHT = float(os.getenv("PREDICTOR_TREND_WEIGHT", "0.7"))


class PredictorState:
    def __init__(self) -> None:
        self.metrics_collector_url = os.getenv("METRICS_COLLECTOR_URL", "http://metrics-collector:8004").strip().rstrip("/")
        self.snapshot: dict[str, Any] = {
            "generated_at": None,
            "source_snapshot_at": None,
            "workers": [],
            "summary": {
                "healthy_workers": 0,
                "max_predicted_pressure": 0.0,
                "prediction_count": 0,
            },
        }
        self.previous_scores: dict[str, float] = {}
        self.client: httpx.AsyncClient | None = None
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()

    async def update_snapshot(self, snapshot: dict[str, Any]) -> None:
        async with self.lock:
            self.snapshot = snapshot

    async def read_snapshot(self) -> dict[str, Any]:
        async with self.lock:
            return self.snapshot


PREDICTED_PRESSURE = Gauge(
    "predictor_worker_pressure_score",
    "Predicted near-term worker pressure score.",
    ["worker_id"],
)
HEALTHY_WORKERS = Gauge(
    "predictor_healthy_workers",
    "Number of healthy workers in the latest prediction snapshot.",
)
MAX_PRESSURE = Gauge(
    "predictor_max_pressure_score",
    "Maximum predicted pressure in the latest prediction snapshot.",
)


state = PredictorState()


def _compute_pressure(worker: dict[str, Any], previous_score: float) -> float:
    base_score = (
        float(worker.get("inflight_requests", 0))
        + (float(worker.get("queue_depth", 0)) * 1.5)
        + (float(worker.get("artificial_delay_ms", 0)) / 100.0)
        + float(worker.get("load_score", 0.0))
    )
    trend = max(base_score - previous_score, 0.0)
    return round(base_score + (trend * TREND_WEIGHT), 3)


async def _prediction_loop() -> None:
    while True:
        try:
            assert state.client is not None
            response = await state.client.get(f"{state.metrics_collector_url}/snapshot")
            response.raise_for_status()
            collector_snapshot = response.json()
        except Exception:
            await asyncio.sleep(PREDICTOR_POLL_SECONDS)
            continue

        workers: list[dict[str, Any]] = []
        next_scores: dict[str, float] = {}
        for worker in collector_snapshot.get("workers", []):
            worker_id = worker.get("worker_id", "unknown")
            previous_score = state.previous_scores.get(worker_id, 0.0)
            predicted_pressure = _compute_pressure(worker, previous_score)
            next_scores[worker_id] = predicted_pressure
            workers.append(
                {
                    "worker_id": worker_id,
                    "healthy": worker.get("healthy", False),
                    "current_load_score": round(float(worker.get("load_score", 0.0)), 3),
                    "predicted_pressure": predicted_pressure,
                    "queue_depth": worker.get("queue_depth", 0),
                    "inflight_requests": worker.get("inflight_requests", 0),
                    "artificial_delay_ms": worker.get("artificial_delay_ms", 0),
                }
            )
            PREDICTED_PRESSURE.labels(worker_id).set(predicted_pressure)

        healthy_workers = sum(1 for worker in workers if worker["healthy"])
        max_pressure = max((worker["predicted_pressure"] for worker in workers), default=0.0)
        HEALTHY_WORKERS.set(healthy_workers)
        MAX_PRESSURE.set(max_pressure)
        state.previous_scores = next_scores
        await state.update_snapshot(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "source_snapshot_at": collector_snapshot.get("generated_at"),
                "workers": workers,
                "summary": {
                    "healthy_workers": healthy_workers,
                    "max_predicted_pressure": max_pressure,
                    "prediction_count": len(workers),
                },
            }
        )
        await asyncio.sleep(PREDICTOR_POLL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.client = httpx.AsyncClient(timeout=5.0)
    state.task = asyncio.create_task(_prediction_loop())
    try:
        yield
    finally:
        if state.task is not None:
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass
            state.task = None
        if state.client is not None:
            await state.client.aclose()
            state.client = None


app = FastAPI(title="predictor-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    snapshot = await state.read_snapshot()
    return {
        "status": "ok",
        "service": "predictor",
        "generated_at": snapshot.get("generated_at"),
        "metrics_collector_url": state.metrics_collector_url,
    }


@app.get("/predictions")
async def predictions() -> dict[str, Any]:
    return await state.read_snapshot()


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
