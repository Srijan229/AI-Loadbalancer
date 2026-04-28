# Kubernetes Deployment

This directory contains the first runnable Kubernetes slice for Stage 1:

- `gateway`
- `worker-a`
- `worker-b`

## Why two worker deployments?

For this phase, the gateway itself is responsible for proving `round_robin` behavior.

Using two named worker services gives the gateway stable upstream identities:
- `http://worker-a:8000`
- `http://worker-b:8000`

That makes in-cluster routing behavior easy to verify.

## Build Images For Minikube

If Minikube is running and using its own Docker daemon:

```powershell
minikube image build -t ai-loadbalancer-worker:dev services/worker
minikube image build -t ai-loadbalancer-gateway:dev services/gateway
```

## Apply Manifests

```powershell
kubectl apply -k deploy/k8s/base
```

## Verify Resources

```powershell
kubectl get pods -n ai-loadbalancer
kubectl get svc -n ai-loadbalancer
kubectl describe deployment gateway -n ai-loadbalancer
```

## Port Forward Gateway

```powershell
kubectl port-forward -n ai-loadbalancer svc/gateway 8001:8001
```

Then test:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8001/health
1..4 | ForEach-Object {
  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/work -ContentType "application/json" -Body '{"payload_size":10,"work_units":5}'
}
```

Expected result:
- responses alternate between `worker-a` and `worker-b`

## Clean Up

```powershell
kubectl delete -k deploy/k8s/base
```

