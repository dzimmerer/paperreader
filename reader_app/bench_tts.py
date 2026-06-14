"""Benchmark Kokoro TTS real-time factor (RTF = wall_seconds / audio_seconds).

RTF < 1.0 means faster than realtime. Run from the repo root:
    TTS_NUM_THREADS=4 python reader_app/bench_tts.py
"""
from __future__ import annotations

import os
import sys
import time

# Point phonemizer at the pip-bundled espeak-ng (no system install needed).
try:
    import espeakng_loader
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    EspeakWrapper.set_library(espeakng_loader.get_library_path())
    os.environ.setdefault("ESPEAK_LIBRARY", espeakng_loader.get_library_path())
    if hasattr(EspeakWrapper, "set_data_path"):
        EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
    os.environ.setdefault("PHONEMIZER_ESPEAK_DATA", espeakng_loader.get_data_path())
except Exception as exc:  # pragma: no cover
    print(f"[bench] espeakng_loader not used ({exc!r}); relying on system espeak")

import torch  # noqa: E402

n_threads = int(os.environ.get("TTS_NUM_THREADS", "0"))
if n_threads > 0:
    torch.set_num_threads(n_threads)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "tts_server", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_server.py")
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SENTENCES = [
    "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder.",
    "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely.",
    "Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable.",
]

print(f"torch={torch.__version__} threads={torch.get_num_threads()} cpu_count={os.cpu_count()}")
eng = m.KokoroEngine(voice_name="af_sarah", device="cpu")
eng.synthesize("warm up the model once.", 1.0, None)  # warm

tot_wall = tot_audio = 0.0
for s in SENTENCES:
    t0 = time.time()
    wav, sr, dur = eng.synthesize(s, 1.0, None)
    el = time.time() - t0
    tot_wall += el
    tot_audio += dur
    print(f"  wall={el:5.2f}s audio={dur:5.2f}s RTF={el/dur:.2f}")
print(f"OVERALL: wall={tot_wall:.2f}s audio={tot_audio:.2f}s RTF={tot_wall/tot_audio:.2f} "
      f"({'REALTIME+' if tot_wall < tot_audio else 'TOO SLOW'})")
