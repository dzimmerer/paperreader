import json
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
