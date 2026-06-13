# Deploying Paper Reader on Kubernetes (minikube)

The app runs as **three containers**, orchestrated by Kubernetes:

```
                 ┌─────────────────────────────────────────────┐
  browser ──▶ NodePort 30080 ──▶ frontend (nginx)               │
                                   │  static files               │
                                   │  /api/*  ──proxy──▶ backend  │  :5101
                                   └──────────────────────│──────┘
                                                          backend ──▶ tts  :5102
                                       (parse + serve + cache)   (synthesize)
```

| Component | Image | Port | Notes |
|-----------|-------|------|-------|
| frontend  | `paperreader-frontend` (nginx) | 80 (NodePort 30080) | serves the SPA, reverse-proxies `/api/` to `backend` |
| backend   | `paperreader-backend`  | 5101 | parsing/serving API; `TTS_URL=http://tts:5102` |
| tts       | `paperreader-tts`      | 5102 | espeak-ng engine by default |

nginx proxying `/api/` to the backend means the browser sees a single origin —
no CORS, and the frontend's relative URLs work unchanged.

## Quick start

```bash
cd reader_app
./deploy.sh
minikube service frontend -n paperreader   # opens the app in your browser
```

`deploy.sh` starts minikube if needed, builds the three images **inside
minikube's Docker daemon** (`eval $(minikube docker-env)`, so no registry is
required), applies the manifests in `k8s/`, and waits for the rollouts.

Re-run `./deploy.sh` after any code change — it rebuilds and restarts the pods.

## Manual steps (what the script does)

```bash
minikube start
eval "$(minikube docker-env)"                       # build into the cluster's daemon

docker build -t paperreader-tts:latest      -f Dockerfile.tts      ..
docker build -t paperreader-backend:latest  -f Dockerfile.backend  ..
docker build -t paperreader-frontend:latest -f Dockerfile.frontend ..

kubectl apply -f k8s/                                # namespace + 3 deploy/svc
kubectl -n paperreader get pods
minikube service frontend -n paperreader
```

Because images are built into minikube's daemon and tagged `:latest`, the
manifests use `imagePullPolicy: IfNotPresent` — no external registry needed.

## Inspecting / tearing down

```bash
kubectl -n paperreader get pods,svc
kubectl -n paperreader logs deploy/backend
kubectl -n paperreader logs deploy/tts

kubectl delete namespace paperreader        # remove everything
```

## Notes

- **State is in-memory.** The backend keeps parsed documents and the audio
  cache in process memory, so it runs as a single replica; deleting the pod
  clears loaded papers.
- **PDF uploads / long TTS calls.** nginx is configured with
  `client_max_body_size 64m` and a 300s proxy read timeout to accommodate
  large PDFs and first-request synthesis latency.

## Using neural Kokoro voices instead of espeak

The default `tts` image uses **espeak-ng** so the deployment works anywhere with
no model download. To use the higher-quality Kokoro voices:

1. Build a Kokoro-enabled image. Add `torch`, `phonemizer`, `munch` to the pip
   install and copy the model into the image (the build context is the repo
   root, so adjust `.dockerignore` to stop excluding `kokoro/`):

   ```dockerfile
   # Dockerfile.tts-kokoro (sketch)
   FROM python:3.11-slim
   RUN apt-get update && apt-get install -y --no-install-recommends \
         espeak-ng libsndfile1 git && rm -rf /var/lib/apt/lists/*
   RUN pip install --no-cache-dir flask flask-cors numpy soundfile \
         torch --index-url https://download.pytorch.org/whl/cpu
   RUN pip install --no-cache-dir phonemizer munch
   COPY kokoro/ /app/kokoro/
   COPY reader_app/tts_server.py /app/reader_app/tts_server.py
   WORKDIR /app/reader_app
   ENV TTS_ENGINE=kokoro TTS_VOICE=af_sarah
   CMD ["python", "tts_server.py"]
   ```

   The `kokoro/voices/*.pt` packs are git-ignored — make sure they exist locally
   before building, since they must be in the build context.

2. Point `k8s/tts.yaml` at the new image and set `TTS_ENGINE=kokoro`.

Note: without a GPU (minikube runs on CPU) Kokoro synthesis is much slower than
espeak; the backend's prefetching hides some of this latency.
