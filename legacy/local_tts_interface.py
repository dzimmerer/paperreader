from __future__ import annotations

from typing import Optional

import requests

# Based on common voices, but the actual availability depends on the specific API endpoint.
# Refer to the documentation of your specific OpenAI-compatible API.
# Example voices from OpenAI documentation: alloy, echo, fable, onyx, nova, shimmer
DEFAULT_VOICES: list[str] = [
    "am_adam",
    "am_michael",
    "af_bella",
    "af_sarah",
    "bf_emma",
    "bf_isabella",
    "bm_george",
    "bm_lewis",
]


class DockerTTSInterface:
    """
    Interface for interacting with an OpenAI-compatible Text-to-Speech REST API.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1/audio/speech",
        voice: str = "am_adam",
        model: str = "tts-1",
    ) -> None:
        """
        Initializes the OpenAIInterface.

        Args:
            base_url (str): The base URL of the OpenAI-compatible TTS API endpoint.
            voice (str): The default voice to use for synthesis.
            model (str): The TTS model to use (e.g., 'tts-1', 'tts-1-hd').
        """
        self.base_url = base_url
        self.voice = voice
        self.model = model
        # You might want to add a check here to see if the API is reachable
        print(f"Initialized OpenAIInterface with URL: {self.base_url}, Voice: {self.voice}, Model: {self.model}")

    def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        response_format: str = "wav",
    ) -> Optional[bytes]:
        """
        Generates audio from text using the configured API.

        Args:
            text (str): The text to synthesize.
            voice (str, optional): The voice to use for this specific request. Defaults to the instance's default voice.
            speed (float, optional): The speaking speed (0.25 to 4.0). Defaults to 1.0.
            response_format (str, optional): The desired audio format (e.g., 'mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'). Defaults to 'wav'.

        Returns:
            bytes: The raw audio data in the specified format, or None if an error occurred.
        """
        if not text:
            print("Error: Input text cannot be empty.")
            return None

        current_voice = voice if voice else self.voice

        headers = {
            "Content-Type": "application/json",
            "Accept": f"audio/{response_format}",  # Adjust based on API capabilities if needed
        }
        payload = {
            "model": self.model,
            "input": text,
            "voice": current_voice,
            "speed": speed,
            "response_format": response_format,
        }

        response: Optional[requests.Response] = None
        try:
            # print(f"Sending request to {self.base_url} with payload: {payload}") # Uncomment for debugging
            response = requests.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

            # Check if the response content type matches the request
            # Some APIs might return a different format or an error message as JSON
            content_type = response.headers.get("Content-Type", "")
            if f"audio/{response_format}" in content_type:
                print(f"Successfully generated audio for text (first 50 chars): '{text[:50]}...'")
                return response.content
            elif "application/json" in content_type:
                error_details = response.json()
                print(f"Error: API returned JSON instead of audio. Details: {error_details}")
                return None
            else:
                print(f"Error: Unexpected content type received: {content_type}")
                # Optionally return response.content anyway, or handle differently
                return None

        except requests.exceptions.RequestException as exc:
            print(f"Error during API request: {exc}")
            if response is not None:
                error_body = response.text
                print(f"Error response body: {error_body}")
            return None
        except Exception as exc:  # pragma: no cover - safeguard for unexpected issues
            print(f"An unexpected error occurred: {exc}")
            return None
