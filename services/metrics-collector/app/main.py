import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.responses import Response


COLLECTOR_POLL_SECONDS = float(os.getenv("COLLECTOR_POLL_SECONDS", "2"))


def _load_urls(env_name: str, default: str) -> list[str]:
    raw_value = os.getenv(env_name, default)
    values = [value.strip().rstrip("/") for value in raw_value.split(",") if value.strip()]
    if not values:
        raise ValueError(f"{env_name} must contain at least one URL.")
    return values


class CollectorState:
    def __init__(self) -> None:
        self.gateway_urls = _load_urls("GATEWAY_URLS", "http://gateway:8001")
        self.worker_urls = _load_urls("WORKER_URLS", "http://worker-a:8000,http://worker-b:8000")
        self.snapshot: dict[str, Any] = {
            "generated_at": None,
            "gateways": [],
            "workers": [],
            "summary": {
                "healthy_gateways": 0,
                "healthy_workers": 0,
                "total_worker_inflight": 0,
                "max_worker_load_score": 0.0,
            },
        }
        self.lock = asyncio.Lock()
        self.client: httpx.AsyncClient | None = None
        self.task: asyncio.Task | None = None

    async def update_snapshot(self, snapshot: dict[str, Any]) -> None:
        async with self.lock:
            self.snapshot = snapshot

    async def read_snapshot(self) -> dict[str, Any]:
        async with self.lock:
            return self.snapshot


SCRAPE_SUCCESS = Counter(
    "metrics_collector_scrapes_total",
    "Total successful collector scrapes.",
    ["target_type"],
)
SCRAPE_FAILURE = Counter(
    "metrics_collector_scrape_failures_total",
    "Total failed collector scrapes.",
    ["target_type"],
)
HEALTHY_TARGETS = Gauge(
    "metrics_collector_healthy_targets",
    "Number of healthy targets by type in the latest collector snapshot.",
    ["target_type"],
)
TOTAL_WORKER_INFLIGHT = Gauge(
    "metrics_collector_total_worker_inflight",
    "Total worker in-flight requests in the latest collector snapshot.",
)
MAX_WORKER_LOAD_SCORE = Gauge(
    "metrics_collector_max_worker_load_score",
    "Maximum observed worker load score in the latest collector snapshot.",
)


state = CollectorState()


async def _fetch_health(url: str, target_type: str) -> dict[str, Any]:
    assert state.client is not None
    try:
        response = await state.client.get(f"{url}/health")
        response.raise_for_status()
        SCRAPE_SUCCESS.labels(target_type).inc()
        return {"url": url, "healthy": True, "data": response.json()}
    except Exception as exc:
        SCRAPE_FAILURE.labels(target_type).inc()
        return {"url": url, "healthy": False, "error": str(exc), "data": None}


def _normalize_gateway(entry: dict[str, Any]) -> dict[str, Any]:
    data = entry.get("data") or {}
    return {
        "gateway_url": entry["url"],
        "healthy": entry["healthy"],
        "mode": data.get("mode"),
        "policy_source": data.get("policy_source"),
        "policy_version": data.get("policy_version"),
        "worker_inflight": data.get("worker_inflight", {}),
    }


def _normalize_worker(entry: dict[str, Any]) -> dict[str, Any]:
    data = entry.get("data") or {}
    fault_state = data.get("fault_state") or {}
    return {
        "worker_url": entry["url"],
        "worker_id": data.get("worker_id", entry["url"].rsplit("/", maxsplit=1)[-1]),
        "healthy": entry["healthy"],
        "inflight_requests": data.get("inflight_requests", 0),
        "queue_depth": data.get("queue_depth", 0),
        "load_score": data.get("load_score", 0.0),
        "artificial_delay_ms": fault_state.get("artificial_delay_ms", 0),
    }


async def _collection_loop() -> None:
    while True:
        gateway_results = await asyncio.gather(
            *[_fetch_health(url, "gateway") for url in state.gateway_urls]
        )
        worker_results = await asyncio.gather(
            *[_fetch_health(url, "worker") for url in state.worker_urls]
        )

        gateways = [_normalize_gateway(entry) for entry in gateway_results]
        workers = [_normalize_worker(entry) for entry in worker_results]

        healthy_gateways = sum(1 for gateway in gateways if gateway["healthy"])
        healthy_workers = sum(1 for worker in workers if worker["healthy"])
        total_worker_inflight = sum(worker["inflight_requests"] for worker in workers)
        max_worker_load_score = max((worker["load_score"] for worker in workers), default=0.0)

        HEALTHY_TARGETS.labels("gateway").set(healthy_gateways)
        HEALTHY_TARGETS.labels("worker").set(healthy_workers)
        TOTAL_WORKER_INFLIGHT.set(total_worker_inflight)
        MAX_WORKER_LOAD_SCORE.set(max_worker_load_score)

        await state.update_snapshot(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "gateways": gateways,
                "workers": workers,
                "summary": {
                    "healthy_gateways": healthy_gateways,
                    "healthy_workers": healthy_workers,
                    "total_worker_inflight": total_worker_inflight,
                    "max_worker_load_score": max_worker_load_score,
                },
            }
        )
        await asyncio.sleep(COLLECTOR_POLL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.client = httpx.AsyncClient(timeout=5.0)
    state.task = asyncio.create_task(_collection_loop())
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


app = FastAPI(title="metrics-collector-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    snapshot = await state.read_snapshot()
    return {
        "status": "ok",
        "service": "metrics-collector",
        "generated_at": snapshot.get("generated_at"),
        "gateway_urls": state.gateway_urls,
        "worker_urls": state.worker_urls,
    }


@app.get("/snapshot")
async def snapshot() -> dict[str, Any]:
    return await state.read_snapshot()


@app.post("/collect")
async def collect_now() -> dict[str, str]:
    return {"status": "collector_runs_automatically"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

