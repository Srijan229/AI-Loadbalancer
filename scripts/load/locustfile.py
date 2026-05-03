import os
import random
from typing import Optional

from locust import HttpUser, LoadTestShape, between, task


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


SCENARIO = os.getenv("LOAD_SCENARIO", "constant").strip().lower()
PAYLOAD_MIN = _env_int("PAYLOAD_MIN", 10)
PAYLOAD_MAX = _env_int("PAYLOAD_MAX", 50)
WORK_UNITS_MIN = _env_int("WORK_UNITS_MIN", 5)
WORK_UNITS_MAX = _env_int("WORK_UNITS_MAX", 20)


class GatewayUser(HttpUser):
    wait_time = between(
        _env_float("REQUEST_WAIT_MIN_SECONDS", 0.05),
        _env_float("REQUEST_WAIT_MAX_SECONDS", 0.20),
    )

    @task
    def send_work(self) -> None:
        payload = {
            "payload_size": random.randint(PAYLOAD_MIN, PAYLOAD_MAX),
            "work_units": random.randint(WORK_UNITS_MIN, WORK_UNITS_MAX),
        }
        with self.client.post("/work", json=payload, catch_response=True, name="/work") as response:
            if response.status_code != 200:
                response.failure(f"Unexpected status: {response.status_code}")


class AdaptiveLoadShape(LoadTestShape):
    """
    Supported scenarios:
    - constant: flat user count
    - burst: baseline traffic with repeating short bursts
    - spike: sharp spike then cooldown
    """

    scenario = SCENARIO

    def tick(self) -> Optional[tuple[int, int]]:
        run_time = self.get_run_time()

        if self.scenario == "constant":
            users = _env_int("CONSTANT_USERS", 15)
            spawn_rate = _env_int("CONSTANT_SPAWN_RATE", 5)
            duration = _env_int("CONSTANT_DURATION_SECONDS", 120)
            if run_time > duration:
                return None
            return users, spawn_rate

        if self.scenario == "burst":
            baseline_users = _env_int("BURST_BASELINE_USERS", 10)
            burst_users = _env_int("BURST_USERS", 35)
            spawn_rate = _env_int("BURST_SPAWN_RATE", 8)
            total_duration = _env_int("BURST_DURATION_SECONDS", 180)
            cycle_seconds = _env_int("BURST_CYCLE_SECONDS", 30)
            burst_seconds = _env_int("BURST_ACTIVE_SECONDS", 10)
            if run_time > total_duration:
                return None
            in_burst = (run_time % cycle_seconds) < burst_seconds
            return (burst_users if in_burst else baseline_users), spawn_rate

        if self.scenario == "spike":
            warmup_users = _env_int("SPIKE_WARMUP_USERS", 8)
            spike_users = _env_int("SPIKE_USERS", 50)
            cooldown_users = _env_int("SPIKE_COOLDOWN_USERS", 6)
            spawn_rate = _env_int("SPIKE_SPAWN_RATE", 10)
            warmup_seconds = _env_int("SPIKE_WARMUP_SECONDS", 20)
            spike_seconds = _env_int("SPIKE_ACTIVE_SECONDS", 20)
            cooldown_seconds = _env_int("SPIKE_COOLDOWN_SECONDS", 40)
            total_duration = warmup_seconds + spike_seconds + cooldown_seconds
            if run_time > total_duration:
                return None
            if run_time < warmup_seconds:
                return warmup_users, spawn_rate
            if run_time < warmup_seconds + spike_seconds:
                return spike_users, spawn_rate
            return cooldown_users, spawn_rate

        raise RuntimeError(
            f"Unsupported LOAD_SCENARIO '{self.scenario}'. "
            "Supported values: constant, burst, spike."
        )

