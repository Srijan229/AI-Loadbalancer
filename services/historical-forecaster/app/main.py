import csv
import math
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


HOLIDAYS: dict[date, str] = {
    date(2025, 1, 1): "new_year",
    date(2025, 2, 14): "valentine_campaign",
    date(2025, 5, 26): "memorial_day_weekend",
}


@dataclass(frozen=True)
class AggregateStats:
    count: int
    actual_rps: float
    avg_latency_ms: float
    p95_latency_ms: float
    error_rate: float
    avg_payload_kb: float
    avg_work_units: float
    recommended_workers: float


class ForecastRequest(BaseModel):
    target_start_utc: datetime
    interval_count: int = Field(default=4, ge=1, le=672)
    is_sale_day: bool | None = None
    event_type: str | None = None


class HistoricalForecaster:
    def __init__(self) -> None:
        self.data_path = self._resolve_data_path()
        self.rows: list[dict[str, Any]] = []
        self.exact_index: dict[tuple[str, int, int, int, str], AggregateStats] = {}
        self.daypart_index: dict[tuple[str, int, int, int], AggregateStats] = {}
        self.weekpart_index: dict[tuple[int, int, int, int], AggregateStats] = {}
        self.hour_index: dict[tuple[int, int, int], AggregateStats] = {}
        self.global_hour_index: dict[tuple[int], AggregateStats] = {}
        self.summary: dict[str, Any] = {}

    def _resolve_data_path(self) -> Path:
        env_path = os.getenv("HISTORICAL_DATA_PATH", "").strip()
        candidates = []
        if env_path:
            candidates.append(Path(env_path).expanduser())
        candidates.append(Path.cwd() / "data" / "historical" / "synthetic_workload_history.csv")
        file_path = Path(__file__).resolve()
        for ancestor in file_path.parents:
            candidates.append(ancestor / "data" / "historical" / "synthetic_workload_history.csv")
        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise FileNotFoundError("Unable to locate synthetic_workload_history.csv for historical forecaster.")

    def load(self) -> None:
        with self.data_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.rows = [self._normalize_row(row) for row in reader]
        if not self.rows:
            raise ValueError("Historical dataset is empty.")
        self._build_indexes()
        self._build_summary()

    def _normalize_row(self, row: dict[str, str]) -> dict[str, Any]:
        return {
            "timestamp_utc": row["timestamp_utc"],
            "day_of_week": row["day_of_week"],
            "hour_of_day": int(row["hour_of_day"]),
            "minute_bucket": int(row["minute_bucket"]),
            "is_weekend": int(row["is_weekend"]),
            "is_sale_day": int(row["is_sale_day"]),
            "event_type": row["event_type"],
            "baseline_rps": float(row["baseline_rps"]),
            "demand_multiplier": float(row["demand_multiplier"]),
            "actual_rps": float(row["actual_rps"]),
            "avg_latency_ms": float(row["avg_latency_ms"]),
            "p95_latency_ms": float(row["p95_latency_ms"]),
            "error_rate": float(row["error_rate"]),
            "avg_payload_kb": float(row["avg_payload_kb"]),
            "avg_work_units": float(row["avg_work_units"]),
            "recommended_workers": int(row["recommended_workers"]),
        }

    def _build_indexes(self) -> None:
        exact: defaultdict[tuple[str, int, int, int, str], list[dict[str, Any]]] = defaultdict(list)
        daypart: defaultdict[tuple[str, int, int, int], list[dict[str, Any]]] = defaultdict(list)
        weekpart: defaultdict[tuple[int, int, int, int], list[dict[str, Any]]] = defaultdict(list)
        hourpart: defaultdict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
        global_hour: defaultdict[tuple[int], list[dict[str, Any]]] = defaultdict(list)

        for row in self.rows:
            exact[(row["day_of_week"], row["hour_of_day"], row["minute_bucket"], row["is_sale_day"], row["event_type"])].append(row)
            daypart[(row["day_of_week"], row["hour_of_day"], row["minute_bucket"], row["is_sale_day"])].append(row)
            weekpart[(row["is_weekend"], row["hour_of_day"], row["minute_bucket"], row["is_sale_day"])].append(row)
            hourpart[(row["is_weekend"], row["hour_of_day"], row["is_sale_day"])].append(row)
            global_hour[(row["hour_of_day"],)].append(row)

        self.exact_index = {key: self._aggregate(rows) for key, rows in exact.items()}
        self.daypart_index = {key: self._aggregate(rows) for key, rows in daypart.items()}
        self.weekpart_index = {key: self._aggregate(rows) for key, rows in weekpart.items()}
        self.hour_index = {key: self._aggregate(rows) for key, rows in hourpart.items()}
        self.global_hour_index = {key: self._aggregate(rows) for key, rows in global_hour.items()}

    def _aggregate(self, rows: list[dict[str, Any]]) -> AggregateStats:
        return AggregateStats(
            count=len(rows),
            actual_rps=round(mean(row["actual_rps"] for row in rows), 3),
            avg_latency_ms=round(mean(row["avg_latency_ms"] for row in rows), 3),
            p95_latency_ms=round(mean(row["p95_latency_ms"] for row in rows), 3),
            error_rate=round(mean(row["error_rate"] for row in rows), 4),
            avg_payload_kb=round(mean(row["avg_payload_kb"] for row in rows), 3),
            avg_work_units=round(mean(row["avg_work_units"] for row in rows), 3),
            recommended_workers=round(mean(row["recommended_workers"] for row in rows), 3),
        )

    def _build_summary(self) -> None:
        weekday_rps = [row["actual_rps"] for row in self.rows if row["is_weekend"] == 0]
        weekend_rps = [row["actual_rps"] for row in self.rows if row["is_weekend"] == 1]
        sale_rps = [row["actual_rps"] for row in self.rows if row["is_sale_day"] == 1]
        event_types = sorted({row["event_type"] for row in self.rows})
        self.summary = {
            "data_path": str(self.data_path),
            "records": len(self.rows),
            "first_timestamp_utc": self.rows[0]["timestamp_utc"],
            "last_timestamp_utc": self.rows[-1]["timestamp_utc"],
            "event_types": event_types,
            "weekday_avg_rps": round(mean(weekday_rps), 3),
            "weekend_avg_rps": round(mean(weekend_rps), 3),
            "sale_day_avg_rps": round(mean(sale_rps), 3),
        }

    def forecast(self, payload: ForecastRequest) -> dict[str, Any]:
        forecasts: list[dict[str, Any]] = []
        current_ts = payload.target_start_utc.astimezone(UTC)
        for _ in range(payload.interval_count):
            context = self._infer_context(current_ts, payload.is_sale_day, payload.event_type)
            aggregate, strategy = self._match_context(context)
            forecasts.append(
                {
                    "timestamp_utc": current_ts.isoformat(),
                    "context": context,
                    "matched_strategy": strategy,
                    "sample_count": aggregate.count,
                    "expected_rps": aggregate.actual_rps,
                    "expected_avg_latency_ms": aggregate.avg_latency_ms,
                    "expected_p95_latency_ms": aggregate.p95_latency_ms,
                    "expected_error_rate": aggregate.error_rate,
                    "expected_avg_payload_kb": aggregate.avg_payload_kb,
                    "expected_avg_work_units": aggregate.avg_work_units,
                    "recommended_workers": max(2, math.ceil(aggregate.recommended_workers)),
                }
            )
            current_ts += timedelta(minutes=15)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "source_dataset": self.summary,
            "forecasts": forecasts,
        }

    def _infer_context(self, ts: datetime, sale_override: bool | None, event_override: str | None) -> dict[str, Any]:
        current_day = ts.date()
        is_weekend = int(ts.weekday() >= 5)
        is_sale_day = int(sale_override if sale_override is not None else self._is_sale_day(current_day))
        inferred_event = event_override or self._event_type(current_day, ts.hour)
        return {
            "day_of_week": current_day.strftime("%A"),
            "hour_of_day": ts.hour,
            "minute_bucket": ts.minute,
            "is_weekend": is_weekend,
            "is_sale_day": is_sale_day,
            "event_type": inferred_event,
        }

    def _match_context(self, context: dict[str, Any]) -> tuple[AggregateStats, str]:
        exact_key = (
            context["day_of_week"],
            context["hour_of_day"],
            context["minute_bucket"],
            context["is_sale_day"],
            context["event_type"],
        )
        if exact_key in self.exact_index:
            return self.exact_index[exact_key], "exact_day_hour_minute_sale_event"

        daypart_key = (
            context["day_of_week"],
            context["hour_of_day"],
            context["minute_bucket"],
            context["is_sale_day"],
        )
        if daypart_key in self.daypart_index:
            return self.daypart_index[daypart_key], "same_day_hour_minute_sale"

        weekpart_key = (
            context["is_weekend"],
            context["hour_of_day"],
            context["minute_bucket"],
            context["is_sale_day"],
        )
        if weekpart_key in self.weekpart_index:
            return self.weekpart_index[weekpart_key], "same_weekpart_hour_minute_sale"

        hour_key = (
            context["is_weekend"],
            context["hour_of_day"],
            context["is_sale_day"],
        )
        if hour_key in self.hour_index:
            return self.hour_index[hour_key], "same_weekpart_hour_sale"

        global_hour_key = (context["hour_of_day"],)
        if global_hour_key in self.global_hour_index:
            return self.global_hour_index[global_hour_key], "global_hour"

        raise HTTPException(status_code=404, detail="No historical pattern match found.")

    def _is_sale_day(self, current_day: date) -> bool:
        second_friday = current_day.weekday() == 4 and 8 <= current_day.day <= 14
        next_week = current_day + timedelta(days=7)
        last_saturday = current_day.weekday() == 5 and next_week.month != current_day.month
        return second_friday or last_saturday

    def _event_type(self, current_day: date, hour: int) -> str:
        if current_day in HOLIDAYS and 10 <= hour < 23:
            return HOLIDAYS[current_day]
        if self._is_sale_day(current_day):
            if 8 <= hour < 11 or 12 <= hour < 15 or 19 <= hour < 22:
                return "sale_day"
        if current_day.day in {1, 15} and 8 <= hour < 23:
            return "payday"
        next_day = current_day + timedelta(days=1)
        if next_day.month != current_day.month and 9 <= hour < 22:
            return "month_end_billing"
        return "none"


state = HistoricalForecaster()


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.load()
    yield


app = FastAPI(title="historical-forecaster-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "historical-forecaster",
        **state.summary,
    }


@app.get("/summary")
async def summary() -> dict[str, Any]:
    return state.summary


@app.post("/forecast")
async def forecast(payload: ForecastRequest) -> dict[str, Any]:
    return state.forecast(payload)
