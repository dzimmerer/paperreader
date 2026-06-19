# Legacy code

This directory holds the **classic stack** and earlier prototypes of Paper Reader,
preserved for reference. For new use, prefer the modern deployable stack in
[`../reader_app/`](../reader_app/) (word-level highlighting, PDF uploads,
Docker/Kubernetes, hardened fetching).

## What's here

| Path                       | What it is                                                          |
|----------------------------|---------------------------------------------------------------------|
| `backend.py`               | Classic Flask backend — sentence highlighting, in-memory sessions (`:5001`) |
| `conver_html.py`           | arXiv-HTML → sentences / figures / highlighted HTML (used by `backend.py` and the Dash apps) |
| `frontend/`                | Vite + React SPA — sentence highlighting, polls the backend          |
| `dash_test.py`             | Original Dash UI (Kokoro / OpenAI-compatible TTS)                    |
| `dash_remote.py`           | Dash UI variant using Coqui TTS                                      |
| `chatterbox/interface.py`  | Chatterbox TTS via Apple MLX (used by `backend.py`)                  |
| `local_tts_interface.py`   | OpenAI-compatible REST TTS client (used by `dash_test.py`)           |
| `assets/`                  | Dash static assets (`custom.css`, `custom.js`)                       |
| `test.py`                  | Early markdown → HTML + MathJax experiment                           |
| `test_kokoro.py`           | Early Kokoro generation + playback experiment                        |
| `tts_test.py`              | Early Coqui TTS experiment                                           |
| `requirements.txt`         | Classic-stack Python deps (Flask + torch + MLX)                      |

## Running the classic stack

The entry points (`backend.py`, `dash_test.py`, `dash_remote.py`, `test_kokoro.py`)
add the repo root to `sys.path` and `chdir` into it on startup, so the shared
`kokoro/` model resolves; `conver_html.py` additionally adds `reader_app/` to the
path so the shared `mathtex2text.py` (which lives in `reader_app/`) resolves too.

```bash
# from the repo root
python -m venv .venv && source .venv/bin/activate
pip install -r legacy/requirements.txt

# 1) download kokoro-v0_19.pth into ../kokoro/  (voice packs are bundled)

# 2) backend (terminal 1)
python legacy/backend.py                     # :5001

# 3) frontend (terminal 2)
cd legacy/frontend && npm install && npm run dev   # :5173, proxies /api -> :5001
```

### Legacy Dash UI

```bash
pip install dash dash-bootstrap-components dash_dangerously_set_inner_html
python legacy/dash_test.py
```

## Notes

- Sessions and audio caches are **in-memory** — restarting loses everything.
- Highlighting is at the **sentence** level (no per-word highlight); the modern
  stack in `reader_app/` does word-level highlighting.
- `dash_remote.py` and the `test_*.py` scripts depend on extra packages
  (`TTS` / Coqui, `sounddevice`, `soundcard`) not listed in `requirements.txt`.
