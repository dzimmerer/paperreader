# Paper Reader

A multi-component Python project for generating text-to-speech audio from academic articles. The project parses HTML content from preprint pages (such as arXiv articles), splits the content into sentences, and uses deep learning models to synthesize speech with customized voices. It also provides a web interface powered by Dash for exploring and playing the generated audio.

## Features

...

## New Flask + React Implementation

The legacy Dash prototype (`dash_test.py`) has been refactored into:

### Backend (`backend.py`)
Flask app providing REST endpoints:

- `POST /api/session` {"url": "https://arxiv.org/abs/..."} -> create a reading session (HTML parsed & TTS model loaded)
- `GET /api/session/<id>/state` -> current highlighted HTML, figure HTML, indices, speed, play state
- `POST /api/session/<id>/control` {"action": one of `play_pause`, `next_sentence`, `prev_sentence`, `next_div`, `prev_div`, `speed_inc`, `speed_dec`}
- `GET /api/session/<id>/audio?div_idx=&sentence_idx=` -> WAV audio for that specific sentence (prefetched when possible)
- `DELETE /api/session/<id>` -> cleanup session
- `GET /api/health` -> basic status

Background thread per session prefetches upcoming sentence audio. Audio cache limited by `MAX_AUDIO_CACHE`.

### Frontend (`frontend/`)
Vite + React single page app.
Features:
- Session creation form (enter arXiv URL) – automatically normalizes `/abs/` -> `/html/` server-side.
- 60/40 split layout, previous/current/next HTML blocks, figure panel (scaled), sentence window bar.
- Controls (play/pause, nav, speed). Auto-advance after audio playback ends.
- Polls backend every ~300ms for updated state (mirrors prior Dash interval logic).

### Running Locally

1. (Recommended) Create a virtual environment and install Python deps (ensure you already satisfied original requirements such as `librosa`, `soundfile`, model weights for Kokoro, etc.)

```bash
python -m venv .venv
source .venv/bin/activate
pip install flask flask-cors librosa soundfile
```

If `KokoroInterface` has extra requirements, install those as well.

2. Start backend:

```bash
python backend.py
```

Backend listens on `http://localhost:5001`.

3. Install frontend deps & run dev server:

```bash
cd frontend
npm install
npm run dev
```

The React dev server (default `5173`) proxies `/api/*` to backend (see `vite.config.js`). Open printed URL (e.g. http://localhost:5173) in your browser.

4. Enter an arXiv URL (abs/pdf) and click Start.

### Notes / Parity vs Dash
- Playback state machine simplified: the frontend triggers `next_sentence` after `<audio>` element finishes. Backend still prefetches audio.
- Speed changes clear audio cache to force re-generation at new speed.
- Title highlighting preserved (`is_title`).
- Scroll lock button placeholder (not yet auto-scrolling content; original also minimal).
- WAV audio generated on-demand and returned as a file response.

### Quality & Edge Cases
- In-memory sessions: restarting server loses state.
- No persistence or eviction policy beyond simple first-key removal when cache size exceeded.
- Concurrency: basic lock around audio cache; for heavy load consider a job queue (RQ/Celery) or async architecture.

### Future Improvements
- WebSocket / Server-Sent Events for pushing state changes (remove polling).
- Progressive audio streaming (chunked) or streaming partial sentences.
- Session inactivity timeout & cleanup scheduler.
- Configurable voice selection (expose voice_name param on session creation).
- Dockerfile for unified backend/frontend build; Nginx static serve + proxy.
- Caching processed HTML & audio across sessions (hash by URL + speed + voice).
- Optional GPU offload / batching for TTS.

---

Legacy Dash script (`dash_test.py`) retained for reference.

# Paper Reader

A multi-component Python project for generating text-to-speech audio from academic articles. The project parses HTML content from preprint pages (such as arXiv articles), splits the content into sentences, and uses deep learning models to synthesize speech with customized voices. It also provides a web interface powered by Dash for exploring and playing the generated audio.

## Features

- **HTML Parsing:** Extracts article content from a given URL and processes text splitting and markup.
- **Text Normalization & Phonemizing:** Processes text with LaTeX equations and converts them into spoken text.
- **Neural TTS:** Uses advanced neural network models (like the Kokoro model) for high-quality speech generation.
- **Dash Web Interface:** A web-based interface (via `dash_test.py`) to display content and control playback.
- **Multi-speaker Support:** Supports several voices, with voice selection managed via the `kokoro/voices` folder.

## Project Structure

- **kokoro/**
    - `kokoro_model.py`: Loads and builds the Kokoro TTS model.
    - `main.py`: Provides functions to generate audio from text.
    - `interface.py`: A simple interface for generating audio using the Kokoro model.
    - `config.json`: Configuration file for model parameters.
    - Other supporting modules (`istftnet.py`, `plbert.py`, etc.).
- **conver_html.py:** Converts webpage HTML to processed content.
- **dash_test.py:** Main entry point that launches the Dash web app.
- **test_kokoro.py, test.py, tts_test.py:** Additional test and demo scripts.
- **assets/**: Contains custom CSS and JS for the Dash app.
- **mathtex2text.py:** Processes LaTeX strings and converts them to spoken text.
- **readme.md:** This README file.

## Requirements

- Python 3.7+
- PyTorch
- NumPy, SciPy
- Dash and Dash Bootstrap Components
- BeautifulSoup4, requests, markdown, markdownify, tqdm
- phonemizer and pylatexenc
- Additional dependencies as listed in individual modules

## Installation

1. **Clone the repository:**

     ```bash
     git clone <your_repo_url>
     cd paperreader
     ```

2. **Create and activate a virtual environment:**

     ```bash
     python -m venv env
     source env/bin/activate
     ```

3. **Install the required packages:**

     ```bash
     pip install -r requirements.txt
     ```

     Ensure that your `requirements.txt` includes all the modules used in the project.

4. **Running the Application**

     ```bash
     python dash_test.py
     ```

     After launching, open your browser and go to [http://127.0.0.1:8050](http://127.0.0.1:8050) to use the interface.

## Usage

- **Web Interface:** The Dash app displays article content, highlights sentences, and plays back generated audio. Navigate between sections using the provided buttons.
- **Text-to-Speech:** The TTS interface supports different voices (located in the `kokoro/voices` folder) and allows you to adjust playback speed.

## Notes

Ensure the correct paths to required libraries and assets (for example, the espeak-ng library in `main.py`). The project is set up for scalability, so feel free to modify configuration parameters in `config.json` and experiment with different voices and models.