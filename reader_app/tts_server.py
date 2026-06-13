"""Standalone TTS backend for the Paper Reader app.

Exposes a tiny REST API (default port 5102):

    GET  /health -> {"status": "ok", "engine": "<name>"}
    POST /tts    -> body {"text": str, "speed": float?, "voice": str?}
                    returns {"audio_b64": str (WAV), "sample_rate": int, "duration": float}

Engine selection (env var ``TTS_ENGINE`` or auto-detect, in order):
    kokoro  - neural TTS using the Kokoro weights shipped in this repo
    say     - macOS built-in speech synthesis (no extra deps)
    espeak  - espeak-ng command-line synthesiser

Run from anywhere; Kokoro paths resolve against the repo root.
"""

from __future__ import annotations

import base64
import io
import os
import subprocess
import sys
import tempfile
import threading
from typing import Optional, Protocol

import numpy as np
import soundfile as sf
from flask import Flask, jsonify, request
from flask_cors import CORS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEFAULT_PORT = int(os.environ.get("TTS_PORT", "5102"))

# Serialise synthesis: neural engines are not safe for concurrent GPU access.
_GENERATE_LOCK = threading.Lock()


class TTSEngine(Protocol):
    name: str

    def synthesize(self, text: str, speed: float, voice: Optional[str]) -> tuple[bytes, int, float]:
        """Return (wav_bytes, sample_rate, duration_seconds)."""
        ...


def _wav_bytes(audio: np.ndarray, sample_rate: int) -> tuple[bytes, float]:
    bio = io.BytesIO()
    sf.write(bio, audio, sample_rate, format="WAV")
    return bio.getvalue(), len(audio) / float(sample_rate)


class KokoroEngine:
    name = "kokoro"

    def __init__(self, voice_name: str = "af_sarah") -> None:
        # KokoroInterface loads weights via paths relative to the repo root
        os.chdir(REPO_ROOT)
        from kokoro.interface import KokoroInterface

        self._tts = KokoroInterface(voice_name=voice_name)
        self._trim_db = 35

    def synthesize(self, text: str, speed: float, voice: Optional[str]) -> tuple[bytes, int, float]:
        audio = self._tts.generate_audio(text, speed=speed)
        audio = np.asarray(audio, dtype=np.float32)
        audio = self._trim_silence(audio)
        wav, duration = _wav_bytes(audio, self._tts.sample_rate)
        return wav, self._tts.sample_rate, duration

    def _trim_silence(self, audio: np.ndarray, frame: int = 512) -> np.ndarray:
        """Trim leading/trailing silence so word-timing estimates line up."""
        if audio.size < 4 * frame:
            return audio
        rms = np.sqrt(np.mean(audio[: len(audio) // frame * frame].reshape(-1, frame) ** 2, axis=1))
        threshold = max(rms.max(), 1e-6) * 10 ** (-self._trim_db / 20)
        keep = np.where(rms > threshold)[0]
        if keep.size == 0:
            return audio
        start = keep[0] * frame
        end = min((keep[-1] + 2) * frame, len(audio))
        return audio[start:end]


class SayEngine:
    """macOS built-in `say` command (CoreSpeech). Zero extra dependencies."""

    name = "say"
    BASE_WPM = 185

    def synthesize(self, text: str, speed: float, voice: Optional[str]) -> tuple[bytes, int, float]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            cmd = ["say", "-o", tmp_path, "--data-format=LEI16@22050", "-r", str(int(self.BASE_WPM * speed))]
            if voice:
                cmd += ["-v", voice]
            cmd.append(text)
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            audio, sample_rate = sf.read(tmp_path, dtype="float32")
        finally:
            os.unlink(tmp_path)
        wav, duration = _wav_bytes(audio, sample_rate)
        return wav, sample_rate, duration


class EspeakEngine:
    name = "espeak"
    BASE_WPM = 175

    def synthesize(self, text: str, speed: float, voice: Optional[str]) -> tuple[bytes, int, float]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            cmd = ["espeak-ng", "-w", tmp_path, "-s", str(int(self.BASE_WPM * speed))]
            if voice:
                cmd += ["-v", voice]
            cmd.append(text)
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            audio, sample_rate = sf.read(tmp_path, dtype="float32")
        finally:
            os.unlink(tmp_path)
        wav, duration = _wav_bytes(audio, sample_rate)
        return wav, sample_rate, duration


def build_engine() -> TTSEngine:
    requested = os.environ.get("TTS_ENGINE", "auto").lower()
    voice = os.environ.get("TTS_VOICE", "")

    if requested in ("kokoro", "auto"):
        try:
            engine = KokoroEngine(voice_name=voice or "af_sarah")
            print("[tts] Using Kokoro engine")
            return engine
        except Exception as exc:
            if requested == "kokoro":
                raise
            print(f"[tts] Kokoro unavailable ({exc!r}), falling back")

    if requested in ("say", "auto") and sys.platform == "darwin":
        print("[tts] Using macOS `say` engine")
        return SayEngine()

    print("[tts] Using espeak-ng engine")
    return EspeakEngine()


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    engine = build_engine()

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "engine": engine.name})

    @app.route("/tts", methods=["POST"])
    def tts():
        data = request.get_json(force=True, silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "text required"}), 400
        speed = float(data.get("speed", 1.0))
        voice = data.get("voice") or None
        try:
            with _GENERATE_LOCK:
                wav, sample_rate, duration = engine.synthesize(text, speed, voice)
        except Exception as exc:
            return jsonify({"error": f"TTS failed: {exc}"}), 500
        return jsonify(
            {
                "audio_b64": base64.b64encode(wav).decode("ascii"),
                "sample_rate": sample_rate,
                "duration": round(duration, 3),
                "engine": engine.name,
            }
        )

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=DEFAULT_PORT, debug=False, threaded=True)
