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

import os
import threading
from collections import OrderedDict
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
MAX_AUDIO_CACHE = 80
PREFETCH_AHEAD = 3

# Per-word constant overhead (in weight units) so short words still get time
WORD_BASE_WEIGHT = 2.0
# Estimated leading silence in the synthesized audio (seconds)
LEAD_PAD = 0.05


class DocumentStore:
    """In-memory documents plus per-sentence audio cache and prefetching."""

    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add(self, doc: dict[str, Any]) -> None:
        images = doc.pop("_images", [])  # keep binary data out of the JSON doc
        flat: list[dict[str, Any]] = []
        for block in doc["blocks"]:
            flat.extend(block["sentences"])
        flat.sort(key=lambda s: s["idx"])
        with self._lock:
            self._docs[doc["doc_id"]] = {
                "doc": doc,
                "flat": flat,
                "images": images,
                "audio": OrderedDict(),
                "inflight": set(),
                "audio_lock": threading.Lock(),
            }

    def get(self, doc_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            return self._docs.get(doc_id)


STORE = DocumentStore()


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


def generate_audio_entry(entry: dict[str, Any], idx: int) -> Optional[dict[str, Any]]:
    """Fetch TTS audio for sentence ``idx`` and attach word timings (cached)."""
    with entry["audio_lock"]:
        if idx in entry["audio"]:
            return entry["audio"][idx]
        if idx in entry["inflight"]:
            inflight = True
        else:
            entry["inflight"].add(idx)
            inflight = False
    if inflight:
        # Another thread is generating it; wait briefly for the result
        for _ in range(600):
            with entry["audio_lock"]:
                if idx in entry["audio"]:
                    return entry["audio"][idx]
                if idx not in entry["inflight"]:
                    break
            threading.Event().wait(0.2)
        return None

    try:
        if idx < 0 or idx >= len(entry["flat"]):
            return None
        sentence = entry["flat"][idx]
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
        with entry["audio_lock"]:
            entry["audio"][idx] = result
            while len(entry["audio"]) > MAX_AUDIO_CACHE:
                entry["audio"].popitem(last=False)
        return result
    except Exception as exc:
        print(f"[server] audio generation failed for sentence {idx}: {exc}")
        return None
    finally:
        with entry["audio_lock"]:
            entry["inflight"].discard(idx)


def prefetch(entry: dict[str, Any], start_idx: int) -> None:
    def _run() -> None:
        for idx in range(start_idx, min(start_idx + PREFETCH_AHEAD, len(entry["flat"]))):
            with entry["audio_lock"]:
                cached = idx in entry["audio"] or idx in entry["inflight"]
            if not cached:
                generate_audio_entry(entry, idx)

    threading.Thread(target=_run, daemon=True).start()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
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
        STORE.add(doc)
        entry = STORE.get(doc["doc_id"])
        if entry is not None:
            prefetch(entry, 0)
        return jsonify(doc)

    @app.route("/api/doc/<doc_id>", methods=["GET"])
    def get_doc(doc_id: str):
        entry = STORE.get(doc_id)
        if entry is None:
            abort(404, description="Document not found")
        return jsonify(entry["doc"])

    @app.route("/api/doc/<doc_id>/img/<int:n>", methods=["GET"])
    def get_image(doc_id: str, n: int):
        entry = STORE.get(doc_id)
        if entry is None:
            abort(404, description="Document not found")
        if n < 0 or n >= len(entry["images"]):
            abort(404, description="Image not found")
        img = entry["images"][n]
        return Response(img["data"], mimetype=img["mime"])

    @app.route("/api/doc/<doc_id>/audio/<int:idx>", methods=["GET"])
    def get_audio(doc_id: str, idx: int):
        entry = STORE.get(doc_id)
        if entry is None:
            abort(404, description="Document not found")
        if idx < 0 or idx >= len(entry["flat"]):
            return jsonify({"error": "sentence index out of range"}), 404
        result = generate_audio_entry(entry, idx)
        prefetch(entry, idx + 1)
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
