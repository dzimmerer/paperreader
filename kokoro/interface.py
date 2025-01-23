import time

import torch

from .kokoro_model import build_model
from .main import generate_full


VOICE_NAMES = [
    "af",  # Default voice is a 50-50 mix of Bella & Sarah
    "am",
    "af_bella",
    "af_sarah",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bf_isabella",
    "bm_george",
    "bm_lewis",
    "af_nicole",
    "af_sky",
]


class KokoroInterface:

    def __init__(self, voice_name="af", lang="a"):

        assert voice_name in VOICE_NAMES, f"Voice name must be one of {VOICE_NAMES}"

        self.voice_name = voice_name

        if lang is None:
            self.lang = voice_name[0]
        else:
            self.lang = lang

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = build_model("kokoro/kokoro-v0_19.pth", self.device)
        self.voice_pack = torch.load(f"kokoro/voices/{voice_name}.pt", weights_only=True).to(self.device)
        print(f"Loaded voice: {voice_name}")

    def generate_audio(self, text, speed=1):
        # t1 = time.time()
        audio, out_ps = generate_full(self.model, text, self.voice_pack, lang=self.lang, speed=speed)
        # t2 = time.time()

        # print(f"Generated in {t2 - t1:.2f}s")
        # print("Real-time factor:", (t2 - t1) / (len(audio) / 24000))

        return audio
