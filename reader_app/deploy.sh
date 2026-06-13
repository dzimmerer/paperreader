#!/usr/bin/env bash
# Build the Paper Reader images into minikube's Docker daemon and deploy them.
# Idempotent: re-run after code changes.
#
#   ./deploy.sh                # all-in-cluster; TTS runs as a container (CPU)
#   ./deploy.sh --native-tts   # REALTIME: TTS runs natively on the host, the
#                              # cluster reaches it via an ExternalName service
#
# Why --native-tts: PyTorch CPU inference inside minikube's Linux VM on Apple
# Silicon is ~7x slower than native (no Apple Accelerate), i.e. slower than
# realtime, which causes a pause before every sentence. Native Kokoro hits
# ~4.7x realtime. In native mode, start the host server with ./run-native-tts.sh.
set -euo pipefail

cd "$(dirname "$0")"
REPO_ROOT="$(cd .. && pwd)"

NATIVE_TTS=0
[ "${1:-}" = "--native-tts" ] && NATIVE_TTS=1

if ! minikube status >/dev/null 2>&1; then
  echo "==> Starting minikube..."
  minikube start
fi

echo "==> Pointing Docker at the minikube daemon..."
eval "$(minikube docker-env)"

echo "==> Building images (context: $REPO_ROOT)..."
docker build -t paperreader-backend:latest  -f Dockerfile.backend  "$REPO_ROOT"
docker build -t paperreader-frontend:latest -f Dockerfile.frontend "$REPO_ROOT"
if [ "$NATIVE_TTS" -eq 0 ]; then
  docker build -t paperreader-tts:latest -f Dockerfile.tts "$REPO_ROOT"
fi

echo "==> Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml          # namespace first (avoid a race)
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/frontend.yaml

if [ "$NATIVE_TTS" -eq 1 ]; then
  echo "==> TTS: native host mode (ExternalName -> host.minikube.internal)"
  kubectl -n paperreader delete deploy tts --ignore-not-found
  kubectl delete svc tts -n paperreader --ignore-not-found   # may be wrong type
  kubectl apply -f k8s/tts-native.yaml
else
  echo "==> TTS: in-cluster container mode"
  kubectl delete svc tts -n paperreader --ignore-not-found   # may be ExternalName
  kubectl apply -f k8s/tts.yaml
fi

# Pick up rebuilt :latest layers.
kubectl -n paperreader rollout restart deploy/backend deploy/frontend >/dev/null 2>&1 || true
[ "$NATIVE_TTS" -eq 0 ] && kubectl -n paperreader rollout restart deploy/tts >/dev/null 2>&1 || true

echo "==> Waiting for rollouts..."
kubectl -n paperreader rollout status deploy/backend --timeout=180s
kubectl -n paperreader rollout status deploy/frontend --timeout=120s
[ "$NATIVE_TTS" -eq 0 ] && kubectl -n paperreader rollout status deploy/tts --timeout=120s

echo
if [ "$NATIVE_TTS" -eq 1 ]; then
  echo "==> Now start the native TTS server (separate terminal, keep it running):"
  echo "      ./run-native-tts.sh"
fi
echo "==> Open the app with:"
echo "      minikube service frontend -n paperreader"
echo "    (or: kubectl -n paperreader port-forward svc/frontend 8080:80  ->  http://localhost:8080)"
