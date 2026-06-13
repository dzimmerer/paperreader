#!/usr/bin/env bash
# Build the three Paper Reader images into minikube's Docker daemon and deploy
# them to the local cluster. Idempotent: re-run after code changes.
set -euo pipefail

cd "$(dirname "$0")"
REPO_ROOT="$(cd .. && pwd)"

if ! minikube status >/dev/null 2>&1; then
  echo "==> Starting minikube..."
  minikube start
fi

echo "==> Pointing Docker at the minikube daemon..."
eval "$(minikube docker-env)"

echo "==> Building images (context: $REPO_ROOT)..."
docker build -t paperreader-tts:latest      -f Dockerfile.tts      "$REPO_ROOT"
docker build -t paperreader-backend:latest  -f Dockerfile.backend  "$REPO_ROOT"
docker build -t paperreader-frontend:latest -f Dockerfile.frontend "$REPO_ROOT"

echo "==> Applying Kubernetes manifests..."
# Namespace first so the namespaced resources don't race ahead of it.
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/

# If images were rebuilt, restart so pods pick up the new :latest layers.
kubectl -n paperreader rollout restart deploy/tts deploy/backend deploy/frontend >/dev/null 2>&1 || true

echo "==> Waiting for rollouts..."
kubectl -n paperreader rollout status deploy/tts --timeout=120s
kubectl -n paperreader rollout status deploy/backend --timeout=180s
kubectl -n paperreader rollout status deploy/frontend --timeout=120s

echo
echo "==> Ready. Open the app with:"
echo "      minikube service frontend -n paperreader"
echo "    (or: kubectl -n paperreader port-forward svc/frontend 8080:80  ->  http://localhost:8080)"
