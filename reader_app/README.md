# Paper Reader (reader_app)

Reads scientific papers out loud, sentence by sentence, with live highlighting:
the **spoken sentence** is marked light yellow and the **currently spoken word**
dark yellow. Takes an arXiv link (resolved to the parsed HTML version when one
exists, with ar5iv and PDF fallbacks), any article URL, a direct PDF URL, or a
locally uploaded PDF.

## Architecture

Three components:

```
reader_app/
├── tts_server.py    # TTS backend (port 5102): text -> WAV + duration
├── server.py        # Parsing/serving backend (port 5101): document API,
│                    # word-timing estimation, audio cache + prefetch,
│                    # also serves the frontend
├── parsing.py       # URL resolution + arXiv-HTML / generic-HTML / PDF parsing
├── mathtex2text.py  # LaTeX -> spoken English (shared with legacy/)
├── frontend/        # Static website (no build step): rendering, playback,
│                    # play/pause/prev/next, sentence + word highlighting
├── docker/          # Dockerfiles (Dockerfile.{backend,frontend,tts,tts.pkg})
└── deploy/          # Deploy scripts + k8s manifests (see DEPLOY.md)
    ├── deploy.sh  deploy-server.sh  run-native-tts.sh
    └── k8s/
```

Flow: the frontend POSTs a URL (or PDF) to `server.py`, which returns the paper
as structured JSON — blocks of headings / paragraphs / figures, each sentence
split into display words with per-word duration weights (math is expanded to
spoken English via `mathtex2text.py`). On playback the frontend fetches
`/api/doc/<id>/audio/<sentence_idx>`; the backend asks `tts_server.py` to
synthesize the sentence, distributes the returned audio duration over the words
proportionally to their weights, caches the result, and prefetches the next
sentences. The frontend syncs `audio.currentTime` against those word timings in
a `requestAnimationFrame` loop to move the dark-yellow word highlight.

## Running it

Use the `paperreader` conda env (or any env with `requirements.txt` installed):

```bash
# Terminal 1 — TTS backend
python reader_app/tts_server.py

# Terminal 2 — parsing/serving backend + frontend
python reader_app/server.py
```

Open http://localhost:5101 and paste e.g. `https://arxiv.org/abs/2412.06787`,
or click "Open PDF" for a local file.

### TTS engines

`tts_server.py` picks an engine automatically, or set `TTS_ENGINE`:

| engine   | requirements                                            |
|----------|---------------------------------------------------------|
| `kokoro` | repo's `kokoro/` weights + voices, torch, espeak-ng     |
| `say`    | macOS only, built in (default fallback on macOS)        |
| `espeak` | `espeak-ng` on PATH                                     |

`TTS_VOICE` selects a voice (e.g. `af_sarah` for Kokoro, `Samantha` for `say`).
Playback speed is changed client-side via `audio.playbackRate`, so cached audio
stays valid; word timings scale automatically.

## API

- `POST /api/doc` — `{"url": "..."}` or multipart `file` (PDF) → document JSON
- `GET  /api/doc/<doc_id>` — document JSON
- `GET  /api/doc/<doc_id>/audio/<idx>` — `{"audio_b64", "duration", "timings": [{start, end}]}`
- `GET  /api/doc/<doc_id>/img/<n>` — images extracted from an uploaded/parsed PDF
- `GET  /api/health` — backend + TTS status

TTS backend: `POST /tts` `{"text", "speed"?, "voice"?}` →
`{"audio_b64", "sample_rate", "duration"}`; `GET /health`.

## Notes / limitations

- Sessions and audio caches are in-memory; restart clears everything.
- Word timings are estimated proportionally from word lengths (spoken-form
  length for math), not from forced alignment — close, not exact.
- Math is rendered client-side with KaTeX (CDN); without network access it
  falls back to showing the raw `$latex$` source. Long standalone equations
  render as centered, horizontally scrollable blocks.
- PDFs are parsed with pymupdf4llm (layout-aware: headings from font sizes,
  multi-column text, images at their true positions, automatic OCR of
  image-only pages when Tesseract is installed), with a plain pypdf
  line-heuristic parser as fallback. markitdown was evaluated too but produced
  flat, heading-less text with broken word spacing on papers.
- Figures: arXiv-HTML/ar5iv image URLs are resolved like a browser would
  (honoring <base href>); PDF-embedded images are served by the backend.
