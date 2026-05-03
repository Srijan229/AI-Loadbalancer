import asyncio
import os
from contextlib import asynccontextmanager
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


def _strip_url(value: str) -> str:
    return value.strip().rstrip("/")


def _load_urls(env_name: str, default: str) -> list[str]:
    raw_value = os.getenv(env_name, default)
    values = [_strip_url(value) for value in raw_value.split(",") if value.strip()]
    if not values:
        raise ValueError(f"{env_name} must contain at least one URL.")
    return values


def _worker_id_from_url(worker_url: str) -> str:
    parsed = urlparse(worker_url)
    return parsed.hostname or worker_url.rsplit("/", maxsplit=1)[-1]


class ModeUpdateRequest(BaseModel):
    mode: str


class LatencyFaultRequest(BaseModel):
    delay_ms: int = Field(..., ge=0, le=60_000)
    duration_seconds: int = Field(..., ge=1, le=3_600)


class StrategicPreviewRequest(BaseModel):
    target_start_utc: datetime
    interval_count: int = Field(default=4, ge=1, le=96)
    is_sale_day: bool | None = None
    event_type: str | None = None


class TimeAdvanceRequest(BaseModel):
    days: int = 0
    hours: int = 0
    minutes: int = 0


class TimePresetRequest(BaseModel):
    preset: str


class DashboardState:
    def __init__(self) -> None:
        self.gateway_url = _strip_url(os.getenv("GATEWAY_URL", "http://gateway:8001"))
        self.orchestrator_url = _strip_url(os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8002"))
        self.metrics_collector_url = _strip_url(
            os.getenv("METRICS_COLLECTOR_URL", "http://metrics-collector:8004")
        )
        self.predictor_url = _strip_url(os.getenv("PREDICTOR_URL", "http://predictor:8003"))
        self.time_controller_url = _strip_url(os.getenv("TIME_CONTROLLER_URL", "http://time-controller:8006"))
        self.worker_urls = _load_urls("WORKER_URLS", "http://worker-a:8000,http://worker-b:8000")
        self.worker_urls_by_id = {_worker_id_from_url(worker_url): worker_url for worker_url in self.worker_urls}
        self.client: httpx.AsyncClient | None = None
        self.overview: dict[str, Any] | None = None
        self.history: deque[dict[str, Any]] = deque(maxlen=int(os.getenv("DASHBOARD_HISTORY_LIMIT", "120")))
        self.lock = asyncio.Lock()
        self.refresh_task: asyncio.Task | None = None
        self.refresh_seconds = float(os.getenv("DASHBOARD_REFRESH_SECONDS", "2"))
        self.pending_time_event: dict[str, Any] | None = None

    def _queue_time_event(self, action: str, label: str, payload: dict[str, Any]) -> None:
        self.pending_time_event = {
            "action": action,
            "label": label,
            "payload": payload,
            "recorded_at": datetime.now(UTC).isoformat(),
        }

    async def gather_overview(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")

        (
            gateway_health,
            orchestrator_health,
            collector_snapshot,
            predictor_snapshot,
            policy_snapshot,
            time_snapshot,
        ) = await self._fetch_all()

        prediction_by_worker = {
            worker.get("worker_id"): worker for worker in predictor_snapshot.get("workers", []) if worker.get("worker_id")
        }
        policy_by_worker = {
            worker.get("worker_id"): worker for worker in policy_snapshot.get("workers", []) if worker.get("worker_id")
        }

        workers: list[dict[str, Any]] = []
        for worker in collector_snapshot.get("workers", []):
            worker_id = worker.get("worker_id")
            prediction = prediction_by_worker.get(worker_id, {})
            policy = policy_by_worker.get(worker_id, {})
            workers.append(
                {
                    "worker_id": worker_id,
                    "worker_url": worker.get("worker_url"),
                    "healthy": worker.get("healthy"),
                    "inflight_requests": worker.get("inflight_requests"),
                    "queue_depth": worker.get("queue_depth"),
                    "load_score": worker.get("load_score"),
                    "artificial_delay_ms": worker.get("artificial_delay_ms"),
                    "predicted_pressure": prediction.get("predicted_pressure"),
                    "current_load_score": prediction.get("current_load_score"),
                    "policy_weight": policy.get("weight"),
                    "policy_reason": policy.get("reason"),
                }
            )

        return {
            "generated_at": collector_snapshot.get("generated_at"),
            "dashboard_recorded_at": datetime.now(UTC).isoformat(),
            "services": {
                "gateway": gateway_health,
                "orchestrator": orchestrator_health,
                "metrics_collector": {
                    "status": "ok",
                    "service": "metrics-collector",
                    "generated_at": collector_snapshot.get("generated_at"),
                },
                "predictor": {
                    "status": "ok",
                    "service": "predictor",
                    "generated_at": predictor_snapshot.get("generated_at"),
                },
            },
            "control_plane": {
                "mode": orchestrator_health.get("mode"),
                "policy_version": orchestrator_health.get("policy_version"),
                "policy_generated_at": policy_snapshot.get("generated_at"),
                "effective_time_utc": policy_snapshot.get("effective_time_utc"),
                "policy_workers": policy_snapshot.get("workers", []),
                "strategic_forecast": policy_snapshot.get("strategic_forecast"),
                "scale_recommendation": policy_snapshot.get("scale_recommendation"),
                "time": time_snapshot,
            },
            "data_plane": {
                "gateway_mode": gateway_health.get("mode"),
                "policy_source": gateway_health.get("policy_source"),
                "worker_inflight": gateway_health.get("worker_inflight", {}),
            },
            "summary": {
                **collector_snapshot.get("summary", {}),
                **predictor_snapshot.get("summary", {}),
                "strategic_avg_expected_rps": (policy_snapshot.get("strategic_forecast") or {}).get("avg_expected_rps"),
                "strategic_peak_expected_rps": (policy_snapshot.get("strategic_forecast") or {}).get("peak_expected_rps"),
                "strategic_target_workers": (policy_snapshot.get("scale_recommendation") or {}).get("target_workers"),
            },
            "workers": workers,
        }

    async def refresh_overview(self) -> dict[str, Any] | None:
        try:
            overview = await self.gather_overview()
        except HTTPException:
            return None
        async with self.lock:
            if self.pending_time_event is not None:
                overview["time_event"] = self.pending_time_event
                self.pending_time_event = None
            self.overview = overview
            self.history.append(overview)
        return overview

    async def read_overview(self) -> dict[str, Any] | None:
        async with self.lock:
            return self.overview

    async def read_history(self) -> list[dict[str, Any]]:
        async with self.lock:
            return list(self.history)

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        assert self.client is not None
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def _fetch_all(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        assert self.client is not None
        try:
            (
                gateway_health,
                orchestrator_health,
                collector_snapshot,
                predictor_snapshot,
                policy_snapshot,
                time_snapshot,
            ) = await asyncio.gather(
                self._fetch_json(f"{self.gateway_url}/health"),
                self._fetch_json(f"{self.orchestrator_url}/health"),
                self._fetch_json(f"{self.metrics_collector_url}/snapshot"),
                self._fetch_json(f"{self.predictor_url}/predictions"),
                self._fetch_json(f"{self.orchestrator_url}/policy"),
                self._fetch_json(f"{self.time_controller_url}/time"),
            )
            return (
                gateway_health,
                orchestrator_health,
                collector_snapshot,
                predictor_snapshot,
                policy_snapshot,
                time_snapshot,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Dashboard dependency fetch failed: {exc}") from exc

    async def update_mode(self, mode: str) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.post(f"{self.orchestrator_url}/mode", json={"mode": mode})
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    async def fetch_recommendations(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.get(f"{self.orchestrator_url}/recommendations")
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    async def preview_recommendations(self, payload: StrategicPreviewRequest) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.post(
            f"{self.orchestrator_url}/recommendations/preview",
            json=payload.model_dump(mode="json"),
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    async def fetch_time(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.get(f"{self.time_controller_url}/time")
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    async def fetch_time_presets(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.get(f"{self.time_controller_url}/presets")
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    async def freeze_time(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.post(f"{self.time_controller_url}/time/freeze")
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        payload = response.json()
        self._queue_time_event("freeze", "Freeze Time", payload)
        return payload

    async def resume_time(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.post(f"{self.time_controller_url}/time/resume")
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        payload = response.json()
        self._queue_time_event("resume", "Resume Realtime", payload)
        return payload

    async def advance_time(self, payload: TimeAdvanceRequest) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.post(
            f"{self.time_controller_url}/time/advance",
            json=payload.model_dump(),
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        response_payload = response.json()
        advance_label_parts: list[str] = []
        if payload.days:
            advance_label_parts.append(f"{payload.days}d")
        if payload.hours:
            advance_label_parts.append(f"{payload.hours}h")
        if payload.minutes:
            advance_label_parts.append(f"{payload.minutes}m")
        advance_label = " ".join(advance_label_parts) or "0m"
        self._queue_time_event("advance", f"Advance {advance_label}", response_payload)
        return response_payload

    async def apply_time_preset(self, payload: TimePresetRequest) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Dashboard HTTP client is not initialized.")
        response = await self.client.post(
            f"{self.time_controller_url}/time/preset",
            json=payload.model_dump(),
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        response_payload = response.json()
        preset_label = payload.preset.replace("_", " ").title()
        self._queue_time_event("preset", f"Jump {preset_label}", response_payload)
        return response_payload

    async def inject_worker_latency(self, worker_id: str, payload: LatencyFaultRequest) -> dict[str, Any]:
        worker_url = self.worker_urls_by_id.get(worker_id)
        if worker_url is None:
            raise HTTPException(status_code=404, detail=f"Unknown worker '{worker_id}'.")
        assert self.client is not None
        response = await self.client.post(f"{worker_url}/faults/latency", json=payload.model_dump())
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()

    async def clear_worker_faults(self, worker_id: str) -> dict[str, Any]:
        worker_url = self.worker_urls_by_id.get(worker_id)
        if worker_url is None:
            raise HTTPException(status_code=404, detail=f"Unknown worker '{worker_id}'.")
        assert self.client is not None
        response = await self.client.post(f"{worker_url}/faults/clear")
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()


state = DashboardState()
STATIC_DIR = Path(__file__).parent / "static"


async def _background_refresh_loop() -> None:
    while True:
        await state.refresh_overview()
        await asyncio.sleep(state.refresh_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.client = httpx.AsyncClient(timeout=5.0)
    await state.refresh_overview()
    state.refresh_task = asyncio.create_task(_background_refresh_loop())
    try:
        yield
    finally:
        if state.refresh_task is not None:
            state.refresh_task.cancel()
            try:
                await state.refresh_task
            except asyncio.CancelledError:
                pass
            state.refresh_task = None
        if state.client is not None:
            await state.client.aclose()
            state.client = None


app = FastAPI(title="dashboard-service", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "dashboard",
        "gateway_url": state.gateway_url,
        "orchestrator_url": state.orchestrator_url,
        "metrics_collector_url": state.metrics_collector_url,
        "predictor_url": state.predictor_url,
        "time_controller_url": state.time_controller_url,
        "worker_ids": sorted(state.worker_urls_by_id),
    }


@app.get("/api/overview")
async def overview() -> dict[str, Any]:
    snapshot = await state.read_overview()
    if snapshot is not None:
        return snapshot
    fresh_snapshot = await state.refresh_overview()
    if fresh_snapshot is None:
        raise HTTPException(status_code=502, detail="Dashboard overview is unavailable.")
    return fresh_snapshot


@app.get("/api/history")
async def history() -> dict[str, Any]:
    snapshots = await state.read_history()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "points": snapshots,
    }


@app.post("/api/mode")
async def set_mode(payload: ModeUpdateRequest) -> dict[str, Any]:
    return await state.update_mode(payload.mode)


@app.get("/api/recommendations")
async def recommendations() -> dict[str, Any]:
    return await state.fetch_recommendations()


@app.get("/api/time")
async def get_time() -> dict[str, Any]:
    return await state.fetch_time()


@app.get("/api/time/presets")
async def get_time_presets() -> dict[str, Any]:
    return await state.fetch_time_presets()


@app.post("/api/time/freeze")
async def freeze_time() -> dict[str, Any]:
    return await state.freeze_time()


@app.post("/api/time/resume")
async def resume_time() -> dict[str, Any]:
    return await state.resume_time()


@app.post("/api/time/advance")
async def advance_time(payload: TimeAdvanceRequest) -> dict[str, Any]:
    return await state.advance_time(payload)


@app.post("/api/time/preset")
async def apply_time_preset(payload: TimePresetRequest) -> dict[str, Any]:
    return await state.apply_time_preset(payload)


@app.post("/api/recommendations/preview")
async def preview_recommendations(payload: StrategicPreviewRequest) -> dict[str, Any]:
    return await state.preview_recommendations(payload)


@app.post("/api/workers/{worker_id}/faults/latency")
async def inject_latency(worker_id: str, payload: LatencyFaultRequest) -> dict[str, Any]:
    return await state.inject_worker_latency(worker_id, payload)


@app.post("/api/workers/{worker_id}/faults/clear")
async def clear_faults(worker_id: str) -> dict[str, Any]:
    return await state.clear_worker_faults(worker_id)
