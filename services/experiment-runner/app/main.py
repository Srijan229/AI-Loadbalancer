import asyncio
import csv
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


SUPPORTED_MODES = {"round_robin", "least_connections", "predictive_rules", "agentic"}
EXECUTABLE_MODE_MAP = {
    "round_robin": "round_robin",
    "least_connections": "least_connections",
    "predictive_rules": "predictive",
}


class RunCreateRequest(BaseModel):
    scenario_id: str
    mode: str


class BatchRunRequest(BaseModel):
    scenario_id: str
    modes: list[str]
    repeat_count: int = 2


def _strip_url(value: str) -> str:
    return value.strip().rstrip("/")


def _worker_id_from_url(worker_url: str) -> str:
    parsed = urlparse(worker_url)
    return parsed.hostname or worker_url.rsplit("/", maxsplit=1)[-1]


class ExperimentRunnerState:
    def __init__(self) -> None:
        self.root_dir = self._resolve_root_dir()
        self.scenarios_dir = self.root_dir / "data" / "experiments" / "scenarios"
        self.runs_dir = self.root_dir / "data" / "experiments" / "runs"
        self.comparisons_dir = self.root_dir / "data" / "experiments" / "comparisons"
        self.batches_dir = self.root_dir / "data" / "experiments" / "batches"
        self.dashboard_url = _strip_url(os.getenv("DASHBOARD_URL", "http://127.0.0.1:8510"))
        self.gateway_url = _strip_url(os.getenv("GATEWAY_URL", "http://127.0.0.1:8301"))
        self.orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://127.0.0.1:8302").strip().rstrip("/")
        self.time_controller_url = os.getenv("TIME_CONTROLLER_URL", "http://127.0.0.1:8606").strip().rstrip("/")
        self.worker_urls_by_id = self._load_worker_endpoints()
        self.client: httpx.AsyncClient | None = None
        self.sample_interval_seconds = float(os.getenv("RUN_SAMPLE_INTERVAL_SECONDS", "2"))
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.comparisons_dir.mkdir(parents=True, exist_ok=True)
        self.batches_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_root_dir() -> Path:
        explicit_root = os.getenv("PROJECT_ROOT", "").strip()
        if explicit_root:
            return Path(explicit_root).resolve()

        here = Path(__file__).resolve()
        candidates = [
            here.parents[3],  # repo checkout
            Path("/app"),     # container layout
        ]
        for candidate in candidates:
            if (candidate / "data" / "experiments" / "scenarios").exists():
                return candidate
        return here.parents[3]

    def list_scenarios(self) -> list[dict[str, Any]]:
        scenarios: list[dict[str, Any]] = []
        for scenario_path in sorted(self.scenarios_dir.glob("*.json")):
            with scenario_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            scenarios.append(payload)
        return scenarios

    def get_scenario(self, scenario_id: str) -> dict[str, Any]:
        scenario_path = self.scenarios_dir / f"{scenario_id}.json"
        if not scenario_path.exists():
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
        with scenario_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _load_worker_endpoints() -> dict[str, str]:
        endpoints = os.getenv("WORKER_ENDPOINTS", "").strip()
        if endpoints:
            mapping: dict[str, str] = {}
            for entry in endpoints.split(","):
                if "=" not in entry:
                    continue
                worker_id, worker_url = entry.split("=", maxsplit=1)
                mapping[worker_id.strip()] = _strip_url(worker_url)
            if mapping:
                return mapping

        worker_urls = os.getenv("WORKER_URLS", "http://127.0.0.1:8220,http://127.0.0.1:8221")
        mapping = {}
        for worker_url in worker_urls.split(","):
            worker_url = _strip_url(worker_url)
            if worker_url:
                mapping[_worker_id_from_url(worker_url)] = worker_url
        return mapping

    def create_run(self, payload: RunCreateRequest) -> dict[str, Any]:
        if payload.mode not in SUPPORTED_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported mode '{payload.mode}'. Supported modes: {sorted(SUPPORTED_MODES)}.",
            )

        scenario = self.get_scenario(payload.scenario_id)
        run_id = self._generate_run_id()
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        now = datetime.now(UTC)
        metadata = {
            "run_id": run_id,
            "mode": payload.mode,
            "scenario_id": scenario["scenario_id"],
            "description": scenario.get("description"),
            "started_at": now.isoformat(),
            "ended_at": None,
            "duration_seconds": scenario.get("load_profile", {}).get("duration_seconds"),
            "status": "created",
            "time_context": {
                "controller_mode": None,
                "effective_time_utc": None,
                "preset": scenario.get("time_preset"),
            },
            "load_profile": scenario.get("load_profile", {}),
            "failure_plan": scenario.get("failure_plan", []),
        }

        metadata_path = run_dir / "metadata.json"
        with metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)
            handle.write("\n")

        self.append_event(
            run_id,
            {
                "timestamp": now.isoformat(),
                "event_type": "run_created",
                "payload": {
                    "scenario_id": metadata["scenario_id"],
                    "mode": metadata["mode"],
                },
            },
        )

        return metadata

    def get_run(self, run_id: str) -> dict[str, Any]:
        metadata_path = self.runs_dir / run_id / "metadata.json"
        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
        with metadata_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _generate_run_id() -> str:
        now = datetime.now(UTC)
        return f"run_{now.strftime('%Y_%m_%d_%H%M%S')}_{uuid4().hex[:6]}"

    @staticmethod
    def _generate_batch_id() -> str:
        now = datetime.now(UTC)
        return f"batch_{now.strftime('%Y_%m_%d_%H%M%S')}_{uuid4().hex[:6]}"

    def metadata_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "metadata.json"

    def events_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "events.jsonl"

    def update_run_metadata(self, run_id: str, metadata: dict[str, Any]) -> None:
        metadata_path = self.metadata_path(run_id)
        with metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2)
            handle.write("\n")

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        events_path = self.events_path(run_id)
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event))
            handle.write("\n")

    def summary_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "summary.json"

    def batch_dir(self, batch_id: str) -> Path:
        return self.batches_dir / batch_id

    def batch_summary_path(self, batch_id: str) -> Path:
        return self.batch_dir(batch_id) / "summary.json"

    def timeseries_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "timeseries.jsonl"

    def worker_timeseries_path(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "worker_timeseries.jsonl"

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        events_path = self.events_path(run_id)
        if not events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
            handle.write("\n")

    async def prepare_run(self, run_id: str) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Experiment runner HTTP client is not initialized.")

        metadata = self.get_run(run_id)
        mode = metadata["mode"]
        if mode not in EXECUTABLE_MODE_MAP:
            raise HTTPException(
                status_code=409,
                detail=f"Mode '{mode}' is not executable yet. Executable modes: {sorted(EXECUTABLE_MODE_MAP)}.",
            )
        if metadata["status"] != "created":
            raise HTTPException(
                status_code=409,
                detail=f"Run '{run_id}' cannot be prepared from status '{metadata['status']}'.",
            )

        prepared_at = datetime.now(UTC).isoformat()
        try:
            time_preset = metadata["time_context"].get("preset")
            if time_preset:
                time_response = await self.client.post(
                    f"{self.time_controller_url}/time/preset",
                    json={"preset": time_preset},
                )
                time_response.raise_for_status()
                time_payload = time_response.json()
                self.append_event(
                    run_id,
                    {
                        "timestamp": prepared_at,
                        "event_type": "time_preset_applied",
                        "payload": {"preset": time_preset, "time_state": time_payload},
                    },
                )
            else:
                time_response = await self.client.post(f"{self.time_controller_url}/time/resume")
                time_response.raise_for_status()
                time_payload = time_response.json()
                self.append_event(
                    run_id,
                    {
                        "timestamp": prepared_at,
                        "event_type": "time_realtime_resumed",
                        "payload": {"time_state": time_payload},
                    },
                )

            orchestrator_mode = EXECUTABLE_MODE_MAP[mode]
            mode_response = await self.client.post(
                f"{self.orchestrator_url}/mode",
                json={"mode": orchestrator_mode},
            )
            mode_response.raise_for_status()
            mode_payload = mode_response.json()
            self.append_event(
                run_id,
                {
                    "timestamp": prepared_at,
                    "event_type": "orchestrator_mode_applied",
                    "payload": mode_payload,
                },
            )

            recommendation_response = await self.client.get(f"{self.orchestrator_url}/recommendations")
            recommendation_response.raise_for_status()
            recommendation_payload = recommendation_response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Run preparation failed because a control-plane dependency was unreachable: {exc}",
            ) from exc

        metadata["status"] = "prepared"
        metadata["prepared_at"] = prepared_at
        metadata["time_context"]["controller_mode"] = time_payload.get("mode")
        metadata["time_context"]["effective_time_utc"] = recommendation_payload.get("effective_time_utc")
        metadata["execution"] = {
            "orchestrator_mode": orchestrator_mode,
            "time_state": time_payload,
            "recommendation": recommendation_payload,
        }
        self.update_run_metadata(run_id, metadata)
        self.append_event(
            run_id,
            {
                "timestamp": prepared_at,
                "event_type": "run_prepared",
                "payload": {
                    "orchestrator_mode": orchestrator_mode,
                    "effective_time_utc": recommendation_payload.get("effective_time_utc"),
                },
            },
        )
        return metadata

    async def execute_run(self, run_id: str) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Experiment runner HTTP client is not initialized.")

        metadata = self.get_run(run_id)
        if metadata["status"] != "prepared":
            raise HTTPException(
                status_code=409,
                detail=f"Run '{run_id}' cannot be executed from status '{metadata['status']}'.",
            )

        run_dir = self.runs_dir / run_id
        load_profile = metadata.get("load_profile", {})
        execution_started_at = datetime.now(UTC).isoformat()
        metadata["status"] = "running"
        metadata["execution_started_at"] = execution_started_at
        self.update_run_metadata(run_id, metadata)
        self.append_event(
            run_id,
            {
                "timestamp": execution_started_at,
                "event_type": "run_execution_started",
                "payload": {
                    "gateway_url": self.gateway_url,
                    "load_profile": load_profile,
                },
            },
        )

        stop_sampling = asyncio.Event()
        sampler_task = asyncio.create_task(self._sample_run_state(run_id, stop_sampling))
        failure_task = asyncio.create_task(self._run_failure_plan(run_id, metadata.get("failure_plan", [])))
        try:
            locust_result = await self._run_locust(run_id, load_profile, run_dir)
            await failure_task
        except Exception as exc:
            stop_sampling.set()
            try:
                await sampler_task
            except Exception:
                pass
            failure_task.cancel()
            metadata["status"] = "failed"
            metadata["ended_at"] = datetime.now(UTC).isoformat()
            metadata["error"] = str(exc)
            self.update_run_metadata(run_id, metadata)
            self.append_event(
                run_id,
                {
                    "timestamp": metadata["ended_at"],
                    "event_type": "run_failed",
                    "payload": {"error": str(exc)},
                },
            )
            raise

        stop_sampling.set()
        await sampler_task
        ended_at = datetime.now(UTC).isoformat()
        summary = self._build_summary(run_id, metadata, locust_result)
        with self.summary_path(run_id).open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
            handle.write("\n")

        metadata["status"] = "completed" if locust_result["returncode"] == 0 else "failed"
        metadata["ended_at"] = ended_at
        metadata["artifacts"] = {
            "locust_stdout": locust_result["stdout_path"],
            "locust_stderr": locust_result["stderr_path"],
            "locust_csv_prefix": locust_result["csv_prefix"],
            "summary_path": str(self.summary_path(run_id)),
        }
        self.update_run_metadata(run_id, metadata)
        self.append_event(
            run_id,
            {
                "timestamp": ended_at,
                "event_type": "run_execution_completed",
                "payload": {
                    "returncode": locust_result["returncode"],
                    "summary": summary,
                },
            },
        )
        return {
            "run_id": run_id,
            "status": metadata["status"],
            "summary": summary,
            "artifacts": metadata["artifacts"],
        }

    async def _sample_run_state(self, run_id: str, stop_event: asyncio.Event) -> None:
        if self.client is None:
            return

        timeseries_path = self.timeseries_path(run_id)
        worker_timeseries_path = self.worker_timeseries_path(run_id)
        previous_target_workers: int | None = None
        previous_scale_action: str | None = None
        previous_policy_weights: dict[str, float] = {}

        while not stop_event.is_set():
            try:
                response = await self.client.get(f"{self.dashboard_url}/api/overview")
                response.raise_for_status()
                overview = response.json()
                timestamp = overview.get("dashboard_recorded_at") or datetime.now(UTC).isoformat()
                summary = overview.get("summary", {})
                control_plane = overview.get("control_plane", {})
                scale_recommendation = control_plane.get("scale_recommendation") or {}
                current_target_workers = summary.get("strategic_target_workers")
                current_scale_action = scale_recommendation.get("action")
                system_point = {
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "mode": control_plane.get("mode"),
                    "policy_version": control_plane.get("policy_version"),
                    "healthy_workers": summary.get("healthy_workers"),
                    "total_inflight": summary.get("total_worker_inflight"),
                    "max_queue_depth": max(
                        [0, *[(worker.get("queue_depth") or 0) for worker in overview.get("workers", [])]]
                    ),
                    "max_load_score": summary.get("max_worker_load_score"),
                    "max_predicted_pressure": summary.get("max_predicted_pressure"),
                    "strategic_avg_expected_rps": summary.get("strategic_avg_expected_rps"),
                    "strategic_peak_expected_rps": summary.get("strategic_peak_expected_rps"),
                    "target_workers": current_target_workers,
                    "scale_action": current_scale_action,
                    "demand_level": scale_recommendation.get("demand_level"),
                    "effective_time_utc": control_plane.get("effective_time_utc"),
                }
                self.append_jsonl(timeseries_path, system_point)

                current_policy_weights: dict[str, float] = {}
                for worker in overview.get("workers", []):
                    worker_id = worker.get("worker_id")
                    policy_weight = worker.get("policy_weight")
                    if worker_id and policy_weight is not None:
                        current_policy_weights[worker_id] = float(policy_weight)
                    worker_point = {
                        "run_id": run_id,
                        "timestamp": timestamp,
                        "worker_id": worker_id,
                        "healthy": worker.get("healthy"),
                        "inflight": worker.get("inflight_requests"),
                        "queue_depth": worker.get("queue_depth"),
                        "load_score": worker.get("load_score"),
                        "predicted_pressure": worker.get("predicted_pressure"),
                        "policy_weight": policy_weight,
                        "policy_reason": worker.get("policy_reason"),
                        "artificial_delay_ms": worker.get("artificial_delay_ms"),
                    }
                    self.append_jsonl(worker_timeseries_path, worker_point)

                if previous_target_workers is not None and current_target_workers != previous_target_workers:
                    self.append_event(
                        run_id,
                        {
                            "timestamp": timestamp,
                            "event_type": "target_workers_shift",
                            "payload": {
                                "previous": previous_target_workers,
                                "current": current_target_workers,
                            },
                        },
                    )

                if previous_scale_action is not None and current_scale_action != previous_scale_action:
                    self.append_event(
                        run_id,
                        {
                            "timestamp": timestamp,
                            "event_type": "scale_action_shift",
                            "payload": {
                                "previous": previous_scale_action,
                                "current": current_scale_action,
                            },
                        },
                    )

                for worker_id, current_weight in current_policy_weights.items():
                    previous_weight = previous_policy_weights.get(worker_id)
                    if previous_weight is None:
                        continue
                    if abs(current_weight - previous_weight) >= 0.05:
                        self.append_event(
                            run_id,
                            {
                                "timestamp": timestamp,
                                "event_type": "policy_weight_shift",
                                "payload": {
                                    "worker_id": worker_id,
                                    "previous": round(previous_weight, 4),
                                    "current": round(current_weight, 4),
                                },
                            },
                        )

                previous_target_workers = current_target_workers
                previous_scale_action = current_scale_action
                previous_policy_weights = current_policy_weights
            except httpx.HTTPError as exc:
                self.append_event(
                    run_id,
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "event_type": "sampling_error",
                        "payload": {"error": str(exc)},
                    },
                )

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.sample_interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def _run_failure_plan(self, run_id: str, failure_plan: list[dict[str, Any]]) -> None:
        if self.client is None or not failure_plan:
            return

        previous_second = 0
        for failure in sorted(failure_plan, key=lambda item: int(item.get("at_second", 0))):
            at_second = int(failure.get("at_second", 0))
            await asyncio.sleep(max(0, at_second - previous_second))
            previous_second = at_second

            failure_type = failure.get("type")
            target = failure.get("target")
            target_url = self.worker_urls_by_id.get(target or "")
            if failure_type != "latency_injection" or not target_url:
                self.append_event(
                    run_id,
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "event_type": "fault_skipped",
                        "payload": failure,
                    },
                )
                continue

            response = await self.client.post(
                f"{target_url}/faults/latency",
                json={
                    "delay_ms": int(failure.get("delay_ms", 0)),
                    "duration_seconds": int(failure.get("duration_seconds", 1)),
                },
            )
            response.raise_for_status()
            self.append_event(
                run_id,
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "event_type": "fault_injected",
                    "payload": {
                        **failure,
                        "response": response.json(),
                    },
                },
            )

    async def _run_locust(self, run_id: str, load_profile: dict[str, Any], run_dir: Path) -> dict[str, Any]:
        scenario_type = str(load_profile.get("type", "constant")).strip().lower()
        locustfile_path = self.root_dir / "scripts" / "load" / "locustfile.py"
        csv_prefix = run_dir / "locust"
        stdout_path = run_dir / "locust_stdout.log"
        stderr_path = run_dir / "locust_stderr.log"

        env = os.environ.copy()
        env["LOAD_SCENARIO"] = scenario_type
        env["PYTHONPATH"] = str(self.root_dir)

        users = int(load_profile.get("users", 10))
        spawn_rate = int(load_profile.get("spawn_rate", 5))
        duration_seconds = int(load_profile.get("duration_seconds", 60))

        if scenario_type == "constant":
            env["CONSTANT_USERS"] = str(users)
            env["CONSTANT_SPAWN_RATE"] = str(spawn_rate)
            env["CONSTANT_DURATION_SECONDS"] = str(duration_seconds)
        elif scenario_type == "burst":
            env["BURST_BASELINE_USERS"] = str(max(1, users // 4))
            env["BURST_USERS"] = str(users)
            env["BURST_SPAWN_RATE"] = str(spawn_rate)
            env["BURST_DURATION_SECONDS"] = str(duration_seconds)
        elif scenario_type == "spike":
            env["SPIKE_USERS"] = str(users)
            env["SPIKE_SPAWN_RATE"] = str(spawn_rate)
            env["SPIKE_ACTIVE_SECONDS"] = str(max(5, duration_seconds // 3))
            env["SPIKE_WARMUP_SECONDS"] = str(max(5, duration_seconds // 3))
            env["SPIKE_COOLDOWN_SECONDS"] = str(max(5, duration_seconds - (2 * max(5, duration_seconds // 3))))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported load profile type '{scenario_type}'.")

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "locust",
            "-f",
            str(locustfile_path),
            "--host",
            self.gateway_url,
            "--headless",
            "--csv",
            str(csv_prefix),
            cwd=str(self.root_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        self.append_event(
            run_id,
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event_type": "load_generator_completed",
                "payload": {
                    "scenario_type": scenario_type,
                    "returncode": process.returncode,
                },
            },
        )
        return {
            "returncode": process.returncode,
            "csv_prefix": str(csv_prefix),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "stdout": stdout_text,
            "stderr": stderr_text,
        }

    def _build_summary(self, run_id: str, metadata: dict[str, Any], locust_result: dict[str, Any]) -> dict[str, Any]:
        timeseries_points = self._read_jsonl(self.timeseries_path(run_id))
        events = self.read_events(run_id)
        stats_path = Path(f"{locust_result['csv_prefix']}_stats.csv")
        stats: dict[str, Any] = {}
        if stats_path.exists():
            with stats_path.open("r", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
            aggregated = None
            for row in rows:
                if row.get("Name") == "Aggregated":
                    aggregated = row
                    break
            if aggregated is None and rows:
                aggregated = rows[-1]
            if aggregated:
                request_count = int(float(aggregated.get("Request Count", "0") or 0))
                failure_count = int(float(aggregated.get("Failure Count", "0") or 0))
                stats = {
                    "requests_total": request_count,
                    "requests_failed": failure_count,
                    "throughput_avg_rps": float(aggregated.get("Requests/s", "0") or 0),
                    "latency_p50_ms": float(aggregated.get("50%", aggregated.get("Median Response Time", "0")) or 0),
                    "latency_p95_ms": float(aggregated.get("95%", "0") or 0),
                    "latency_p99_ms": float(aggregated.get("99%", "0") or 0),
                    "error_rate": (failure_count / request_count) if request_count else 0.0,
                }

        max_queue_depth = max([0, *[(point.get("max_queue_depth") or 0) for point in timeseries_points]])
        max_load_score = max([0.0, *[(point.get("max_load_score") or 0.0) for point in timeseries_points]])
        max_predicted_pressure = max([0.0, *[(point.get("max_predicted_pressure") or 0.0) for point in timeseries_points]])
        max_target_workers = max([0, *[(point.get("target_workers") or 0) for point in timeseries_points]])
        policy_shift_count = len([event for event in events if event.get("event_type") == "policy_weight_shift"])
        target_worker_shift_count = len([event for event in events if event.get("event_type") == "target_workers_shift"])
        scale_action_shift_count = len([event for event in events if event.get("event_type") == "scale_action_shift"])

        return {
            "run_id": run_id,
            "mode": metadata["mode"],
            "scenario_id": metadata["scenario_id"],
            "status": "completed" if locust_result["returncode"] == 0 else "failed",
            "locust_return_code": locust_result["returncode"],
            "sample_count": len(timeseries_points),
            "max_queue_depth": max_queue_depth,
            "max_load_score": max_load_score,
            "max_predicted_pressure": max_predicted_pressure,
            "max_target_workers": max_target_workers,
            "policy_shift_count": policy_shift_count,
            "target_worker_shift_count": target_worker_shift_count,
            "scale_action_shift_count": scale_action_shift_count,
            **stats,
        }

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def build_comparison(self, scenario_id: str) -> dict[str, Any]:
        summaries_by_mode: dict[str, dict[str, Any]] = {}
        latest_run_ids: dict[str, str] = {}
        for run_dir in sorted(self.runs_dir.glob("run_*")):
            summary_path = run_dir / "summary.json"
            if not summary_path.exists():
                continue
            with summary_path.open("r", encoding="utf-8") as handle:
                summary = json.load(handle)
            if summary.get("scenario_id") != scenario_id:
                continue
            mode = summary.get("mode")
            if not mode:
                continue
            metadata = self.get_run(run_dir.name)
            ended_at = metadata.get("ended_at") or metadata.get("execution_started_at") or metadata.get("started_at")
            existing_run_id = latest_run_ids.get(mode)
            if existing_run_id:
                existing_metadata = self.get_run(existing_run_id)
                existing_ended_at = (
                    existing_metadata.get("ended_at")
                    or existing_metadata.get("execution_started_at")
                    or existing_metadata.get("started_at")
                )
                if str(existing_ended_at) >= str(ended_at):
                    continue
            summaries_by_mode[mode] = summary
            latest_run_ids[mode] = run_dir.name

        comparison = {
            "generated_at": datetime.now(UTC).isoformat(),
            "scenario_id": scenario_id,
            "mode_count": len(summaries_by_mode),
            "runs": [
                {
                    "run_id": latest_run_ids[mode],
                    **summary,
                }
                for mode, summary in sorted(summaries_by_mode.items())
            ],
        }
        comparison_path = self.comparisons_dir / f"{scenario_id}_latest.json"
        with comparison_path.open("w", encoding="utf-8") as handle:
            json.dump(comparison, handle, indent=2)
            handle.write("\n")
        return comparison

    def get_run_artifacts(self, run_id: str) -> dict[str, Any]:
        metadata = self.get_run(run_id)
        summary_path = self.summary_path(run_id)
        summary = None
        if summary_path.exists():
            with summary_path.open("r", encoding="utf-8") as handle:
                summary = json.load(handle)

        return {
            "run_id": run_id,
            "metadata": metadata,
            "summary": summary,
            "events": self.read_events(run_id),
            "timeseries": self._read_jsonl(self.timeseries_path(run_id)),
            "worker_timeseries": self._read_jsonl(self.worker_timeseries_path(run_id)),
        }

    async def execute_batch(self, payload: BatchRunRequest) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("Experiment runner HTTP client is not initialized.")
        if payload.repeat_count < 1 or payload.repeat_count > 10:
            raise HTTPException(status_code=400, detail="repeat_count must be between 1 and 10.")
        _ = self.get_scenario(payload.scenario_id)
        if not payload.modes:
            raise HTTPException(status_code=400, detail="At least one mode must be provided.")

        modes = []
        for mode in payload.modes:
            if mode not in SUPPORTED_MODES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported mode '{mode}'. Supported modes: {sorted(SUPPORTED_MODES)}.",
                )
            if mode not in EXECUTABLE_MODE_MAP:
                raise HTTPException(
                    status_code=400,
                    detail=f"Mode '{mode}' is not executable yet. Executable modes: {sorted(EXECUTABLE_MODE_MAP)}.",
                )
            if mode not in modes:
                modes.append(mode)

        batch_id = self._generate_batch_id()
        batch_dir = self.batch_dir(batch_id)
        batch_dir.mkdir(parents=True, exist_ok=False)

        started_at = datetime.now(UTC).isoformat()
        results: list[dict[str, Any]] = []
        for repeat_index in range(1, payload.repeat_count + 1):
            for mode in modes:
                run_metadata = self.create_run(RunCreateRequest(scenario_id=payload.scenario_id, mode=mode))
                prepared = await self.prepare_run(run_metadata["run_id"])
                execution = await self.execute_run(run_metadata["run_id"])
                results.append(
                    {
                        "repeat_index": repeat_index,
                        "mode": mode,
                        "run_id": run_metadata["run_id"],
                        "prepared_status": prepared["status"],
                        "execution_status": execution["status"],
                        "summary": execution["summary"],
                    }
                )

        aggregate = self._build_batch_aggregate(batch_id, payload.scenario_id, modes, payload.repeat_count, results)
        with self.batch_summary_path(batch_id).open("w", encoding="utf-8") as handle:
            json.dump(aggregate, handle, indent=2)
            handle.write("\n")

        aggregate["started_at"] = started_at
        aggregate["ended_at"] = datetime.now(UTC).isoformat()
        with self.batch_summary_path(batch_id).open("w", encoding="utf-8") as handle:
            json.dump(aggregate, handle, indent=2)
            handle.write("\n")
        return aggregate

    def _build_batch_aggregate(
        self,
        batch_id: str,
        scenario_id: str,
        modes: list[str],
        repeat_count: int,
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {mode: [] for mode in modes}
        for result in results:
            grouped.setdefault(result["mode"], []).append(result)

        def average(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 3) if values else None

        aggregates: list[dict[str, Any]] = []
        for mode in modes:
            mode_results = grouped.get(mode, [])
            summaries = [entry["summary"] for entry in mode_results if entry.get("summary")]
            p95_values = [float(summary.get("latency_p95_ms", 0) or 0) for summary in summaries]
            throughput_values = [float(summary.get("throughput_avg_rps", 0) or 0) for summary in summaries]
            queue_values = [float(summary.get("max_queue_depth", 0) or 0) for summary in summaries]
            error_values = [float(summary.get("error_rate", 0) or 0) for summary in summaries]
            policy_shift_values = [float(summary.get("policy_shift_count", 0) or 0) for summary in summaries]
            aggregates.append(
                {
                    "mode": mode,
                    "run_count": len(mode_results),
                    "completed_runs": len([entry for entry in mode_results if entry.get("execution_status") == "completed"]),
                    "avg_latency_p95_ms": average(p95_values),
                    "best_latency_p95_ms": min(p95_values) if p95_values else None,
                    "worst_latency_p95_ms": max(p95_values) if p95_values else None,
                    "avg_throughput_avg_rps": average(throughput_values),
                    "avg_max_queue_depth": average(queue_values),
                    "avg_error_rate": average(error_values),
                    "avg_policy_shift_count": average(policy_shift_values),
                    "run_ids": [entry["run_id"] for entry in mode_results],
                }
            )

        return {
            "batch_id": batch_id,
            "scenario_id": scenario_id,
            "repeat_count": repeat_count,
            "modes": modes,
            "generated_at": datetime.now(UTC).isoformat(),
            "results": results,
            "aggregates": aggregates,
        }

    def get_batch_summary(self, batch_id: str) -> dict[str, Any]:
        summary_path = self.batch_summary_path(batch_id)
        if not summary_path.exists():
            raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found.")
        with summary_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


state = ExperimentRunnerState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.client = httpx.AsyncClient(timeout=10.0)
    try:
        yield
    finally:
        if state.client is not None:
            await state.client.aclose()
            state.client = None


app = FastAPI(title="experiment-runner-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "experiment-runner",
        "scenarios_dir": str(state.scenarios_dir),
        "runs_dir": str(state.runs_dir),
        "supported_modes": sorted(SUPPORTED_MODES),
        "dashboard_url": state.dashboard_url,
        "orchestrator_url": state.orchestrator_url,
        "time_controller_url": state.time_controller_url,
    }


@app.get("/scenarios")
async def scenarios() -> dict[str, Any]:
    payload = state.list_scenarios()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "count": len(payload),
        "scenarios": payload,
    }


@app.post("/runs")
async def create_run(payload: RunCreateRequest) -> dict[str, Any]:
    metadata = state.create_run(payload)
    return {
        "run_id": metadata["run_id"],
        "status": metadata["status"],
        "scenario_id": metadata["scenario_id"],
        "mode": metadata["mode"],
        "metadata": metadata,
    }


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    return state.get_run(run_id)


@app.post("/runs/{run_id}/prepare")
async def prepare_run(run_id: str) -> dict[str, Any]:
    metadata = await state.prepare_run(run_id)
    return {
        "run_id": metadata["run_id"],
        "status": metadata["status"],
        "prepared_at": metadata.get("prepared_at"),
        "execution": metadata.get("execution"),
    }


@app.post("/runs/{run_id}/execute")
async def execute_run(run_id: str) -> dict[str, Any]:
    return await state.execute_run(run_id)


@app.get("/runs/{run_id}/events")
async def get_run_events(run_id: str) -> dict[str, Any]:
    _ = state.get_run(run_id)
    events = state.read_events(run_id)
    return {
        "run_id": run_id,
        "count": len(events),
        "events": events,
    }


@app.get("/runs/{run_id}/artifacts")
async def get_run_artifacts(run_id: str) -> dict[str, Any]:
    return state.get_run_artifacts(run_id)


@app.get("/comparisons/{scenario_id}")
async def get_comparison(scenario_id: str) -> dict[str, Any]:
    _ = state.get_scenario(scenario_id)
    return state.build_comparison(scenario_id)


@app.post("/batches")
async def execute_batch(payload: BatchRunRequest) -> dict[str, Any]:
    return await state.execute_batch(payload)


@app.get("/batches/{batch_id}")
async def get_batch(batch_id: str) -> dict[str, Any]:
    return state.get_batch_summary(batch_id)
