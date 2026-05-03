# Service Architecture

## Stage 1 Services

Stage 1 is split into a `data plane` and a `control plane`.

### Data Plane

#### `gateway`
- external entrypoint for traffic
- selects a worker based on current routing mode and policy
- forwards requests to workers
- exports request, latency, and routing metrics

#### `worker`
- simulates an application server
- processes requests with configurable artificial work
- exports worker health and load metrics
- supports fault injection controls

### Control Plane

#### `metrics-collector`
- gathers live metrics snapshots from worker and gateway services
- normalizes them into a format the predictor and orchestrator can use
- writes recent state into Redis

#### `predictor`
- reads recent metrics windows
- forecasts short-horizon load trends
- publishes predicted pressure scores

#### `historical-forecaster`
- reads synthetic multi-week workload history
- models weekday/weekend/event-driven demand patterns
- produces long-horizon demand forecasts for future windows

#### `time-controller`
- maintains simulation time for demos and forecasting
- supports fast-forward and preset jumps to meaningful windows
- gives strategic services a non-wall-clock time source

#### `orchestrator`
- computes routing weights for the gateway
- supports three modes:
  - `round_robin`
  - `least_connections`
  - `predictive`
- excludes unhealthy workers
- publishes the active routing policy

#### `failure-injector`
- applies controlled faults to workers
- supports latency injection and pod failure scenarios

#### `experiment-runner`
- runs repeatable benchmark scenarios
- drives traffic patterns and records mode comparisons

### Infrastructure Services

#### `redis`
- shared low-latency state store for policy and metrics snapshots

#### `prometheus`
- scrapes metrics endpoints

#### `grafana`
- visualizes system behavior and comparison results

## Communication Pattern

### Request path
1. client sends request to `gateway`
2. `gateway` chooses a target worker using the current mode/policy
3. `gateway` forwards the request to `worker`
4. `worker` returns response
5. `gateway` returns final response to client

### Control path
1. `metrics-collector` gathers metrics and stores snapshots
2. `predictor` reads recent snapshots and computes forecasts
3. `time-controller` can override current simulation time
4. `historical-forecaster` provides long-horizon baseline forecasts
5. `orchestrator` reads live state and predictions
6. `orchestrator` publishes a routing policy
7. `gateway` refreshes and applies that policy locally

## Orchestrator V1 Boundary

The first orchestrator implementation will only own:
- active routing mode
- policy versioning
- static policy publication

It will not yet own:
- predictive scoring
- worker health scoring
- Redis-backed state
- scale decisions

## Metrics Collector V1 Boundary

The first metrics collector implementation will:
- poll structured `/health` endpoints from workers and gateway
- normalize that state into one snapshot
- expose the snapshot to the orchestrator

It will not yet:
- parse Prometheus metrics directly
- persist history
- compute forecasts

## Stage 1 Decision

The gateway will not call the orchestrator on every request.

Instead:
- the orchestrator periodically publishes the latest routing policy
- the gateway periodically refreshes it
- routing stays in the data plane

This avoids turning the control plane into a per-request bottleneck.
