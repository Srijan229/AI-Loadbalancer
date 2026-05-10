import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response


SUPPORTED_INFRA_MODES = {"simulate", "aws_execute"}


class InfraModeRequest(BaseModel):
    mode: str


class PendingPlan(BaseModel):
    generated_at: str
    recommendation: dict[str, Any] | None
    plan: dict[str, Any]


@dataclass
class PendingTransition:
    ready_at_monotonic: float
    target_current_instances: int
    action: str


class InfrastructureControllerState:
    def __init__(self) -> None:
        self.orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8002").strip().rstrip("/")
        self.mode = os.getenv("INFRA_MODE", "simulate").strip()
        if self.mode not in SUPPORTED_INFRA_MODES:
            self.mode = "simulate"

        self.provider = os.getenv("INFRA_PROVIDER", "aws").strip() or "aws"
        self.resource_type = "autoscaling-group"
        self.group_name = os.getenv("INFRA_GROUP_NAME", "ai-loadbalancer-workers").strip() or "ai-loadbalancer-workers"
        self.min_instances = int(os.getenv("INFRA_MIN_INSTANCES", "1"))
        self.max_instances = int(os.getenv("INFRA_MAX_INSTANCES", "5"))
        self.current_instances = int(os.getenv("INFRA_CURRENT_INSTANCES", "2"))
        self.desired_instances = self.current_instances
        self.cooldown_seconds = int(os.getenv("INFRA_COOLDOWN_SECONDS", "45"))
        self.provision_seconds = int(os.getenv("INFRA_PROVISION_SECONDS", "30"))
        self.max_scale_step = int(os.getenv("INFRA_MAX_SCALE_STEP", "1"))
        self.cooldown_until_monotonic = 0.0
        self.last_action: str = "hold"
        self.last_recommendation: dict[str, Any] | None = None
        self.pending_plan: dict[str, Any] | None = None
        self.pending_transitions: list[PendingTransition] = []
        self.action_history: list[dict[str, Any]] = []
        self.client: httpx.AsyncClient | None = None
        self.lock = asyncio.Lock()

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def _advance_state_locked(self) -> None:
        now = asyncio.get_running_loop().time()
        remaining: list[PendingTransition] = []
        transitioned = False
        for transition in self.pending_transitions:
            if now >= transition.ready_at_monotonic:
                self.current_instances = transition.target_current_instances
                self.last_action = f"{transition.action}_applied"
                transitioned = True
            else:
                remaining.append(transition)
        self.pending_transitions = remaining
        if transitioned and not self.pending_transitions:
            self.last_action = "stable"

    def _cooldown_remaining_locked(self) -> float:
        now = asyncio.get_running_loop().time()
        return max(self.cooldown_until_monotonic - now, 0.0)

    def _pending_instances_locked(self) -> int:
        return max(self.desired_instances - self.current_instances, 0)

    def _scale_down_pending_locked(self) -> int:
        return max(self.current_instances - self.desired_instances, 0)

    def _snapshot_locked(self) -> dict[str, Any]:
        self._advance_state_locked()
        cooldown_remaining = self._cooldown_remaining_locked()
        return {
            "status": "ok",
            "service": "infrastructure-controller",
            "mode": self.mode,
            "provider": self.provider,
            "resource_type": self.resource_type,
            "group_name": self.group_name,
            "current_instances": self.current_instances,
            "desired_instances": self.desired_instances,
            "pending_instances": self._pending_instances_locked(),
            "pending_scale_down": self._scale_down_pending_locked(),
            "min_instances": self.min_instances,
            "max_instances": self.max_instances,
            "cooldown_seconds": self.cooldown_seconds,
            "cooldown_remaining_seconds": round(cooldown_remaining, 1),
            "cooldown_active": cooldown_remaining > 0,
            "last_action": self.last_action,
            "last_recommendation": self.last_recommendation,
            "pending_plan": self.pending_plan,
            "generated_at": self._now_iso(),
        }

    async def fetch_recommendation(self) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Infrastructure controller HTTP client is not initialized.")
        response = await self.client.get(f"{self.orchestrator_url}/recommendations")
        response.raise_for_status()
        return response.json()

    def _build_plan_locked(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        scale_recommendation = recommendation.get("scale_recommendation") or {}
        current_desired = self.desired_instances
        target_instances = int(scale_recommendation.get("target_workers") or current_desired)
        bounded_target = max(self.min_instances, min(self.max_instances, target_instances))
        delta = bounded_target - current_desired
        cooldown_remaining = self._cooldown_remaining_locked()
        recommendation_action = scale_recommendation.get("action") or "hold"

        plan_action = "hold"
        execute_target = current_desired
        blocked_reason = None

        if self.mode == "aws_execute":
            blocked_reason = "aws_execute_not_configured"
        elif cooldown_remaining > 0 and delta != 0:
            plan_action = "cooldown_hold"
            blocked_reason = "cooldown_active"
        elif delta > 0:
            step = min(delta, self.max_scale_step)
            execute_target = current_desired + step
            plan_action = "pre_scale_up" if recommendation_action == "pre_scale_up" else "scale_up"
        elif delta < 0:
            step = min(abs(delta), self.max_scale_step)
            execute_target = current_desired - step
            plan_action = "scale_down"

        return {
            "action": plan_action,
            "recommended_action": recommendation_action,
            "current_instances": self.current_instances,
            "current_desired_instances": current_desired,
            "target_instances": bounded_target,
            "execute_target_instances": execute_target,
            "delta": delta,
            "blocked_reason": blocked_reason,
            "demand_level": scale_recommendation.get("demand_level"),
            "avg_expected_rps": scale_recommendation.get("avg_expected_rps"),
            "peak_expected_rps": scale_recommendation.get("peak_expected_rps"),
        }

    async def read_state(self) -> dict[str, Any]:
        async with self.lock:
            return self._snapshot_locked()

    async def read_actions(self) -> dict[str, Any]:
        async with self.lock:
            return {
                "generated_at": self._now_iso(),
                "count": len(self.action_history),
                "actions": list(self.action_history),
            }

    async def update_mode(self, mode: str) -> dict[str, Any]:
        if mode not in SUPPORTED_INFRA_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported infrastructure mode '{mode}'. Supported modes: {sorted(SUPPORTED_INFRA_MODES)}.",
            )
        async with self.lock:
            self.mode = mode
            self.last_action = "mode_updated"
            snapshot = self._snapshot_locked()
        return snapshot

    async def sync(self) -> dict[str, Any]:
        try:
            recommendation = await self.fetch_recommendation()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch orchestrator recommendation: {exc}") from exc

        async with self.lock:
            self._advance_state_locked()
            self.last_recommendation = recommendation
            plan = self._build_plan_locked(recommendation)
            self.pending_plan = PendingPlan(
                generated_at=self._now_iso(),
                recommendation=recommendation,
                plan=plan,
            ).model_dump()
            snapshot = self._snapshot_locked()
        return {
            "status": "synced",
            "recommendation": recommendation,
            "plan": plan,
            "state": snapshot,
        }

    async def execute(self) -> dict[str, Any]:
        async with self.lock:
            self._advance_state_locked()
            if not self.pending_plan:
                raise HTTPException(status_code=409, detail="No pending plan. Call /sync first.")

            plan = self.pending_plan.get("plan") or {}
            action = plan.get("action", "hold")
            if self.mode == "aws_execute":
                raise HTTPException(status_code=409, detail="aws_execute mode requires AWS credentials and is not enabled yet.")

            before_state = self._snapshot_locked()
            now = asyncio.get_running_loop().time()
            execute_target = int(plan.get("execute_target_instances") or self.desired_instances)

            if action in {"scale_up", "pre_scale_up", "scale_down"} and execute_target != self.desired_instances:
                self.desired_instances = execute_target
                self.cooldown_until_monotonic = now + self.cooldown_seconds
                self.pending_transitions.append(
                    PendingTransition(
                        ready_at_monotonic=now + self.provision_seconds,
                        target_current_instances=execute_target,
                        action=action,
                    )
                )
                self.last_action = action
            else:
                self.last_action = action

            record = {
                "timestamp": self._now_iso(),
                "mode": self.mode,
                "action": action,
                "before": before_state,
                "plan": plan,
                "after": self._snapshot_locked(),
            }
            self.action_history.append(record)
            self.action_history = self.action_history[-100:]
            self.pending_plan = None
            after_state = self._snapshot_locked()

        return {
            "status": "executed",
            "record": record,
            "state": after_state,
        }

    async def reset(self) -> dict[str, Any]:
        async with self.lock:
            self.desired_instances = max(self.min_instances, min(self.max_instances, self.current_instances))
            self.pending_transitions = []
            self.cooldown_until_monotonic = 0.0
            self.pending_plan = None
            self.last_action = "reset"
            self.action_history.append(
                {
                    "timestamp": self._now_iso(),
                    "mode": self.mode,
                    "action": "reset",
                    "after": self._snapshot_locked(),
                }
            )
            self.action_history = self.action_history[-100:]
            snapshot = self._snapshot_locked()
        return {
            "status": "reset",
            "state": snapshot,
        }


CURRENT_INSTANCES = Gauge(
    "infrastructure_current_instances",
    "Current worker instances in the simulated infrastructure group.",
)
DESIRED_INSTANCES = Gauge(
    "infrastructure_desired_instances",
    "Desired worker instances in the simulated infrastructure group.",
)
PENDING_INSTANCES = Gauge(
    "infrastructure_pending_instances",
    "Pending worker instances waiting to become active.",
)
COOLDOWN_REMAINING = Gauge(
    "infrastructure_cooldown_remaining_seconds",
    "Remaining cooldown before another scaling action is allowed.",
)


state = InfrastructureControllerState()


async def _metrics_refresh_loop() -> None:
    while True:
        snapshot = await state.read_state()
        CURRENT_INSTANCES.set(snapshot["current_instances"])
        DESIRED_INSTANCES.set(snapshot["desired_instances"])
        PENDING_INSTANCES.set(snapshot["pending_instances"])
        COOLDOWN_REMAINING.set(snapshot["cooldown_remaining_seconds"])
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.client = httpx.AsyncClient(timeout=5.0)
    metrics_task = asyncio.create_task(_metrics_refresh_loop())
    try:
        yield
    finally:
        metrics_task.cancel()
        try:
            await metrics_task
        except asyncio.CancelledError:
            pass
        if state.client is not None:
            await state.client.aclose()
            state.client = None


app = FastAPI(title="infrastructure-controller-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return await state.read_state()


@app.get("/state")
async def get_state() -> dict[str, Any]:
    return await state.read_state()


@app.get("/actions")
async def get_actions() -> dict[str, Any]:
    return await state.read_actions()


@app.post("/mode")
async def set_mode(payload: InfraModeRequest) -> dict[str, Any]:
    return await state.update_mode(payload.mode)


@app.post("/sync")
async def sync_recommendation() -> dict[str, Any]:
    return await state.sync()


@app.post("/execute")
async def execute_plan() -> dict[str, Any]:
    return await state.execute()


@app.post("/reset")
async def reset_state() -> dict[str, Any]:
    return await state.reset()


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
