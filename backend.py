"""Flask backend that replaces the Dash app in `dash_test.py`.

Responsibilities:
 - Create a reading session for a given arXiv (or other) URL (parses HTML via `get_html`).
 - Maintain per-session reading state (div_idx, sentence_idx, speed, play_state).
 - Provide JSON endpoints to fetch current content + context + figure + highlighted HTML.
 - Provide control endpoints (play/pause, next/prev sentence/div, speed +/-).
 - Provide audio endpoint that returns WAV bytes for a given sentence (prefetched in background).
 - Background prefetch thread per session that keeps a rolling cache of upcoming sentences' audio.

Initial version keeps things in-memory (NOT production safe). Future improvements listed later.
"""

from __future__ import annotations

import io
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional

from flask import Flask, jsonify, request, send_file, abort
from flask_cors import CORS

import librosa

from conver_html import get_html  # existing HTML parsing function
from kokoro.interface import KokoroInterface  # existing TTS interface

SAMPLE_RATE = 44100
DEFAULT_SPEED = 1.2
MAX_AUDIO_CACHE = 40  # number of sentence audios to keep in memory per session


@dataclass
class ReadingStatus:
    div_idx: int = 0
    sentence_idx: int = 0
    play_state: str = "PAUSED"  # or PLAY
    speed: float = DEFAULT_SPEED
    created_at: float = field(default_factory=time.time)


class ReadingSession:
    """Holds all state for a single reading session."""

    def __init__(self, url: str):
        self.id = str(uuid.uuid4())
        self.url = self._normalize_url(url)
        self.div_ids_list, self.div_ids_dict = get_html(url=self.url)
        self.status = ReadingStatus()
        self.tts = KokoroInterface(voice_name="am")  # could parameterize
        self.audio_cache: Dict[Tuple[int, int], bytes] = {}
        self.cache_lock = threading.Lock()
        self.shutdown_flag = False
        self.prefetch_thread = threading.Thread(target=self._prefetch_loop, daemon=True)
        self.prefetch_thread.start()

    # ------------- URL Normalization -------------
    def _normalize_url(self, url: str) -> str:
        if "/abs/" in url:
            return url.replace("/abs/", "/html/")
        if "/pdf/" in url:
            return url.replace("/pdf/", "/html/")
        if "/ps/" in url:
            return url.replace("/ps/", "/html/")
        return url

    # ------------- Helpers replicating dash_test logic -------------
    def incr_sentence_idx(self, div_idx: int, sentence_idx: int) -> Tuple[int, int]:
        div_id = self.div_ids_list[div_idx]
        sentences = self.div_ids_dict[div_id]["sentences"]
        new_sentence_idx = sentence_idx + 1
        new_div_idx = div_idx
        if new_sentence_idx >= len(sentences):
            new_sentence_idx = 0
            new_div_idx += 1
        if new_div_idx >= len(self.div_ids_list):
            return div_idx, new_sentence_idx
        # skip empty sentence divs
        while (
            new_div_idx < len(self.div_ids_list)
            and len(self.div_ids_dict[self.div_ids_list[new_div_idx]]["sentences"]) == 0
        ):
            new_div_idx += 1
        if new_div_idx >= len(self.div_ids_list):
            new_div_idx = div_idx
        return new_div_idx, new_sentence_idx

    def decr_sentence_idx(self, div_idx: int, sentence_idx: int) -> Tuple[int, int]:
        new_sentence_idx = sentence_idx - 1
        new_div_idx = div_idx
        if new_sentence_idx < 0:
            if new_div_idx > 0:
                new_div_idx -= 1
                div_id = self.div_ids_list[new_div_idx]
                sentences = self.div_ids_dict[div_id]["sentences"]
                new_sentence_idx = max(0, len(sentences) - 1)
            else:
                new_div_idx = 0
                new_sentence_idx = 0
        return new_div_idx, new_sentence_idx

    def incr_div_idx(self, div_idx: int) -> Tuple[int, int]:
        new_div_idx = min(div_idx + 1, len(self.div_ids_list) - 1)
        return new_div_idx, 0

    def decr_div_idx(self, div_idx: int) -> Tuple[int, int]:
        new_div_idx = max(div_idx - 1, 0)
        return new_div_idx, 0

    # ------------- Audio Generation -------------
    def _generate_audio_for(self, div_idx: int, sentence_idx: int) -> Optional[bytes]:
        key = (div_idx, sentence_idx)
        if key in self.audio_cache:
            return self.audio_cache[key]
        if div_idx >= len(self.div_ids_list):
            return None
        div_id = self.div_ids_list[div_idx]
        if div_id == "#end":
            return None
        sentences_spoken = self.div_ids_dict[div_id]["sentences_spoken"]
        sentences = self.div_ids_dict[div_id]["sentences"]
        if sentence_idx >= len(sentences_spoken):
            return None
        sentence_spoken = sentences_spoken[sentence_idx]
        real_sentence = sentences[sentence_idx]
        speed = self.status.speed
        if real_sentence.count("$") > 1:
            speed *= 0.8
        try:
            # KokoroInterface.generate_audio expects integral speed? Cast conservatively
            wav = self.tts.generate_audio(sentence_spoken, speed=int(round(speed)))
            # Original assumed wav is 24000 sr
            wav_resampled = librosa.resample(wav, orig_sr=24000, target_sr=SAMPLE_RATE)
            cut_off = int(12000 * (1 / self.status.speed))
            trimmed = wav_resampled[cut_off:-cut_off] if len(wav_resampled) > 2 * cut_off else wav_resampled
            # Convert to WAV bytes
            import soundfile as sf  # local import to avoid global dependency issues

            bio = io.BytesIO()
            sf.write(bio, trimmed, SAMPLE_RATE, format="WAV")
            bio.seek(0)
            data = bio.read()
            with self.cache_lock:
                if len(self.audio_cache) > MAX_AUDIO_CACHE:
                    # simple eviction: pop oldest key
                    first_key = next(iter(self.audio_cache))
                    self.audio_cache.pop(first_key, None)
                self.audio_cache[key] = data
            return data
        except Exception:
            return None

    def _prefetch_loop(self):
        # Continuously attempt to prefetch a few sentences ahead while session active
        while not self.shutdown_flag:
            current_div = self.status.div_idx
            current_sent = self.status.sentence_idx
            # prefetch next N
            N = 5
            d, s = current_div, current_sent
            for _ in range(N):
                d, s = self.incr_sentence_idx(d, s)
                if (d, s) not in self.audio_cache:
                    self._generate_audio_for(d, s)
            time.sleep(0.5)

    # ------------- Content Packaging -------------
    def get_current_payload(self) -> Dict:
        if self.status.div_idx >= len(self.div_ids_list):
            return {"end": True}
        div_id = self.div_ids_list[self.status.div_idx]
        if div_id == "#end":
            return {"end": True}
        sentences = self.div_ids_dict[div_id]["sentences"]
        highlighted_list = self.div_ids_dict[div_id]["highlighted_html"]
        figure_html = self.div_ids_dict[div_id]["figure"]
        prev_html = self.div_ids_dict[div_id]["prev_html"]
        next_html = self.div_ids_dict[div_id]["next_html"]
        sent_idx = self.status.sentence_idx
        sent_idx = min(sent_idx, len(sentences) - 1)
        # sentence window (current +/- 1)
        window_prev = sentences[sent_idx - 1] if sent_idx - 1 >= 0 else ""
        window_curr = sentences[sent_idx] if sent_idx < len(sentences) else ""
        window_next = sentences[sent_idx + 1] if sent_idx + 1 < len(sentences) else ""
        html_sentences = f"{window_prev}\n<br><b>{window_curr}</b>\n<br>{window_next}\n" if window_curr else ""
        is_title = sent_idx == 0 and window_curr.strip() == self.div_ids_dict[div_id]["title"].strip()
        return {
            "session_id": self.id,
            "url": self.url,
            "div_idx": self.status.div_idx,
            "sentence_idx": sent_idx,
            "play_state": self.status.play_state,
            "speed": self.status.speed,
            "sec_title": self.div_ids_dict[div_id]["title"][:100],
            "is_title": is_title,
            "html_content": highlighted_list[sent_idx],
            "figure_html": figure_html,
            "prev_html": prev_html,
            "next_html": next_html,
            "sentences_window_html": html_sentences,
            "has_audio_cached": (self.status.div_idx, sent_idx) in self.audio_cache,
            "end": False,
        }

    # ------------- Navigation / Control -------------
    def control(self, action: str):
        if action == "play_pause":
            self.status.play_state = "PAUSED" if self.status.play_state == "PLAY" else "PLAY"
        elif action == "next_sentence":
            self.status.div_idx, self.status.sentence_idx = self.incr_sentence_idx(
                self.status.div_idx, self.status.sentence_idx
            )
        elif action == "prev_sentence":
            self.status.div_idx, self.status.sentence_idx = self.decr_sentence_idx(
                self.status.div_idx, self.status.sentence_idx
            )
        elif action == "next_div":
            self.status.div_idx, self.status.sentence_idx = self.incr_div_idx(self.status.div_idx)
        elif action == "prev_div":
            self.status.div_idx, self.status.sentence_idx = self.decr_div_idx(self.status.div_idx)
        else:
            return False
        return True

    def adjust_speed(self, delta: float):
        self.status.speed = max(0.5, min(2.0, round(self.status.speed + delta, 2)))
        # clear cache so audio regenerated at new speed
        with self.cache_lock:
            self.audio_cache.clear()


# ------------------ Flask App Factory ------------------


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    sessions: Dict[str, ReadingSession] = {}

    def get_session_or_404(session_id: str) -> ReadingSession:
        sess = sessions.get(session_id)
        if not sess:
            abort(404, description="Session not found")
        return sess

    @app.route("/api/session", methods=["POST"])
    def create_session():
        data = request.get_json(force=True)
        url = data.get("url")
        if not url:
            return jsonify({"error": "url required"}), 400
        sess = ReadingSession(url=url)
        sessions[sess.id] = sess
        return jsonify({"session_id": sess.id, "url": sess.url})

    @app.route("/api/session/<session_id>/state", methods=["GET"])
    def get_state(session_id: str):
        sess = get_session_or_404(session_id)
        return jsonify(sess.get_current_payload())

    @app.route("/api/session/<session_id>/control", methods=["POST"])
    def control(session_id: str):
        sess = get_session_or_404(session_id)
        data = request.get_json(force=True)
        action = data.get("action")
        if action in {"speed_inc", "speed_dec"}:
            delta = 0.1 if action == "speed_inc" else -0.1
            sess.adjust_speed(delta)
            return jsonify({"ok": True, "speed": sess.status.speed})
        ok = sess.control(action)
        if not ok:
            return jsonify({"error": "Unknown action"}), 400
        return jsonify({"ok": True})

    @app.route("/api/session/<session_id>/audio", methods=["GET"])
    def get_audio(session_id: str):
        sess = get_session_or_404(session_id)
        try:
            div_idx = int(request.args.get("div_idx", sess.status.div_idx))
            sentence_idx = int(request.args.get("sentence_idx", sess.status.sentence_idx))
        except ValueError:
            return jsonify({"error": "Invalid indices"}), 400
        key = (div_idx, sentence_idx)
        with sess.cache_lock:
            data = sess.audio_cache.get(key)
        if data is None:
            # attempt synchronous generation
            data = sess._generate_audio_for(div_idx, sentence_idx)
        if data is None:
            return jsonify({"error": "Audio not available"}), 404
        return send_file(io.BytesIO(data), mimetype="audio/wav", as_attachment=False, download_name="audio.wav")

    @app.route("/api/session/<session_id>", methods=["DELETE"])
    def delete_session(session_id: str):
        sess = sessions.pop(session_id, None)
        if not sess:
            return jsonify({"error": "Not found"}), 404
        sess.shutdown_flag = True
        return jsonify({"ok": True})

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "sessions": len(sessions)})

    return app


if __name__ == "__main__":
    # Development entrypoint
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=True)
