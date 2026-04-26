# Stage 1 Implementation Contract

## Goal

Stage 1 exists to prove one narrow claim:

Predictive routing can outperform standard balancing policies under bursty load and partial failures.

## Scope

### Data Plane
- gateway
- worker deployment with multiple replicas

### Control Plane
- metrics collector
- predictor
- orchestrator
- failure injector
- Redis

### Observability
- Prometheus
- Grafana

## Comparison Modes

- round robin
- least connections
- predictive weighted routing

## Verification Style

Every implementation step must be:

1. built
2. explained
3. verified by running it locally
4. approved before continuing

## Initial Build Order

1. repository setup
2. project structure and service contracts
3. first worker service
4. gateway with baseline routing
5. Kubernetes deployment for first runnable slice
6. observability baseline
7. orchestrator and predictor
8. failure injection
9. benchmark scenarios

