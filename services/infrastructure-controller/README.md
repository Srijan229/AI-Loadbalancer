# Infrastructure Controller

This service translates orchestration scale recommendations into infrastructure actions.

Current scope:

- local-first simulated Auto Scaling Group behavior
- reads strategic scale recommendations from the orchestrator
- keeps desired/current/pending instance state
- applies cooldown and bounded scale steps
- records action history for dashboard demos

Supported modes:

- `simulate`
- `aws_execute` placeholder only

The `aws_execute` path is intentionally not active yet. This service is meant to take the project to the point where real AWS credentials would be needed.

## Endpoints

- `GET /health`
- `GET /state`
- `GET /actions`
- `POST /mode`
- `POST /sync`
- `POST /execute`
- `POST /reset`

## Demo flow

1. jump to a strategic surge window in the dashboard
2. let the orchestrator produce a higher `target_workers`
3. call infra `sync`
4. call infra `execute`
5. watch desired/current/pending capacity move over time
