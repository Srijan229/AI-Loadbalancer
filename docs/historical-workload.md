# Historical Workload Model

This project now includes a synthetic historical workload dataset so we can model:

- weekday vs weekend behavior
- hour-of-day seasonality
- sale day spikes
- payday / month-end billing effects
- holiday/event anomalies

The goal is not to pretend this is real production data. The goal is to create a reproducible workload history that is rich enough to test long-horizon forecasting logic.

## Dataset Shape

Each row represents one 15-minute interval.

Fields:

- `timestamp_utc`
- `day_of_week`
- `hour_of_day`
- `minute_bucket`
- `is_weekend`
- `is_sale_day`
- `event_type`
- `baseline_rps`
- `demand_multiplier`
- `actual_rps`
- `avg_latency_ms`
- `p95_latency_ms`
- `error_rate`
- `avg_payload_kb`
- `avg_work_units`
- `recommended_workers`

## Pattern Assumptions

### Weekdays

- stronger morning ramp
- highest sustained demand during workday and early evening
- lower overnight traffic

### Weekends

- softer morning traffic
- stronger afternoon/evening usage
- different payload/work-unit mix

### Sale Days

- scheduled large spikes
- strongest windows around 09:00, 13:00, and 20:00

### Payday and Billing Days

- moderate demand lift around the 1st, 15th, and month-end

### Holidays / Events

- special anomaly multipliers for selected dates

## Generation

Run:

```powershell
python scripts\data\generate_historical_workload.py
```

Output:

- `data/historical/synthetic_workload_history.csv`

## Why This Matters

This dataset gives the project a second forecasting horizon:

- short-term: seconds to minutes for adaptive routing
- long-term: days and event windows for proactive capacity planning

That is a much stronger systems story than using only immediate pressure signals.
