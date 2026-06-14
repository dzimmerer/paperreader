"""Parsing/serving backend for the Paper Reader app (default port 5101).

Responsibilities:
  - Accept a URL (arXiv or generic, HTML or PDF) or an uploaded PDF, parse it
    via ``parsing.load_document`` and keep the document in memory.
  - Serve the structured document JSON to the frontend.
  - For each sentence, fetch synthesized audio from the TTS backend
    (``tts_server.py``), estimate per-word timings from the audio duration and
    the per-word weights, cache the result, and prefetch upcoming sentences.
  - Serve the static frontend from ./frontend.

API:
    POST /api/doc                      {"url": ...}  or multipart "file" (PDF)
    GET  /api/doc/<doc_id>             full document JSON
    GET  /api/doc/<doc_id>/audio/<n>   {"audio_b64", "duration", "timings": [{start, end}]}
    GET  /api/health                   backend + TTS service status
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from typing import Any, Optional

import requests
from flask import Flask, Response, abort, jsonify, request, send_from_directory
from flask_cors import CORS

from parsing import load_document

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(APP_DIR, "frontend")

PORT = int(os.environ.get("READER_PORT", "5101"))
TTS_URL = os.environ.get("TTS_URL", "http://localhost:5102")
TTS_TIMEOUT = 180
PREFETCH_AHEAD = 3

# Cap the on-disk store so it can't fill the disk. Oldest (least-recently-used)
# documents are evicted when either limit is exceeded.
MAX_DOCS = int(os.environ.get("READER_MAX_DOCS", "50"))
MAX_STORE_BYTES = int(os.environ.get("READER_MAX_STORE_BYTES", str(5 * 1024**3)))  # 5 GiB

# Per-word constant overhead (in weight units) so short words still get time
WORD_BASE_WEIGHT = 2.0
# Estimated leading silence in the synthesized audio (seconds)
LEAD_PAD = 0.05

# Documents, images, and per-sentence audio live on a shared filesystem (not in
# process memory) so multiple gunicorn workers see the same data and a restart
# doesn't lose loaded papers. Workers in one container share this directory.
DATA_DIR = os.environ.get("READER_DATA_DIR") or os.path.join(tempfile.gettempdir(), "paperreader_docs")
os.makedirs(DATA_DIR, exist_ok=True)

# Avoid two threads/workers synthesizing the same sentence concurrently.
_inflight_lock = threading.Lock()


# doc_ids are uuid4().hex[:12]; validate strictly before using them in a path so
# a crafted id (e.g. "..%2f..") can't escape DATA_DIR (path traversal).
_DOC_ID_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")


def _valid_doc_id(doc_id: str) -> bool:
    return bool(_DOC_ID_RE.match(doc_id))


def _doc_dir(doc_id: str) -> str:
    if not _valid_doc_id(doc_id):
        raise ValueError("invalid doc_id")
    return os.path.join(DATA_DIR, doc_id)


def _audio_path(doc_id: str, idx: int) -> str:
    return os.path.join(_doc_dir(doc_id), "audio", f"{idx}.json")


def _load_json(path: str) -> Optional[Any]:
    try:
        with open(path, "rb") as f:
            return json.loads(f.read())
    except Exception:
        return None


def _atomic_write_bytes(path: str, data: bytes) -> None:
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _atomic_write_json(path: str, obj: Any) -> None:
    _atomic_write_bytes(path, json.dumps(obj).encode())


def store_add(doc: dict[str, Any]) -> None:
    """Persist a parsed document (JSON), its flat sentence list, and images."""
    images = doc.pop("_images", [])
    flat: list[dict[str, Any]] = []
    for block in doc["blocks"]:
        flat.extend(block["sentences"])
    flat.sort(key=lambda s: s["idx"])

    d = _doc_dir(doc["doc_id"])
    os.makedirs(os.path.join(d, "audio"), exist_ok=True)
    manifest = []
    for i, img in enumerate(images):
        _atomic_write_bytes(os.path.join(d, f"img_{i}.bin"), img["data"])
        manifest.append({"mime": img["mime"]})
    _atomic_write_json(os.path.join(d, "images.json"), manifest)
    _atomic_write_json(os.path.join(d, "flat.json"), flat)
    # Write doc.json last: its presence marks the document as fully stored.
    _atomic_write_json(os.path.join(d, "doc.json"), doc)
    evict_if_needed()


def _dir_size(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def touch_doc(doc_id: str) -> None:
    """Mark a document as recently used (for LRU eviction)."""
    try:
        os.utime(_doc_dir(doc_id), None)
    except OSError:
        pass


def evict_if_needed() -> None:
    """Delete least-recently-used documents until under the count/size caps."""
    try:
        entries = []
        total = 0
        for name in os.listdir(DATA_DIR):
            d = os.path.join(DATA_DIR, name)
            if not os.path.isdir(d):
                continue
            size = _dir_size(d)
            total += size
            entries.append((os.path.getmtime(d), size, d))
        entries.sort()  # oldest mtime first
        count = len(entries)
        i = 0
        while (count > MAX_DOCS or total > MAX_STORE_BYTES) and i < len(entries) - 1:
            _mtime, size, d = entries[i]
            import shutil

            shutil.rmtree(d, ignore_errors=True)
            total -= size
            count -= 1
            i += 1
    except FileNotFoundError:
        pass


def store_doc(doc_id: str) -> Optional[dict[str, Any]]:
    return _load_json(os.path.join(_doc_dir(doc_id), "doc.json"))


def store_flat(doc_id: str) -> Optional[list[dict[str, Any]]]:
    return _load_json(os.path.join(_doc_dir(doc_id), "flat.json"))


def store_image(doc_id: str, n: int) -> Optional[tuple[str, bytes]]:
    manifest = _load_json(os.path.join(_doc_dir(doc_id), "images.json"))
    if not isinstance(manifest, list) or n < 0 or n >= len(manifest):
        return None
    bin_path = os.path.join(_doc_dir(doc_id), f"img_{n}.bin")
    if not os.path.exists(bin_path):
        return None
    with open(bin_path, "rb") as f:
        return manifest[n]["mime"], f.read()


def estimate_timings(weights: list[float], duration: float) -> list[dict[str, float]]:
    """Distribute the audio duration over words proportionally to their weights."""
    speakable = max(duration - LEAD_PAD, 0.05)
    total = sum(w + WORD_BASE_WEIGHT for w in weights) or 1.0
    t = LEAD_PAD
    timings: list[dict[str, float]] = []
    for w in weights:
        dt = speakable * (w + WORD_BASE_WEIGHT) / total
        timings.append({"start": round(t, 3), "end": round(t + dt, 3)})
        t += dt
    return timings


def generate_audio_entry(doc_id: str, idx: int) -> Optional[dict[str, Any]]:
    """Return cached audio+timings for sentence ``idx`` or synthesize it.

    Cached on the shared filesystem. A lock-directory claim makes generation
    safe across threads and gunicorn worker processes: whoever creates the lock
    dir synthesizes; others wait for the result file to appear.
    """
    path = _audio_path(doc_id, idx)
    cached = _load_json(path)
    if cached is not None:
        return cached

    flat = store_flat(doc_id)
    if flat is None or idx < 0 or idx >= len(flat):
        return None

    lock = path + ".lock"
    claimed = False
    try:
        os.mkdir(lock)  # atomic across processes
        claimed = True
    except FileExistsError:
        claimed = False
    except FileNotFoundError:
        return None  # doc dir vanished

    if not claimed:
        for _ in range(900):  # ~180s
            result = _load_json(path)
            if result is not None:
                return result
            if not os.path.exists(lock):
                break
            time.sleep(0.2)
        return _load_json(path)

    try:
        with _inflight_lock:
            pass  # (intra-process serialization handled by the lock dir)
        sentence = flat[idx]
        resp = requests.post(
            f"{TTS_URL}/tts",
            json={"text": sentence["spoken"], "speed": 1.0},
            timeout=TTS_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "audio_b64" not in payload:
            return None
        result = {
            "idx": idx,
            "audio_b64": payload["audio_b64"],
            "duration": payload["duration"],
            "timings": estimate_timings(sentence["weights"], payload["duration"]),
        }
        _atomic_write_json(path, result)
        return result
    except Exception as exc:
        print(f"[server] audio generation failed for {doc_id}#{idx}: {exc}")
        return None
    finally:
        try:
            os.rmdir(lock)
        except OSError:
            pass


def prefetch(doc_id: str, start_idx: int) -> None:
    flat = store_flat(doc_id)
    if flat is None:
        return
    total = len(flat)

    def _run() -> None:
        for idx in range(start_idx, min(start_idx + PREFETCH_AHEAD, total)):
            if not os.path.exists(_audio_path(doc_id, idx)):
                generate_audio_entry(doc_id, idx)

    threading.Thread(target=_run, daemon=True).start()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    # Cap request bodies (PDF uploads) as defense-in-depth behind nginx's limit.
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024
    CORS(app)

    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/api/doc", methods=["POST"])
    def create_doc():
        try:
            if request.files.get("file"):
                upload = request.files["file"]
                doc = load_document(pdf_bytes=upload.read(), filename=upload.filename or "upload.pdf")
            else:
                data = request.get_json(force=True, silent=True) or {}
                url = (data.get("url") or "").strip()
                if not url:
                    return jsonify({"error": "url (or a PDF file upload) is required"}), 400
                doc = load_document(url=url)
        except Exception as exc:
            return jsonify({"error": f"Failed to load document: {exc}"}), 422
        store_add(doc)
        prefetch(doc["doc_id"], 0)
        return jsonify(doc)

    @app.route("/api/doc/<doc_id>", methods=["GET"])
    def get_doc(doc_id: str):
        if not _valid_doc_id(doc_id):
            abort(404, description="Document not found")
        doc = store_doc(doc_id)
        if doc is None:
            abort(404, description="Document not found")
        touch_doc(doc_id)
        return jsonify(doc)

    @app.route("/api/doc/<doc_id>/img/<int:n>", methods=["GET"])
    def get_image(doc_id: str, n: int):
        if not _valid_doc_id(doc_id):
            abort(404, description="Image not found")
        img = store_image(doc_id, n)
        if img is None:
            abort(404, description="Image not found")
        mime, data = img
        return Response(data, mimetype=mime)

    @app.route("/api/doc/<doc_id>/audio/<int:idx>", methods=["GET"])
    def get_audio(doc_id: str, idx: int):
        if not _valid_doc_id(doc_id):
            abort(404, description="Document not found")
        flat = store_flat(doc_id)
        if flat is None:
            abort(404, description="Document not found")
        if idx < 0 or idx >= len(flat):
            return jsonify({"error": "sentence index out of range"}), 404
        touch_doc(doc_id)
        result = generate_audio_entry(doc_id, idx)
        prefetch(doc_id, idx + 1)
        if result is None:
            return jsonify({"error": "audio not available (is the TTS server running?)"}), 503
        return jsonify(result)

    @app.route("/api/health", methods=["GET"])
    def health():
        tts_status: dict[str, Any] = {"status": "unreachable"}
        try:
            tts_status = requests.get(f"{TTS_URL}/health", timeout=3).json()
        except Exception:
            pass
        return jsonify({"status": "ok", "tts": tts_status})

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
