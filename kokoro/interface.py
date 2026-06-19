from __future__ import annotations

from typing import Literal

import numpy as np
import torch
from numpy.typing import NDArray

from .kokoro_model import build_model
from .main import generate_full


VoiceName = Literal[
    "af",
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

VOICE_NAMES: tuple[str, ...] = (
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
)


class KokoroInterface:

    def __init__(self, voice_name: VoiceName = "af", lang: str | None = "a") -> None:
        if voice_name not in VOICE_NAMES:
            raise ValueError(f"Voice name must be one of {VOICE_NAMES}")

        self.voice_name = voice_name
        self.lang = voice_name[0] if lang is None else lang
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = build_model("kokoro/kokoro-v0_19.pth", self.device)
        self.voice_pack = torch.load(f"kokoro/voices/{voice_name}.pt", weights_only=True).to(self.device)
        print(f"Loaded voice: {voice_name}")

    def generate_audio(self, text: str, speed: int = 1) -> NDArray[np.float32]:
        # t1 = time.time()
        result = generate_full(self.model, text, self.voice_pack, lang=self.lang, speed=speed)
        if result is None:
            raise ValueError("No audio generated for the provided text")
        audio, _ = result
        # t2 = time.time()

        # print(f"Generated in {t2 - t1:.2f}s")
        # print("Real-time factor:", (t2 - t1) / (len(audio) / 24000))

        return audio

    @property
    def sample_rate(self) -> int:
        return 24000
