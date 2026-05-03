from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
import time as monotonic_time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


PRESETS = {
    "weekday_peak": "Next weekday 18:00 UTC",
    "weekend_evening": "Next Saturday 20:00 UTC",
    "sale_day_evening": "Next synthetic sale day 20:00 UTC",
    "month_end_billing": "Next month-end 10:00 UTC",
}


class SetTimeRequest(BaseModel):
    target_time_utc: datetime


class AdvanceTimeRequest(BaseModel):
    hours: int = Field(default=0, ge=0, le=24 * 365)
    minutes: int = Field(default=0, ge=0, le=24 * 365 * 60)
    days: int = Field(default=0, ge=0, le=3650)


class PresetRequest(BaseModel):
    preset: str


@dataclass
class TimeState:
    mode: str
    simulated_anchor_utc: datetime
    real_anchor_monotonic: float

    def current_time(self) -> datetime:
        if self.mode == "realtime":
            elapsed_seconds = monotonic_time.monotonic() - self.real_anchor_monotonic
            return self.simulated_anchor_utc + timedelta(seconds=elapsed_seconds)
        return self.simulated_anchor_utc


class Controller:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.state = TimeState(
            mode="realtime",
            simulated_anchor_utc=now,
            real_anchor_monotonic=monotonic_time.monotonic(),
        )

    def snapshot(self) -> dict[str, Any]:
        current_time = self.state.current_time()
        return {
            "status": "ok",
            "service": "time-controller",
            "mode": self.state.mode,
            "simulated_time_utc": current_time.isoformat(),
            "anchor_time_utc": self.state.simulated_anchor_utc.isoformat(),
            "presets": list(PRESETS),
        }

    def freeze(self) -> dict[str, Any]:
        current = self.state.current_time()
        self.state = TimeState(
            mode="frozen",
            simulated_anchor_utc=current,
            real_anchor_monotonic=monotonic_time.monotonic(),
        )
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        current = self.state.current_time()
        self.state = TimeState(
            mode="realtime",
            simulated_anchor_utc=current,
            real_anchor_monotonic=monotonic_time.monotonic(),
        )
        return self.snapshot()

    def set_time(self, target: datetime) -> dict[str, Any]:
        normalized = target.astimezone(UTC)
        self.state = TimeState(
            mode="frozen",
            simulated_anchor_utc=normalized,
            real_anchor_monotonic=monotonic_time.monotonic(),
        )
        return self.snapshot()

    def advance(self, days: int, hours: int, minutes: int) -> dict[str, Any]:
        current = self.state.current_time()
        new_time = current + timedelta(days=days, hours=hours, minutes=minutes)
        self.state = TimeState(
            mode="frozen",
            simulated_anchor_utc=new_time,
            real_anchor_monotonic=monotonic_time.monotonic(),
        )
        return self.snapshot()

    def apply_preset(self, preset: str) -> dict[str, Any]:
        if preset not in PRESETS:
            raise HTTPException(status_code=400, detail=f"Unsupported preset '{preset}'.")
        current = self.state.current_time()
        target = {
            "weekday_peak": self._next_weekday_peak(current),
            "weekend_evening": self._next_weekend_evening(current),
            "sale_day_evening": self._next_sale_day_evening(current),
            "month_end_billing": self._next_month_end_billing(current),
        }[preset]
        self.state = TimeState(
            mode="frozen",
            simulated_anchor_utc=target,
            real_anchor_monotonic=monotonic_time.monotonic(),
        )
        snapshot = self.snapshot()
        snapshot["applied_preset"] = preset
        return snapshot

    def _next_weekday_peak(self, current: datetime) -> datetime:
        candidate = current.astimezone(UTC).replace(hour=18, minute=0, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    def _next_weekend_evening(self, current: datetime) -> datetime:
        candidate = current.astimezone(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
        while candidate.weekday() != 5 or candidate <= current:
            candidate += timedelta(days=1)
            candidate = candidate.replace(hour=20, minute=0, second=0, microsecond=0)
        return candidate

    def _next_sale_day_evening(self, current: datetime) -> datetime:
        candidate = current.astimezone(UTC).replace(hour=20, minute=0, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        while not self._is_sale_day(candidate.date()):
            candidate += timedelta(days=1)
            candidate = candidate.replace(hour=20, minute=0, second=0, microsecond=0)
        return candidate

    def _next_month_end_billing(self, current: datetime) -> datetime:
        candidate = current.astimezone(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
        while not self._is_month_end(candidate.date()) or candidate <= current:
            candidate += timedelta(days=1)
            candidate = candidate.replace(hour=10, minute=0, second=0, microsecond=0)
        return candidate

    def _is_sale_day(self, current_day: date) -> bool:
        second_friday = current_day.weekday() == 4 and 8 <= current_day.day <= 14
        next_week = current_day + timedelta(days=7)
        last_saturday = current_day.weekday() == 5 and next_week.month != current_day.month
        return second_friday or last_saturday

    def _is_month_end(self, current_day: date) -> bool:
        return (current_day + timedelta(days=1)).month != current_day.month


controller = Controller()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="time-controller-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return controller.snapshot()


@app.get("/time")
async def get_time() -> dict[str, Any]:
    return controller.snapshot()


@app.get("/presets")
async def presets() -> dict[str, Any]:
    return {"presets": PRESETS}


@app.post("/time/freeze")
async def freeze_time() -> dict[str, Any]:
    return controller.freeze()


@app.post("/time/resume")
async def resume_time() -> dict[str, Any]:
    return controller.resume()


@app.post("/time/set")
async def set_time(payload: SetTimeRequest) -> dict[str, Any]:
    return controller.set_time(payload.target_time_utc)


@app.post("/time/advance")
async def advance_time(payload: AdvanceTimeRequest) -> dict[str, Any]:
    if payload.days == 0 and payload.hours == 0 and payload.minutes == 0:
        raise HTTPException(status_code=400, detail="Advance request must change time.")
    return controller.advance(payload.days, payload.hours, payload.minutes)


@app.post("/time/preset")
async def apply_preset(payload: PresetRequest) -> dict[str, Any]:
    return controller.apply_preset(payload.preset)
