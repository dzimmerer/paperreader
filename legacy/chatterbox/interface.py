from __future__ import annotations

from typing import Optional

import mlx.core as mx
import numpy as np
from mlx_audio.tts.utils import load_model
from numpy.typing import NDArray


class ChatterboxInterface:
    """
    Interface for the Chatterbox TTS model using MLX.
    """

    def __init__(self, model_path: str = "mlx-community/chatterbox-turbo-fp16", voice: str = "af_heart") -> None:
        """
        Initializes the ChatterboxInterface.

        Args:
            model_path (str): The path or Hugging Face ID of the Chatterbox model.
            voice (str): The default voice to use for synthesis.
        """
        self.model_path = model_path
        self.voice = voice
        print(f"Loading Chatterbox model: {model_path}")
        self.model = load_model(model_path=model_path)
        print(f"Loaded Chatterbox model with default voice: {voice}")

    def generate_audio(
        self, text: str, speed: float = 1.0, voice: Optional[str] = None, **kwargs
    ) -> NDArray[np.float32]:
        """
        Generates audio from text and returns it as a numpy array.

        Args:
            text (str): The text to synthesize.
            speed (float): The speaking speed.
            voice (str, optional): The voice to use for this specific request.
            **kwargs: Additional arguments for the model's generate method.

        Returns:
            NDArray[np.float32]: The generated audio as a numpy array.
        """
        current_voice = voice if voice else self.voice

        # Generate audio (returns a generator of results)
        results = self.model.generate(text=text, voice=current_voice, speed=speed, **kwargs)

        audio_list = []
        for result in results:
            audio_list.append(result.audio)

        if not audio_list:
            raise ValueError("No audio generated for the provided text")

        # Concatenate all segments into one mlx array
        full_audio = mx.concatenate(audio_list, axis=0)

        # Convert mlx array to numpy array
        audio_np = np.array(full_audio)

        return audio_np

    @property
    def sample_rate(self) -> int:
        """Returns the sample rate of the model."""
        return self.model.sample_rate


if __name__ == "__main__":
    # Simple test script
    import sounddevice as sd

    text = "In the beginning, the universe was created... or the simulation was booted up."
    interface = ChatterboxInterface()

    print(f"Generating audio for: {text}")
    audio = interface.generate_audio(text)
    sr = interface.sample_rate

    print(f"Playing audio at {sr}Hz...")
    sd.play(audio, sr)
    sd.wait()
    print("Done.")
