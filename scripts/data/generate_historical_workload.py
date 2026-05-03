from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path


OUTPUT_PATH = Path("data/historical/synthetic_workload_history.csv")
START_DATE = date(2025, 1, 1)
TOTAL_DAYS = 140
INTERVAL_MINUTES = 15
WORKER_CAPACITY_RPS = 55.0
SEED = 229


@dataclass(frozen=True)
class EventWindow:
    event_type: str
    multiplier: float
    start_hour: int
    end_hour: int


HOLIDAYS: dict[date, str] = {
    date(2025, 1, 1): "new_year",
    date(2025, 2, 14): "valentine_campaign",
    date(2025, 5, 26): "memorial_day_weekend",
}


def sale_days() -> set[date]:
    days: set[date] = set()
    current = START_DATE
    end_date = START_DATE + timedelta(days=TOTAL_DAYS)
    while current < end_date:
        # Second Friday of each month
        if current.weekday() == 4 and 8 <= current.day <= 14:
            days.add(current)
        # Last Saturday of each month
        next_week = current + timedelta(days=7)
        if current.weekday() == 5 and next_week.month != current.month:
            days.add(current)
        current += timedelta(days=1)
    return days


SALE_DAYS = sale_days()


def weekday_hourly_profile(hour: int) -> float:
    if 0 <= hour < 6:
        return 0.32
    if 6 <= hour < 9:
        return 0.75 + ((hour - 6) * 0.18)
    if 9 <= hour < 12:
        return 1.25
    if 12 <= hour < 17:
        return 1.42
    if 17 <= hour < 21:
        return 1.18
    return 0.7


def weekend_hourly_profile(hour: int) -> float:
    if 0 <= hour < 8:
        return 0.26
    if 8 <= hour < 12:
        return 0.72
    if 12 <= hour < 18:
        return 1.08
    if 18 <= hour < 23:
        return 1.22
    return 0.55


def event_windows(current_day: date) -> list[EventWindow]:
    windows: list[EventWindow] = []
    if current_day in HOLIDAYS:
        windows.append(EventWindow(HOLIDAYS[current_day], 1.45, 10, 23))
    if current_day.day in {1, 15}:
        windows.append(EventWindow("payday", 1.18, 8, 23))
    next_day = current_day + timedelta(days=1)
    if next_day.month != current_day.month:
        windows.append(EventWindow("month_end_billing", 1.22, 9, 22))
    if current_day in SALE_DAYS:
        windows.extend(
            [
                EventWindow("sale_day", 1.9, 8, 11),
                EventWindow("sale_day", 1.55, 12, 15),
                EventWindow("sale_day", 2.2, 19, 22),
            ]
        )
    return windows


def active_event_type(hour: int, windows: list[EventWindow]) -> str:
    active = [window.event_type for window in windows if window.start_hour <= hour < window.end_hour]
    return active[0] if active else "none"


def event_multiplier(hour: int, windows: list[EventWindow]) -> float:
    multiplier = 1.0
    for window in windows:
        if window.start_hour <= hour < window.end_hour:
            multiplier *= window.multiplier
    return multiplier


def minute_noise(minute_bucket: int) -> float:
    return 1.0 + ((minute_bucket / 15.0) * 0.02)


def row_for_timestamp(ts: datetime, rng: random.Random) -> dict[str, str | int | float]:
    current_day = ts.date()
    hour = ts.hour
    minute_bucket = ts.minute
    is_weekend = current_day.weekday() >= 5
    is_sale_day = current_day in SALE_DAYS

    base_daily_rps = 28.0 if not is_weekend else 20.0
    profile = weekend_hourly_profile(hour) if is_weekend else weekday_hourly_profile(hour)

    event_defs = event_windows(current_day)
    event_type = active_event_type(hour, event_defs)
    event_boost = event_multiplier(hour, event_defs)

    trend_position = (ts - datetime.combine(START_DATE, time.min, tzinfo=UTC)).days / TOTAL_DAYS
    seasonal_growth = 1.0 + (0.18 * trend_position)

    burst_noise = 1.0 + rng.uniform(-0.07, 0.08)
    if rng.random() < 0.012:
        burst_noise *= rng.uniform(1.15, 1.35)

    demand_multiplier = profile * event_boost * seasonal_growth * minute_noise(minute_bucket) * burst_noise
    baseline_rps = round(base_daily_rps * profile, 3)
    actual_rps = round(base_daily_rps * demand_multiplier, 3)

    congestion_ratio = actual_rps / WORKER_CAPACITY_RPS
    latency_base = 24.0 if not is_weekend else 21.0
    avg_latency_ms = round(
        latency_base
        + (actual_rps * 0.55)
        + max(congestion_ratio - 0.85, 0.0) ** 2 * 180.0,
        3,
    )
    p95_latency_ms = round(avg_latency_ms * (1.28 + max(congestion_ratio - 0.9, 0.0) * 0.45), 3)
    error_rate = round(max(congestion_ratio - 1.0, 0.0) * 0.035, 4)

    avg_payload_kb = round((18.0 if not is_weekend else 14.0) * (1.12 if is_sale_day else 1.0), 3)
    avg_work_units = round((8.0 if not is_weekend else 6.5) * (1.18 if event_type == "sale_day" else 1.0), 3)
    recommended_workers = max(2, math.ceil((actual_rps * 1.28) / WORKER_CAPACITY_RPS))

    return {
        "timestamp_utc": ts.isoformat(),
        "day_of_week": current_day.strftime("%A"),
        "hour_of_day": hour,
        "minute_bucket": minute_bucket,
        "is_weekend": int(is_weekend),
        "is_sale_day": int(is_sale_day),
        "event_type": event_type,
        "baseline_rps": baseline_rps,
        "demand_multiplier": round(demand_multiplier, 4),
        "actual_rps": actual_rps,
        "avg_latency_ms": avg_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "error_rate": error_rate,
        "avg_payload_kb": avg_payload_kb,
        "avg_work_units": avg_work_units,
        "recommended_workers": recommended_workers,
    }


def generate_rows() -> list[dict[str, str | int | float]]:
    rng = random.Random(SEED)
    rows: list[dict[str, str | int | float]] = []
    current_ts = datetime.combine(START_DATE, time.min, tzinfo=UTC)
    end_ts = current_ts + timedelta(days=TOTAL_DAYS)
    interval = timedelta(minutes=INTERVAL_MINUTES)

    while current_ts < end_ts:
        rows.append(row_for_timestamp(current_ts, rng))
        current_ts += interval
    return rows


def write_csv(rows: list[dict[str, str | int | float]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = generate_rows()
    write_csv(rows)
    sale_day_rows = sum(1 for row in rows if row["is_sale_day"] == 1)
    print(f"generated_rows={len(rows)}")
    print(f"sale_day_rows={sale_day_rows}")
    print(f"output={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
