# AI-Driven Adaptive Load Orchestrator

A Kubernetes-based distributed systems project for comparing traditional load balancing strategies against a predictive orchestration layer under bursty traffic and injected failures.

## Stage 1 Objective

Build a local, production-inspired MVP on Minikube that demonstrates:

- multiple worker pods handling requests
- a gateway routing traffic in different modes
- a control plane that uses metrics and short-horizon prediction
- Prometheus and Grafana observability
- measurable comparison between reactive and predictive routing

## Planned Stack

- Python
- FastAPI
- Redis
- Prometheus
- Grafana
- Docker
- Minikube
- Kubernetes manifests

## Repository Structure

```text
services/
shared/
deploy/
observability/
scripts/
docs/
```

## Workflow

We will implement this project in verifiable steps. Each step should end with:

1. code or config changes
2. a local verification method
3. your approval before moving to the next step

