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
./deploy.sh                       # all-in-cluster (TTS container, CPU)
minikube service frontend -n paperreader   # opens the app in your browser
```

For **realtime** TTS on Apple Silicon, use native-TTS mode (see below):

```bash
cd reader_app
./deploy.sh --native-tts          # cluster talks to a host TTS
./run-native-tts.sh               # separate terminal — keep running
minikube service frontend -n paperreader
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

## Deploying to a remote Linux server (k3s, public)

On a real x86 Linux box (where CPU Kokoro is realtime — unlike the Apple-Silicon
Docker VM), you can run the whole stack in-cluster and expose it publicly:

```bash
# on the server (needs passwordless sudo), with the app source under ~/paperreader
./reader_app/deploy-server.sh
```

It installs Docker + k3s, builds the three images, imports them into k3s, and
exposes the frontend on **NodePort 30080 behind HTTP basic auth** (user `reader`,
a random password printed at the end / stored in `~/paperreader/.reader_password`).
Open the firewall for 30080 (the script does `ufw allow` if ufw is active; a
provider-level firewall may also need it).

The TTS pod here uses the **public `kokoro` package** (`Dockerfile.tts.pkg`,
`TTS_ENGINE=kokoro-pkg`) which pulls Kokoro-82M weights from HuggingFace at build
time — so no model weights are shipped from a dev machine. `bench_tts.py`
measures the real-time factor on the host.

> Basic auth over plain HTTP sends credentials unencrypted. For real public use,
> front it with TLS (e.g. a domain + cert-manager/Traefik or a reverse proxy).

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

### Realtime: run Kokoro natively (`--native-tts`)

Measured Kokoro speed (real-time factor = wall ÷ audio seconds; lower is faster,
`<1.0` is faster than realtime):

| Where Kokoro runs | RTF | Verdict |
|-------------------|-----|---------|
| In-cluster container (Docker Desktop Linux VM, Apple Silicon) | **~1.7** | slower than realtime → a pause before every sentence |
| Natively on the macOS host (PyTorch + Apple Accelerate) | **~0.21** | ~4.7× realtime → prefetch always stays ahead, no pauses |

The container is slow not because of thread count or CPU limits (raising both
didn't help) but because PyTorch CPU inference in the Linux VM has no access to
Apple's Accelerate/AMX backend and pays virtualization overhead — roughly 7×
slower than the same code run natively.

So for realtime on Apple Silicon, run the TTS **natively** and let the cluster
reach it:

```bash
./deploy.sh --native-tts     # frontend+backend in-cluster; tts = ExternalName
./run-native-tts.sh          # native Kokoro server on the host :5102
```

`k8s/tts-native.yaml` makes the `tts` service an **ExternalName** pointing at
`host.minikube.internal`, so the backend's `TTS_URL=http://tts:5102` transparently
routes to the host process — no backend change needed. Switch back to the
all-in-cluster container with `./deploy.sh` (re-applies `tts.yaml`).

### GPU notes

Inside minikube there is **no GPU** (Docker Desktop's Linux VM exposes neither
Metal/MPS nor NVIDIA). Even natively, Apple's GPU does *not* help Kokoro: its
iSTFT vocoder calls `aten::angle`, unimplemented on MPS, so `TTS_DEVICE=mps`
(with `PYTORCH_ENABLE_MPS_FALLBACK=1`) is *slower* than CPU — native CPU +
Accelerate is the sweet spot. `tts_server.py` tries the requested device and
falls back to CPU if an op is unsupported. A real **CUDA** GPU does help: install
a CUDA torch build and set `TTS_DEVICE=cuda`.

To skip the model entirely, set `TTS_ENGINE=espeak` (tiny, no weights needed).
