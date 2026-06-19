import multiprocessing
import sys

# Reverting to 'spawn' (default on macOS) to avoid 'Double free' malloc errors
# which occur when using 'fork' with multi-threaded libraries like torch/mlx.
if sys.platform == "darwin":
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

def _patch_resource_tracker():
    # The resource_tracker warning is often a false positive on macOS with 
    # libraries like torch/mlx. This patch prevents it from reporting leaks.
    from multiprocessing import resource_tracker
    def fix_register(name, rtype):
        if rtype == "semaphore": return
        return resource_tracker._resource_tracker.register(name, rtype)
    resource_tracker.register = fix_register
    def fix_unregister(name, rtype):
        if rtype == "semaphore": return
        return resource_tracker._resource_tracker.unregister(name, rtype)
    resource_tracker.unregister = fix_unregister
    if "semaphore" in resource_tracker._CLEANUP_FUNCS:
        del resource_tracker._CLEANUP_FUNCS["semaphore"]

_patch_resource_tracker()

import os

# This file lives in legacy/ but uses shared modules at the repo root
# (kokoro/) and opens kokoro weights + podcast_transcript.json via CWD-relative
# paths, so put the repo root on sys.path and chdir into it.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

import json
import warnings
from kokoro.kokoro_model import build_model
import torch
import time
from kokoro.main import generate, generate_full

import soundcard as sc

SAMPLE_RATE = 44100 / 2


device = "cuda" if torch.cuda.is_available() else "cpu"
MODEL = build_model("kokoro/kokoro-v0_19.pth", device)
# VOICE_NAME = [
#     "af",  # Default voice is a 50-50 mix of Bella & Sarah
#     "af_bella",
#     "af_sarah",
#     "am_adam",
#     "am_michael",
#     "bf_emma",
#     "bf_isabella",
#     "bm_george",
#     "bm_lewis",
#     "af_nicole",
#     "af_sky",
# ][8]

v_f = torch.load("kokoro/voices/af.pt", weights_only=True).to(device)
v_m = torch.load("kokoro/voices/am.pt", weights_only=True).to(device)

# print(f"Loaded voice: {VOICE_NAME}")

# 3️⃣ Call generate, which returns 24khz audio and the phonemes used

# load content from podcast transcript.json

with open("podcast_transcript.json", "r") as f:
    data = json.load(f)

text = data["transcript"]

for segment in text:
    speaker = segment["speaker"]
    cleaned_text = segment["text"].replace("\n", " ").replace("...", " ").replace("…", " ").strip()

    if speaker == "Host":
        vp = v_f
    else:
        vp = v_m

    audio, out_ps = generate_full(MODEL, cleaned_text, vp, lang="a", speed=1.1)

    sc.default_speaker().play(
        audio,
        samplerate=24000,
    )

# text = "How could I know? It's an unanswerable question. Like asking an unborn child if they'll lead a good life. They haven't even been born."

# t1 = time.time()
# audio, out_ps = generate(MODEL, text, vp, lang="a", speed=1.0)
# t2 = time.time()

# print(f"Generated in {t2 - t1:.2f}s")
# print("Real-time factor:", (t2 - t1) / (len(audio) / 24000))

# import sounddevice as sd

# sd.play(audio, samplerate=24000)


print("Done")
