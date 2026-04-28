import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response


class GatewayWorkRequest(BaseModel):
    request_id: Optional[str] = None
    payload_size: int = Field(default=10, ge=1, le=10_000)
    work_units: int = Field(default=5, ge=1, le=1_000)


class ModeUpdateRequest(BaseModel):
    mode: str


SUPPORTED_MODES = {"round_robin", "least_connections"}


class WorkerWorkResponse(BaseModel):
    request_id: str
    worker_id: str
    processing_time_ms: float
    queue_depth: int
    status: str


class GatewayWorkResponse(BaseModel):
    request_id: str
    mode: str
    selected_worker: str
    worker_response_ms: float
    total_latency_ms: float
    result: WorkerWorkResponse


GATEWAY_REQUESTS = Counter(
    "gateway_requests_total",
    "Total number of requests handled by the gateway.",
    ["mode", "selected_worker", "status"],
)
GATEWAY_INFLIGHT = Gauge(
    "gateway_inflight_requests",
    "Current number of requests being handled by the gateway.",
)
GATEWAY_TOTAL_LATENCY = Histogram(
    "gateway_total_latency_ms",
    "End-to-end gateway latency in milliseconds.",
    ["mode", "selected_worker"],
    buckets=(5, 10, 20, 50, 100, 200, 500, 1000, 5000),
)
GATEWAY_UPSTREAM_LATENCY = Histogram(
    "gateway_upstream_latency_ms",
    "Observed upstream worker latency in milliseconds.",
    ["mode", "selected_worker"],
    buckets=(5, 10, 20, 50, 100, 200, 500, 1000, 5000),
)
GATEWAY_WORKER_COUNT = Gauge(
    "gateway_configured_workers",
    "Number of worker endpoints configured in the gateway.",
)
GATEWAY_WORKER_INFLIGHT = Gauge(
    "gateway_worker_inflight_requests",
    "Gateway-side count of in-flight upstream requests per worker.",
    ["worker"],
)


class GatewayState:
    def __init__(self) -> None:
        self.mode = "round_robin"
        self.worker_urls = self._load_worker_urls()
        self.next_index = 0
        self.lock = asyncio.Lock()
        self.client: Optional[httpx.AsyncClient] = None
        self.worker_inflight = {worker_url: 0 for worker_url in self.worker_urls}

    @staticmethod
    def _load_worker_urls() -> list[str]:
        raw_value = os.getenv("WORKER_URLS", "http://127.0.0.1:8000")
        worker_urls = [value.strip().rstrip("/") for value in raw_value.split(",") if value.strip()]
        if not worker_urls:
            raise ValueError("WORKER_URLS must contain at least one worker endpoint.")
        return worker_urls

    def _choose_round_robin_locked(self) -> str:
        worker_url = self.worker_urls[self.next_index]
        self.next_index = (self.next_index + 1) % len(self.worker_urls)
        return worker_url

    def _choose_least_connections_locked(self) -> str:
        lowest_inflight = min(self.worker_inflight.values())
        candidates = [
            worker_url for worker_url in self.worker_urls if self.worker_inflight[worker_url] == lowest_inflight
        ]
        start_index = self.next_index
        for offset in range(len(self.worker_urls)):
            candidate = self.worker_urls[(start_index + offset) % len(self.worker_urls)]
            if candidate in candidates:
                self.next_index = (self.worker_urls.index(candidate) + 1) % len(self.worker_urls)
                return candidate
        return candidates[0]

    async def begin_request(self) -> str:
        async with self.lock:
            if self.mode == "round_robin":
                worker_url = self._choose_round_robin_locked()
            elif self.mode == "least_connections":
                worker_url = self._choose_least_connections_locked()
            else:
                raise ValueError(f"Unsupported gateway mode: {self.mode}")
            self.worker_inflight[worker_url] += 1
            return worker_url

    async def finish_request(self, worker_url: str) -> None:
        async with self.lock:
            self.worker_inflight[worker_url] = max(self.worker_inflight[worker_url] - 1, 0)

    async def set_mode(self, mode: str) -> None:
        async with self.lock:
            self.mode = mode

    async def health_snapshot(self) -> dict:
        async with self.lock:
            return {
                "mode": self.mode,
                "configured_workers": self.worker_urls,
                "worker_inflight": {
                    _worker_label_from_url(worker_url): inflight
                    for worker_url, inflight in self.worker_inflight.items()
                },
            }


gateway_state = GatewayState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    GATEWAY_WORKER_COUNT.set(len(gateway_state.worker_urls))
    for worker_url in gateway_state.worker_urls:
        GATEWAY_WORKER_INFLIGHT.labels(_worker_label_from_url(worker_url)).set(0)
    gateway_state.client = httpx.AsyncClient(timeout=10.0)
    try:
        yield
    finally:
        if gateway_state.client is not None:
            await gateway_state.client.aclose()
            gateway_state.client = None


app = FastAPI(title="gateway-service", version="0.1.0", lifespan=lifespan)


def _worker_label_from_url(worker_url: str) -> str:
    return worker_url.rsplit("/", maxsplit=1)[-1] if "/" in worker_url else worker_url


@app.get("/health")
async def health() -> dict:
    snapshot = await gateway_state.health_snapshot()
    return {
        "status": "ok",
        "service": "gateway",
        **snapshot,
    }


@app.get("/mode")
async def get_mode() -> dict:
    return {"mode": gateway_state.mode}


@app.post("/mode")
async def set_mode(payload: ModeUpdateRequest) -> dict:
    if payload.mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported mode '{payload.mode}'. Supported modes: {sorted(SUPPORTED_MODES)}.",
        )
    await gateway_state.set_mode(payload.mode)
    return {"status": "updated", "mode": gateway_state.mode}


@app.post("/work", response_model=GatewayWorkResponse)
async def work(payload: GatewayWorkRequest) -> GatewayWorkResponse:
    request_id = payload.request_id or str(uuid.uuid4())
    selected_worker = await gateway_state.begin_request()
    selected_worker_label = _worker_label_from_url(selected_worker)
    GATEWAY_WORKER_INFLIGHT.labels(selected_worker_label).set(gateway_state.worker_inflight[selected_worker])
    GATEWAY_INFLIGHT.inc()
    started_at = time.perf_counter()

    try:
        if gateway_state.client is None:
            raise HTTPException(status_code=503, detail="Gateway HTTP client is not initialized.")
        upstream_response = await gateway_state.client.post(
            f"{selected_worker}/work",
            json={
                "request_id": request_id,
                "payload_size": payload.payload_size,
                "work_units": payload.work_units,
            },
        )
        upstream_response.raise_for_status()
    except httpx.HTTPError as exc:
        GATEWAY_REQUESTS.labels(gateway_state.mode, selected_worker_label, "error").inc()
        raise HTTPException(status_code=502, detail=f"Upstream worker call failed: {exc}") from exc
    finally:
        await gateway_state.finish_request(selected_worker)
        GATEWAY_WORKER_INFLIGHT.labels(selected_worker_label).set(gateway_state.worker_inflight[selected_worker])
        GATEWAY_INFLIGHT.dec()

    total_latency_ms = round((time.perf_counter() - started_at) * 1000, 3)
    worker_result = WorkerWorkResponse.model_validate(upstream_response.json())

    GATEWAY_REQUESTS.labels(gateway_state.mode, worker_result.worker_id, "ok").inc()
    GATEWAY_TOTAL_LATENCY.labels(gateway_state.mode, worker_result.worker_id).observe(total_latency_ms)
    GATEWAY_UPSTREAM_LATENCY.labels(gateway_state.mode, worker_result.worker_id).observe(
        worker_result.processing_time_ms
    )

    return GatewayWorkResponse(
        request_id=request_id,
        mode=gateway_state.mode,
        selected_worker=worker_result.worker_id,
        worker_response_ms=worker_result.processing_time_ms,
        total_latency_ms=total_latency_ms,
        result=worker_result,
    )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
