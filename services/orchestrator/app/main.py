import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.responses import Response


SUPPORTED_MODES = {"round_robin", "least_connections", "predictive"}


class ModeUpdateRequest(BaseModel):
    mode: str


class WorkerPolicy(BaseModel):
    worker_id: str
    weight: float
    healthy: bool
    reason: str


class OrchestratorState:
    def __init__(self) -> None:
        self.mode = os.getenv("DEFAULT_MODE", "round_robin")
        self.policy_version = 1
        self.worker_urls = self._load_worker_urls()
        self.metrics_collector_url = os.getenv("METRICS_COLLECTOR_URL", "").strip().rstrip("/")
        self.client: httpx.AsyncClient | None = None

    @staticmethod
    def _load_worker_urls() -> list[str]:
        raw_value = os.getenv("WORKER_URLS", "http://worker-a:8000,http://worker-b:8000")
        worker_urls = [value.strip().rstrip("/") for value in raw_value.split(",") if value.strip()]
        if not worker_urls:
            raise ValueError("WORKER_URLS must contain at least one worker endpoint.")
        return worker_urls

    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.mode = mode
            self.policy_version += 1

    def build_policy(self) -> dict:
        weight = round(1.0 / len(self.worker_urls), 4)
        workers = [
            WorkerPolicy(
                worker_id=worker_url.rsplit("/", maxsplit=1)[-1],
                weight=weight,
                healthy=True,
                reason="static_baseline_policy",
            ).model_dump()
            for worker_url in self.worker_urls
        ]
        return {
            "mode": self.mode,
            "version": self.policy_version,
            "generated_at": datetime.now(UTC).isoformat(),
            "workers": workers,
        }

    async def fetch_collector_snapshot(self) -> dict[str, Any] | None:
        if not self.metrics_collector_url or self.client is None:
            return None
        try:
            response = await self.client.get(f"{self.metrics_collector_url}/snapshot")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None


MODE_CHANGES = Counter(
    "orchestrator_mode_updates_total",
    "Total number of orchestrator mode updates.",
    ["mode"],
)
CURRENT_MODE = Gauge(
    "orchestrator_current_mode_info",
    "Current orchestrator mode encoded as labeled gauges.",
    ["mode"],
)
POLICY_VERSION = Gauge(
    "orchestrator_policy_version",
    "Current policy version published by the orchestrator.",
)


state = OrchestratorState()


def _set_mode_metrics(active_mode: str) -> None:
    for mode in SUPPORTED_MODES:
        CURRENT_MODE.labels(mode).set(1 if mode == active_mode else 0)
    POLICY_VERSION.set(state.policy_version)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.client = httpx.AsyncClient(timeout=5.0)
    _set_mode_metrics(state.mode)
    try:
        yield
    finally:
        if state.client is not None:
            await state.client.aclose()
            state.client = None


app = FastAPI(title="orchestrator-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "orchestrator",
        "mode": state.mode,
        "policy_version": state.policy_version,
        "configured_workers": state.worker_urls,
        "metrics_collector_url": state.metrics_collector_url or None,
    }


@app.get("/mode")
async def get_mode() -> dict:
    return {"mode": state.mode}


@app.post("/mode")
async def set_mode(payload: ModeUpdateRequest) -> dict:
    if payload.mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported mode '{payload.mode}'. Supported modes: {sorted(SUPPORTED_MODES)}.",
        )
    state.set_mode(payload.mode)
    MODE_CHANGES.labels(payload.mode).inc()
    _set_mode_metrics(state.mode)
    return {"status": "updated", "mode": state.mode, "policy_version": state.policy_version}


@app.get("/policy")
async def policy() -> dict:
    return state.build_policy()


@app.get("/workers")
async def workers() -> dict:
    snapshot = await state.fetch_collector_snapshot()
    if snapshot is not None:
        return {
            "generated_at": snapshot.get("generated_at"),
            "summary": snapshot.get("summary"),
            "workers": [
                {
                    "worker_id": worker.get("worker_id"),
                    "healthy": worker.get("healthy"),
                    "inflight": worker.get("inflight_requests"),
                    "queue_depth": worker.get("queue_depth"),
                    "latency_ms": None,
                    "predicted_pressure": None,
                    "load_score": worker.get("load_score"),
                    "artificial_delay_ms": worker.get("artificial_delay_ms"),
                }
                for worker in snapshot.get("workers", [])
            ],
        }
    return {
        "workers": [
            {
                "worker_id": worker_url.rsplit("/", maxsplit=1)[-1],
                "healthy": True,
                "inflight": 0,
                "queue_depth": 0,
                "latency_ms": None,
                "predicted_pressure": None,
            }
            for worker_url in state.worker_urls
        ]
    }


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
