import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response


class WorkRequest(BaseModel):
    request_id: Optional[str] = None
    payload_size: int = Field(default=10, ge=1, le=10_000)
    work_units: int = Field(default=5, ge=1, le=1_000)


class WorkResponse(BaseModel):
    request_id: str
    worker_id: str
    processing_time_ms: float
    queue_depth: int
    status: str = "ok"


class LatencyFaultRequest(BaseModel):
    delay_ms: int = Field(..., ge=0, le=60_000)
    duration_seconds: int = Field(..., ge=1, le=3_600)


class FaultState(BaseModel):
    artificial_delay_ms: int = 0
    expires_at_monotonic: Optional[float] = None


REQUEST_COUNT = Counter(
    "worker_requests_total",
    "Total number of requests handled by the worker.",
    ["worker_id"],
)
INFLIGHT_REQUESTS = Gauge(
    "worker_inflight_requests",
    "Current number of in-flight requests.",
    ["worker_id"],
)
QUEUE_DEPTH = Gauge(
    "worker_queue_depth",
    "Current simulated queue depth.",
    ["worker_id"],
)
PROCESSING_LATENCY = Histogram(
    "worker_processing_latency_ms",
    "Observed worker processing latency in milliseconds.",
    ["worker_id"],
    buckets=(5, 10, 20, 50, 100, 200, 500, 1000, 5000),
)
FAULT_DELAY = Gauge(
    "worker_fault_delay_ms",
    "Current injected artificial delay in milliseconds.",
    ["worker_id"],
)
LOAD_SCORE = Gauge(
    "worker_load_score",
    "Synthetic load score derived from active work and fault delay.",
    ["worker_id"],
)


class WorkerState:
    def __init__(self, worker_id: str) -> None:
        self.worker_id = worker_id
        self.inflight_requests = 0
        self.total_work_units = 0
        self.fault_state = FaultState()
        self.lock = asyncio.Lock()

    def current_queue_depth(self) -> int:
        return max(self.inflight_requests - 1, 0)

    def active_delay_ms(self) -> int:
        if (
            self.fault_state.expires_at_monotonic is not None
            and time.monotonic() >= self.fault_state.expires_at_monotonic
        ):
            self.fault_state = FaultState()
        return self.fault_state.artificial_delay_ms

    def current_load_score(self) -> float:
        delay_penalty = self.active_delay_ms() / 100.0
        return round(self.inflight_requests + (self.total_work_units / 10.0) + delay_penalty, 3)


worker_state = WorkerState(worker_id=os.getenv("WORKER_ID", "worker-local"))


async def _fault_cleanup_loop() -> None:
    while True:
        worker_state.active_delay_ms()
        FAULT_DELAY.labels(worker_state.worker_id).set(worker_state.fault_state.artificial_delay_ms)
        LOAD_SCORE.labels(worker_state.worker_id).set(worker_state.current_load_score())
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_fault_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="worker-service", version="0.1.0", lifespan=lifespan)


def _compute_processing_delay(payload_size: int, work_units: int) -> float:
    base_delay_ms = 5
    payload_delay_ms = payload_size * 0.15
    work_delay_ms = work_units * 4.5
    fault_delay_ms = worker_state.active_delay_ms()
    return base_delay_ms + payload_delay_ms + work_delay_ms + fault_delay_ms


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "worker_id": worker_state.worker_id,
        "fault_state": {
            "artificial_delay_ms": worker_state.active_delay_ms(),
        },
        "inflight_requests": worker_state.inflight_requests,
        "queue_depth": worker_state.current_queue_depth(),
        "load_score": worker_state.current_load_score(),
    }


@app.post("/work", response_model=WorkResponse)
async def work(payload: WorkRequest) -> WorkResponse:
    request_id = payload.request_id or str(uuid.uuid4())
    started_at = time.perf_counter()

    async with worker_state.lock:
        worker_state.inflight_requests += 1
        worker_state.total_work_units += payload.work_units
        current_queue_depth = worker_state.current_queue_depth()
        INFLIGHT_REQUESTS.labels(worker_state.worker_id).set(worker_state.inflight_requests)
        QUEUE_DEPTH.labels(worker_state.worker_id).set(current_queue_depth)
        LOAD_SCORE.labels(worker_state.worker_id).set(worker_state.current_load_score())

    processing_delay_ms = _compute_processing_delay(payload.payload_size, payload.work_units)
    await asyncio.sleep(processing_delay_ms / 1000.0)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
    REQUEST_COUNT.labels(worker_state.worker_id).inc()
    PROCESSING_LATENCY.labels(worker_state.worker_id).observe(elapsed_ms)

    async with worker_state.lock:
        worker_state.inflight_requests -= 1
        worker_state.total_work_units -= payload.work_units
        current_queue_depth = worker_state.current_queue_depth()
        INFLIGHT_REQUESTS.labels(worker_state.worker_id).set(worker_state.inflight_requests)
        QUEUE_DEPTH.labels(worker_state.worker_id).set(current_queue_depth)
        LOAD_SCORE.labels(worker_state.worker_id).set(worker_state.current_load_score())

    return WorkResponse(
        request_id=request_id,
        worker_id=worker_state.worker_id,
        processing_time_ms=elapsed_ms,
        queue_depth=current_queue_depth,
    )


@app.post("/faults/latency")
async def inject_latency_fault(payload: LatencyFaultRequest) -> dict:
    worker_state.fault_state = FaultState(
        artificial_delay_ms=payload.delay_ms,
        expires_at_monotonic=time.monotonic() + payload.duration_seconds,
    )
    FAULT_DELAY.labels(worker_state.worker_id).set(payload.delay_ms)
    LOAD_SCORE.labels(worker_state.worker_id).set(worker_state.current_load_score())
    return {
        "status": "fault_applied",
        "delay_ms": payload.delay_ms,
        "duration_seconds": payload.duration_seconds,
    }


@app.post("/faults/clear")
async def clear_faults() -> dict:
    worker_state.fault_state = FaultState()
    FAULT_DELAY.labels(worker_state.worker_id).set(0)
    LOAD_SCORE.labels(worker_state.worker_id).set(worker_state.current_load_score())
    return {"status": "fault_cleared"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
