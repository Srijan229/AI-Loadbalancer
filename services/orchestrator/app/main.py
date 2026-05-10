import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from starlette.responses import Response


SUPPORTED_MODES = {"round_robin", "least_connections", "predictive"}
STRATEGIC_INTERVALS = int(os.getenv("STRATEGIC_FORECAST_INTERVALS", "4"))
PREDICTIVE_WEIGHT_SMOOTHING = float(os.getenv("PREDICTIVE_WEIGHT_SMOOTHING", "0.35"))
PREDICTIVE_WEIGHT_HYSTERESIS = float(os.getenv("PREDICTIVE_WEIGHT_HYSTERESIS", "0.08"))
PREDICTIVE_MAX_WEIGHT_STEP = float(os.getenv("PREDICTIVE_MAX_WEIGHT_STEP", "0.18"))
PREDICTIVE_MIN_HEALTHY_WEIGHT = float(os.getenv("PREDICTIVE_MIN_HEALTHY_WEIGHT", "0.2"))
PREDICTIVE_MAX_HEALTHY_WEIGHT = float(os.getenv("PREDICTIVE_MAX_HEALTHY_WEIGHT", "0.65"))
PREDICTIVE_WEIGHT_QUANTIZATION = float(os.getenv("PREDICTIVE_WEIGHT_QUANTIZATION", "0.05"))
PREDICTIVE_REBALANCE_INTERVAL_SECONDS = float(os.getenv("PREDICTIVE_REBALANCE_INTERVAL_SECONDS", "6"))
PREDICTIVE_EMERGENCY_DELTA = float(os.getenv("PREDICTIVE_EMERGENCY_DELTA", "0.22"))


class ModeUpdateRequest(BaseModel):
    mode: str


class WorkerPolicy(BaseModel):
    worker_id: str
    worker_url: str
    weight: float
    healthy: bool
    reason: str


class HistoricalForecastRequest(BaseModel):
    target_start_utc: datetime
    interval_count: int = Field(default=STRATEGIC_INTERVALS, ge=1, le=96)
    is_sale_day: bool | None = None
    event_type: str | None = None


class OrchestratorState:
    def __init__(self) -> None:
        self.mode = os.getenv("DEFAULT_MODE", "round_robin")
        self.policy_version = 1
        self.worker_urls = self._load_worker_urls()
        self.metrics_collector_url = os.getenv("METRICS_COLLECTOR_URL", "").strip().rstrip("/")
        self.predictor_url = os.getenv("PREDICTOR_URL", "").strip().rstrip("/")
        self.historical_forecaster_url = os.getenv("HISTORICAL_FORECASTER_URL", "").strip().rstrip("/")
        self.time_controller_url = os.getenv("TIME_CONTROLLER_URL", "").strip().rstrip("/")
        self.previous_predictive_weights = {worker_url: 1.0 / len(self.worker_urls) for worker_url in self.worker_urls}
        self.last_predictive_rebalance_at = 0.0
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

    async def build_policy(self) -> dict:
        collector_snapshot = await self.fetch_collector_snapshot()
        prediction_snapshot = await self.fetch_prediction_snapshot()
        effective_time = await self.fetch_effective_time()
        strategic_forecast = await self.fetch_historical_forecast(target_time=effective_time)
        strategic_summary = self._summarize_strategic_forecast(strategic_forecast)
        workers = self._build_workers(collector_snapshot, prediction_snapshot, strategic_summary)
        return {
            "mode": self.mode,
            "version": self.policy_version,
            "generated_at": datetime.now(UTC).isoformat(),
            "effective_time_utc": effective_time.isoformat(),
            "workers": workers,
            "strategic_forecast": strategic_summary,
            "scale_recommendation": self._build_scale_recommendation(strategic_summary),
        }

    def _build_workers(
        self,
        collector_snapshot: dict[str, Any] | None,
        prediction_snapshot: dict[str, Any] | None,
        strategic_summary: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        collector_workers_by_url = {
            worker.get("worker_url"): worker
            for worker in (collector_snapshot or {}).get("workers", [])
            if worker.get("worker_url")
        }
        prediction_workers_by_id = {
            worker.get("worker_id"): worker
            for worker in (prediction_snapshot or {}).get("workers", [])
            if worker.get("worker_id")
        }
        worker_records: list[dict[str, Any]] = []
        for worker_url in self.worker_urls:
            collector_worker = collector_workers_by_url.get(worker_url, {})
            worker_id = collector_worker.get("worker_id", worker_url.rsplit("/", maxsplit=1)[-1])
            prediction_worker = prediction_workers_by_id.get(worker_id, {})
            worker_records.append(
                {
                    "worker_id": worker_id,
                    "worker_url": worker_url,
                    "healthy": collector_worker.get("healthy", True),
                    "load_score": collector_worker.get("load_score", 0.0),
                    "predicted_pressure": prediction_worker.get("predicted_pressure"),
                }
            )

        healthy_workers = [worker for worker in worker_records if worker["healthy"]]
        if not healthy_workers:
            healthy_workers = worker_records

        stabilized_weights: dict[str, float] = {}
        if self.mode == "predictive":
            strategic_bias = self._strategic_bias(strategic_summary)
            inverse_pressures: dict[str, float] = {}
            for worker in healthy_workers:
                predicted_pressure = float(worker["predicted_pressure"] or worker["load_score"] or 0.0)
                adjusted_pressure = max(predicted_pressure, 0.1) * strategic_bias
                inverse_pressures[worker["worker_url"]] = 1.0 / adjusted_pressure
            total_inverse_pressure = sum(inverse_pressures.values()) or float(len(healthy_workers))
            target_weights = {
                worker["worker_url"]: inverse_pressures[worker["worker_url"]] / total_inverse_pressure
                for worker in healthy_workers
            }
            stabilized_weights = self._stabilize_predictive_weights(target_weights, healthy_workers)
        else:
            total_inverse_pressure = float(len(healthy_workers))
            self.previous_predictive_weights = {
                worker_url: (1.0 / len(self.worker_urls)) for worker_url in self.worker_urls
            }
            self.last_predictive_rebalance_at = 0.0

        workers: list[dict[str, Any]] = []
        healthy_worker_urls = {worker["worker_url"] for worker in healthy_workers}
        for worker in worker_records:
            worker_id = worker["worker_id"]
            worker_url = worker["worker_url"]
            healthy = worker_url in healthy_worker_urls
            if self.mode == "predictive" and healthy:
                weight = round(stabilized_weights[worker_url], 4)
                demand_level = (strategic_summary or {}).get("demand_level", "normal")
                if demand_level in {"elevated", "surge"}:
                    reason = f"predicted_pressure_weight_stabilized_{demand_level}_window"
                else:
                    reason = "predicted_pressure_weight_stabilized"
            elif healthy:
                weight = round(1.0 / total_inverse_pressure, 4)
                reason = "static_baseline_policy"
            else:
                weight = 0.0
                reason = "unhealthy_worker_excluded"
            workers.append(
                WorkerPolicy(
                    worker_id=worker_id,
                    worker_url=worker_url,
                    weight=weight,
                    healthy=healthy,
                    reason=reason,
                ).model_dump()
            )
        return workers

    def _stabilize_predictive_weights(
        self,
        target_weights: dict[str, float],
        healthy_workers: list[dict[str, Any]],
    ) -> dict[str, float]:
        healthy_worker_urls = [worker["worker_url"] for worker in healthy_workers]
        healthy_count = len(healthy_worker_urls)
        if healthy_count == 0:
            return {worker_url: 0.0 for worker_url in self.worker_urls}

        min_weight = min(PREDICTIVE_MIN_HEALTHY_WEIGHT, 1.0 / healthy_count)
        max_weight = max(min(PREDICTIVE_MAX_HEALTHY_WEIGHT, 1.0), min_weight)
        previous_weights = {
            worker_url: self.previous_predictive_weights.get(worker_url, 1.0 / healthy_count)
            for worker_url in healthy_worker_urls
        }
        max_target_delta = max(
            abs(target_weights.get(worker_url, previous_weights[worker_url]) - previous_weights[worker_url])
            for worker_url in healthy_worker_urls
        )
        now = time.monotonic()
        if (
            self.last_predictive_rebalance_at > 0
            and (now - self.last_predictive_rebalance_at) < PREDICTIVE_REBALANCE_INTERVAL_SECONDS
            and max_target_delta < PREDICTIVE_EMERGENCY_DELTA
        ):
            return previous_weights

        stabilized: dict[str, float] = {}

        for worker_url in healthy_worker_urls:
            previous = previous_weights[worker_url]
            target = target_weights.get(worker_url, previous)
            smoothed = previous + ((target - previous) * PREDICTIVE_WEIGHT_SMOOTHING)
            delta = smoothed - previous
            if abs(target - previous) < PREDICTIVE_WEIGHT_HYSTERESIS:
                smoothed = previous
            elif abs(delta) > PREDICTIVE_MAX_WEIGHT_STEP:
                smoothed = previous + (PREDICTIVE_MAX_WEIGHT_STEP if delta > 0 else -PREDICTIVE_MAX_WEIGHT_STEP)
            stabilized[worker_url] = min(max(smoothed, min_weight), max_weight)

        total = sum(stabilized.values()) or float(healthy_count)
        normalized = {
            worker_url: stabilized[worker_url] / total
            for worker_url in healthy_worker_urls
        }
        quantized = self._quantize_weights(normalized, healthy_worker_urls, min_weight, max_weight)

        self.previous_predictive_weights = {
            worker_url: quantized.get(worker_url, 0.0)
            for worker_url in self.worker_urls
        }
        self.last_predictive_rebalance_at = now
        return quantized

    def _quantize_weights(
        self,
        weights: dict[str, float],
        healthy_worker_urls: list[str],
        min_weight: float,
        max_weight: float,
    ) -> dict[str, float]:
        if PREDICTIVE_WEIGHT_QUANTIZATION <= 0:
            return weights

        quantized = {
            worker_url: round(weights[worker_url] / PREDICTIVE_WEIGHT_QUANTIZATION) * PREDICTIVE_WEIGHT_QUANTIZATION
            for worker_url in healthy_worker_urls
        }
        quantized = {
            worker_url: min(max(weight, min_weight), max_weight)
            for worker_url, weight in quantized.items()
        }
        total = sum(quantized.values()) or float(len(healthy_worker_urls))
        normalized = {
            worker_url: quantized[worker_url] / total
            for worker_url in healthy_worker_urls
        }
        return normalized

    async def fetch_collector_snapshot(self) -> dict[str, Any] | None:
        if not self.metrics_collector_url or self.client is None:
            return None
        try:
            response = await self.client.get(f"{self.metrics_collector_url}/snapshot")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    async def fetch_prediction_snapshot(self) -> dict[str, Any] | None:
        if not self.predictor_url or self.client is None:
            return None
        try:
            response = await self.client.get(f"{self.predictor_url}/predictions")
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    async def fetch_effective_time(self) -> datetime:
        if not self.time_controller_url or self.client is None:
            return datetime.now(UTC)
        try:
            response = await self.client.get(f"{self.time_controller_url}/time")
            response.raise_for_status()
            payload = response.json()
            simulated_time = payload.get("simulated_time_utc")
            if simulated_time:
                return datetime.fromisoformat(simulated_time)
        except Exception:
            pass
        return datetime.now(UTC)

    async def fetch_historical_forecast(
        self,
        payload: HistoricalForecastRequest | None = None,
        target_time: datetime | None = None,
    ) -> dict[str, Any] | None:
        if not self.historical_forecaster_url or self.client is None:
            return None
        try:
            payload = payload or HistoricalForecastRequest(
                target_start_utc=target_time or datetime.now(UTC),
                interval_count=STRATEGIC_INTERVALS,
            )
            response = await self.client.post(
                f"{self.historical_forecaster_url}/forecast",
                json=payload.model_dump(mode="json"),
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _summarize_strategic_forecast(self, strategic_forecast: dict[str, Any] | None) -> dict[str, Any] | None:
        if not strategic_forecast:
            return None
        forecasts = strategic_forecast.get("forecasts", [])
        if not forecasts:
            return None

        expected_rps = [float(entry.get("expected_rps", 0.0)) for entry in forecasts]
        recommended_workers = [int(entry.get("recommended_workers", 2)) for entry in forecasts]
        peak_rps = max(expected_rps, default=0.0)
        avg_rps = round(sum(expected_rps) / max(len(expected_rps), 1), 3)
        peak_workers = max(recommended_workers, default=2)

        if peak_rps >= 85:
            demand_level = "surge"
        elif peak_rps >= 55:
            demand_level = "elevated"
        else:
            demand_level = "normal"

        return {
            "generated_at": strategic_forecast.get("generated_at"),
            "window_intervals": len(forecasts),
            "avg_expected_rps": avg_rps,
            "peak_expected_rps": round(peak_rps, 3),
            "peak_recommended_workers": peak_workers,
            "demand_level": demand_level,
            "matched_strategies": sorted({entry.get("matched_strategy", "unknown") for entry in forecasts}),
            "event_types": sorted({entry.get("context", {}).get("event_type", "none") for entry in forecasts}),
        }

    def _build_scale_recommendation(self, strategic_summary: dict[str, Any] | None) -> dict[str, Any] | None:
        if not strategic_summary:
            return None
        current_workers = len(self.worker_urls)
        target_workers = max(current_workers, int(strategic_summary["peak_recommended_workers"]))
        action = "hold"
        if target_workers > current_workers:
            action = "pre_scale_up"
        elif strategic_summary.get("demand_level") == "normal" and current_workers > 2:
            action = "hold"
        return {
            "action": action,
            "current_workers": current_workers,
            "target_workers": target_workers,
            "demand_level": strategic_summary.get("demand_level"),
            "avg_expected_rps": strategic_summary.get("avg_expected_rps"),
            "peak_expected_rps": strategic_summary.get("peak_expected_rps"),
        }

    def _strategic_bias(self, strategic_summary: dict[str, Any] | None) -> float:
        if not strategic_summary:
            return 1.0
        demand_level = strategic_summary.get("demand_level")
        if demand_level == "surge":
            return 1.6
        if demand_level == "elevated":
            return 1.25
        return 1.0


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
STRATEGIC_PEAK_RPS = Gauge(
    "orchestrator_strategic_peak_expected_rps",
    "Peak expected RPS from the long-horizon strategic forecast.",
)
STRATEGIC_TARGET_WORKERS = Gauge(
    "orchestrator_strategic_target_workers",
    "Target workers recommended by long-horizon strategic forecast.",
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
    effective_time = await state.fetch_effective_time()
    strategic_forecast = await state.fetch_historical_forecast(target_time=effective_time)
    strategic_summary = state._summarize_strategic_forecast(strategic_forecast)
    if strategic_summary:
        STRATEGIC_PEAK_RPS.set(strategic_summary["peak_expected_rps"])
        STRATEGIC_TARGET_WORKERS.set(strategic_summary["peak_recommended_workers"])
    return {
        "status": "ok",
        "service": "orchestrator",
        "mode": state.mode,
        "policy_version": state.policy_version,
        "configured_workers": state.worker_urls,
        "metrics_collector_url": state.metrics_collector_url or None,
        "predictor_url": state.predictor_url or None,
        "historical_forecaster_url": state.historical_forecaster_url or None,
        "time_controller_url": state.time_controller_url or None,
        "effective_time_utc": effective_time.isoformat(),
        "strategic_forecast": strategic_summary,
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
    policy_snapshot = await state.build_policy()
    strategic_summary = policy_snapshot.get("strategic_forecast")
    if strategic_summary:
        STRATEGIC_PEAK_RPS.set(strategic_summary["peak_expected_rps"])
        STRATEGIC_TARGET_WORKERS.set(strategic_summary["peak_recommended_workers"])
    return policy_snapshot


@app.get("/recommendations")
async def recommendations() -> dict:
    effective_time = await state.fetch_effective_time()
    strategic_forecast = await state.fetch_historical_forecast(target_time=effective_time)
    strategic_summary = state._summarize_strategic_forecast(strategic_forecast)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "effective_time_utc": effective_time.isoformat(),
        "strategic_forecast": strategic_summary,
        "scale_recommendation": state._build_scale_recommendation(strategic_summary),
    }


@app.post("/recommendations/preview")
async def preview_recommendations(payload: HistoricalForecastRequest) -> dict:
    strategic_forecast = await state.fetch_historical_forecast(payload)
    strategic_summary = state._summarize_strategic_forecast(strategic_forecast)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "preview_request": payload.model_dump(mode="json"),
        "strategic_forecast": strategic_summary,
        "scale_recommendation": state._build_scale_recommendation(strategic_summary),
        "raw_forecast": strategic_forecast,
    }


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
