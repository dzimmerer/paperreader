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
| tts       | `paperreader-tts`      | 5102 | Kokoro neural voices (CPU) by default; espeak-ng opt-in |

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

## TTS engine & device

The `tts` image ships **Kokoro** neural voices by default (`Dockerfile.tts`
bundles `kokoro/` weights + voice packs; `Dockerfile.tts.dockerignore` keeps
them in the build context while the root `.dockerignore` excludes them from the
backend/frontend images). Configure via env in `k8s/tts.yaml`:

| Env | Default | Notes |
|-----|---------|-------|
| `TTS_ENGINE` | `kokoro` | `kokoro`, `espeak`, or `say` (macOS host only) |
| `TTS_VOICE`  | `af_sarah` | any pack in `kokoro/voices/` (e.g. `am_adam`, `bf_emma`) |
| `TTS_DEVICE` | `cpu` | `cpu`, `cuda`, or `mps`; `auto` → cuda-if-present else cpu |

The `kokoro/voices/*.pt` packs and `kokoro-v0_19.pth` are git-ignored, so make
sure they exist locally before building — they must be in the build context.

### Why CPU (and the GPU story)

Inside minikube there is **no GPU**: Docker Desktop's Linux VM exposes neither
Apple Metal/MPS nor NVIDIA, so the pod runs Kokoro on CPU. On Apple Silicon CPU
is in fact the *fastest* option for Kokoro anyway — its iSTFT vocoder calls
`aten::angle`, which the MPS backend doesn't implement, so forcing `TTS_DEVICE=mps`
(with `PYTORCH_ENABLE_MPS_FALLBACK=1`) ends up **slower** than CPU due to per-op
CPU round-trips. `tts_server.py` will try the requested device and fall back to
CPU automatically if an op is unsupported.

To actually accelerate Kokoro you need a **CUDA** GPU: install a CUDA torch
build in `Dockerfile.tts`, expose the GPU to the cluster (e.g. the NVIDIA device
plugin), and set `TTS_DEVICE=cuda`. For Apple-Silicon GPU you'd have to run the
TTS process *natively on macOS* (outside minikube) — out of scope for this
in-cluster deployment.

To skip the model entirely, set `TTS_ENGINE=espeak` (tiny, no weights needed).
