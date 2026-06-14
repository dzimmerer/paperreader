/* Paper Reader frontend.
 *
 * Loads the structured document from the parsing backend, renders every
 * sentence as a <span class="sent"> of <span class="w"> word spans, and plays
 * sentence audio fetched from /api/doc/<id>/audio/<idx>. While audio plays, a
 * requestAnimationFrame loop maps audio.currentTime onto the per-word timings
 * returned by the backend: the active sentence gets a light-yellow highlight,
 * the active word a dark-yellow one.
 */

"use strict";

const els = {
  urlInput: document.getElementById("url-input"),
  loadBtn: document.getElementById("load-btn"),
  fileInput: document.getElementById("file-input"),
  status: document.getElementById("status"),
  paper: document.getElementById("paper"),
  controls: document.getElementById("controls"),
  prevBtn: document.getElementById("prev-btn"),
  playBtn: document.getElementById("play-btn"),
  nextBtn: document.getElementById("next-btn"),
  speedSelect: document.getElementById("speed-select"),
  progress: document.getElementById("progress"),
  fileLabel: document.getElementById("file-label"),
  cancelBtn: document.getElementById("cancel-btn"),
};

const state = {
  doc: null,
  current: -1, // active global sentence index
  playing: false, // user intent: keep advancing through sentences
  loadToken: 0, // invalidates stale async playSentence calls
  audioCache: new Map(), // idx -> Promise<{src, timings, duration}>
  activeWordEl: null,
  rafId: null,
  loadController: null, // AbortController for the in-flight document load
};

const audio = new Audio();
audio.preload = "auto";

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function setStatus(msg, isError = false) {
  els.status.textContent = msg;
  els.status.classList.toggle("error", isError);
  els.status.title = msg;
}

function updateProgress() {
  if (!state.doc) return;
  els.progress.textContent = `${Math.max(state.current, 0) + 1} / ${state.doc.num_sentences}`;
}

// ---------------------------------------------------------------------------
// Document loading + rendering
// ---------------------------------------------------------------------------

// Toggle the loading state: disable the input controls and show the cancel "✕".
function setLoading(loading) {
  els.loadBtn.disabled = loading;
  els.urlInput.disabled = loading;
  els.fileInput.disabled = loading;
  els.fileLabel.classList.toggle("disabled", loading);
  els.cancelBtn.classList.toggle("hidden", !loading);
}

function cancelLoad() {
  if (state.loadController) state.loadController.abort();
}

async function loadFromUrl(url) {
  if (!url || state.loadController) return;
  await loadDoc((signal) =>
    fetch("/api/doc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal,
    }),
  );
}

async function loadFromFile(file) {
  if (state.loadController) return;
  const form = new FormData();
  form.append("file", file, file.name);
  await loadDoc((signal) => fetch("/api/doc", { method: "POST", body: form, signal }));
}

async function loadDoc(makeRequest) {
  stopPlayback();
  state.doc = null;
  state.audioCache.clear();
  state.current = -1;
  state.loadController = new AbortController();
  setLoading(true);
  setStatus("Parsing document…");
  try {
    const resp = await makeRequest(state.loadController.signal);
    const doc = await resp.json();
    if (!resp.ok) throw new Error(doc.error || `HTTP ${resp.status}`);
    state.doc = doc;
    renderDoc(doc);
    els.controls.classList.remove("hidden");
    setStatus(`Loaded (${doc.source}, ${doc.num_sentences} sentences)`);
    setCurrent(0, { scroll: false });
  } catch (err) {
    if (err.name === "AbortError") {
      setStatus("Cancelled");
    } else {
      setStatus(`Error: ${err.message}`, true);
    }
  } finally {
    state.loadController = null;
    setLoading(false);
  }
}

const MATH_RE = /\$[^$]+\$/g;
const KATEX_MACROS = {
  "\\bm": "\\boldsymbol{#1}",
  "\\nicefrac": "\\frac{#1}{#2}",
  "\\sb": "_",
  "\\sp": "^",
};

/* Fill a word span: plain text stays text, $...$ segments render via KaTeX.
 * Long standalone equations get the scrollable .math-block treatment. */
function renderWordContent(wEl, text) {
  if (!text.includes("$") || typeof katex === "undefined") {
    wEl.textContent = text;
    return;
  }
  MATH_RE.lastIndex = 0;
  let last = 0;
  let match;
  let mathChars = 0;
  while ((match = MATH_RE.exec(text)) !== null) {
    if (match.index > last) wEl.appendChild(document.createTextNode(text.slice(last, match.index)));
    const latex = match[0].slice(1, -1);
    const mathEl = document.createElement("span");
    try {
      katex.render(latex, mathEl, {
        throwOnError: false,
        errorColor: "#8a6d3b",
        strict: false,
        macros: KATEX_MACROS,
      });
    } catch (err) {
      mathEl.textContent = match[0];
    }
    wEl.appendChild(mathEl);
    mathChars += latex.length;
    last = match.index + match[0].length;
  }
  if (last < text.length) wEl.appendChild(document.createTextNode(text.slice(last)));
  if (mathChars > 60) wEl.classList.add("math-block");
}

function sentenceSpan(sentence) {
  const span = document.createElement("span");
  span.className = "sent";
  span.id = `sent-${sentence.idx}`;
  span.dataset.idx = sentence.idx;
  sentence.words.forEach((word, w) => {
    const wEl = document.createElement("span");
    wEl.className = "w";
    wEl.dataset.w = w;
    renderWordContent(wEl, word);
    span.appendChild(wEl);
    if (w < sentence.words.length - 1) span.appendChild(document.createTextNode(" "));
  });
  return span;
}

function renderDoc(doc) {
  els.paper.innerHTML = "";

  const title = document.createElement("h1");
  title.className = "doc-title";
  title.textContent = doc.title;
  els.paper.appendChild(title);

  const source = document.createElement("div");
  source.className = "doc-source";
  // Only render the source as a clickable link if it's a safe http(s) URL,
  // otherwise show it as plain text (guards against javascript:/data: hrefs).
  const isHttp = /^https?:\/\//i.test(doc.url || "");
  if (isHttp) {
    const link = document.createElement("a");
    link.href = doc.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = doc.url;
    source.append(`source: ${doc.source} — `, link);
  } else {
    source.textContent = `source: ${doc.source} — ${doc.url || ""}`;
  }
  els.paper.appendChild(source);

  for (const block of doc.blocks) {
    if (block.type === "heading") {
      const level = Math.min(Math.max(block.level || 2, 2), 4);
      const h = document.createElement(`h${level}`);
      for (const s of block.sentences) h.appendChild(sentenceSpan(s));
      els.paper.appendChild(h);
    } else if (block.type === "figure") {
      const fig = document.createElement("figure");
      if (block.image_url) {
        const img = document.createElement("img");
        img.src = block.image_url;
        img.loading = "lazy";
        img.alt = "figure";
        fig.appendChild(img);
      }
      if (block.sentences.length) {
        const cap = document.createElement("figcaption");
        block.sentences.forEach((s, i) => {
          cap.appendChild(sentenceSpan(s));
          if (i < block.sentences.length - 1) cap.appendChild(document.createTextNode(" "));
        });
        fig.appendChild(cap);
      }
      els.paper.appendChild(fig);
    } else {
      const p = document.createElement("p");
      block.sentences.forEach((s, i) => {
        p.appendChild(sentenceSpan(s));
        if (i < block.sentences.length - 1) p.appendChild(document.createTextNode(" "));
      });
      els.paper.appendChild(p);
    }
  }
}

// ---------------------------------------------------------------------------
// Audio fetching
// ---------------------------------------------------------------------------

function ensureAudio(idx) {
  if (!state.doc || idx < 0 || idx >= state.doc.num_sentences) {
    return Promise.reject(new Error("sentence out of range"));
  }
  if (!state.audioCache.has(idx)) {
    const promise = fetch(`/api/doc/${state.doc.doc_id}/audio/${idx}`)
      .then(async (resp) => {
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
        return {
          src: `data:audio/wav;base64,${data.audio_b64}`,
          timings: data.timings,
          duration: data.duration,
        };
      })
      .catch((err) => {
        state.audioCache.delete(idx); // allow retry
        throw err;
      });
    state.audioCache.set(idx, promise);
  }
  return state.audioCache.get(idx);
}

function prefetch(idx) {
  for (let i = idx; i < idx + 2 && state.doc && i < state.doc.num_sentences; i++) {
    ensureAudio(i).catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Highlighting
// ---------------------------------------------------------------------------

function sentEl(idx) {
  return document.getElementById(`sent-${idx}`);
}

function clearWordHighlight() {
  if (state.activeWordEl) {
    state.activeWordEl.classList.remove("active");
    state.activeWordEl = null;
  }
}

function setCurrent(idx, { scroll = true } = {}) {
  if (!state.doc) return;
  idx = Math.max(0, Math.min(idx, state.doc.num_sentences - 1));
  const prev = sentEl(state.current);
  if (prev) prev.classList.remove("active", "loading");
  clearWordHighlight();
  state.current = idx;
  const el = sentEl(idx);
  if (el) {
    el.classList.add("active");
    if (scroll) el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  updateProgress();
}

function highlightWordAt(time, timings) {
  const el = sentEl(state.current);
  if (!el || !timings) return;
  let active = -1;
  for (let i = 0; i < timings.length; i++) {
    if (time >= timings[i].start && time < timings[i].end) { active = i; break; }
    if (time >= timings[i].end) active = i;
  }
  const wordEl = active >= 0 ? el.querySelector(`.w[data-w="${active}"]`) : null;
  if (wordEl !== state.activeWordEl) {
    clearWordHighlight();
    if (wordEl) {
      wordEl.classList.add("active");
      state.activeWordEl = wordEl;
    }
  }
}

// ---------------------------------------------------------------------------
// Playback engine
// ---------------------------------------------------------------------------

function setPlayButton() {
  els.playBtn.textContent = state.playing ? "⏸" : "▶";
  els.playBtn.classList.remove("busy");
}

async function playSentence(idx) {
  const token = ++state.loadToken;
  setCurrent(idx);
  const el = sentEl(idx);
  els.playBtn.classList.add("busy");
  if (el) el.classList.add("loading");
  let clip;
  try {
    clip = await ensureAudio(idx);
  } catch (err) {
    if (token !== state.loadToken) return;
    setStatus(`Audio error: ${err.message}`, true);
    state.playing = false;
    setPlayButton();
    if (el) el.classList.remove("loading");
    return;
  }
  if (token !== state.loadToken || !state.playing) {
    if (el) el.classList.remove("loading");
    return;
  }
  if (el) el.classList.remove("loading");
  setPlayButton();
  setStatus("");

  audio.src = clip.src;
  audio.playbackRate = parseFloat(els.speedSelect.value);
  try {
    await audio.play();
  } catch (err) {
    state.playing = false;
    setPlayButton();
    return;
  }
  prefetch(idx + 1);

  cancelAnimationFrame(state.rafId);
  const tick = () => {
    if (state.loadToken !== token) return;
    highlightWordAt(audio.currentTime, clip.timings);
    if (!audio.paused && !audio.ended) {
      state.rafId = requestAnimationFrame(tick);
    }
  };
  state.rafId = requestAnimationFrame(tick);

  audio.onended = () => {
    if (state.loadToken !== token) return;
    clearWordHighlight();
    if (state.playing && state.current + 1 < state.doc.num_sentences) {
      playSentence(state.current + 1);
    } else {
      state.playing = false;
      setPlayButton();
      if (state.current + 1 >= state.doc.num_sentences) setStatus("Finished 🎉");
    }
  };
}

function togglePlay() {
  if (!state.doc) return;
  if (state.playing) {
    state.playing = false;
    audio.pause();
    state.loadToken++; // cancel any in-flight sentence load
    setPlayButton();
  } else {
    state.playing = true;
    setPlayButton();
    // Resume mid-sentence if the clip is loaded and not finished
    if (audio.src && !audio.ended && audio.currentTime > 0) {
      const token = ++state.loadToken;
      ensureAudio(state.current).then((clip) => {
        if (state.loadToken !== token || !state.playing) return;
        audio.playbackRate = parseFloat(els.speedSelect.value);
        audio.play();
        const tick = () => {
          if (state.loadToken !== token) return;
          highlightWordAt(audio.currentTime, clip.timings);
          if (!audio.paused && !audio.ended) state.rafId = requestAnimationFrame(tick);
        };
        state.rafId = requestAnimationFrame(tick);
        audio.onended = () => {
          if (state.loadToken !== token) return;
          clearWordHighlight();
          if (state.playing && state.current + 1 < state.doc.num_sentences) {
            playSentence(state.current + 1);
          } else {
            state.playing = false;
            setPlayButton();
          }
        };
      }).catch(() => playSentence(Math.max(state.current, 0)));
    } else {
      playSentence(Math.max(state.current, 0));
    }
  }
}

function stopPlayback() {
  state.playing = false;
  state.loadToken++;
  audio.pause();
  audio.removeAttribute("src");
  cancelAnimationFrame(state.rafId);
  clearWordHighlight();
  setPlayButton();
}

function jumpTo(idx) {
  if (!state.doc) return;
  audio.pause();
  state.loadToken++;
  clearWordHighlight();
  if (state.playing) {
    playSentence(idx);
  } else {
    setCurrent(idx);
    prefetch(idx);
  }
}

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------

els.loadBtn.addEventListener("click", () => loadFromUrl(els.urlInput.value.trim()));
els.urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadFromUrl(els.urlInput.value.trim());
});
els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files.length) loadFromFile(els.fileInput.files[0]);
  els.fileInput.value = "";
});

els.cancelBtn.addEventListener("click", cancelLoad);

els.playBtn.addEventListener("click", togglePlay);
els.prevBtn.addEventListener("click", () => jumpTo(state.current - 1));
els.nextBtn.addEventListener("click", () => jumpTo(state.current + 1));
els.speedSelect.addEventListener("change", () => {
  audio.playbackRate = parseFloat(els.speedSelect.value);
});

els.paper.addEventListener("click", (e) => {
  const sent = e.target.closest(".sent");
  if (sent) jumpTo(parseInt(sent.dataset.idx, 10));
});

document.addEventListener("keydown", (e) => {
  if (e.target === els.urlInput || e.target.tagName === "SELECT") return;
  if (e.code === "Space") {
    e.preventDefault();
    togglePlay();
  } else if (e.key === "ArrowRight") {
    jumpTo(state.current + 1);
  } else if (e.key === "ArrowLeft") {
    jumpTo(state.current - 1);
  }
});

fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    if (h.tts && h.tts.engine) setStatus(`TTS ready (${h.tts.engine})`);
    else setStatus("TTS server not reachable", true);
  })
  .catch(() => {});
