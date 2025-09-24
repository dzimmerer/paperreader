import requests
import io

# Based on common voices, but the actual availability depends on the specific API endpoint.
# Refer to the documentation of your specific OpenAI-compatible API.
# Example voices from OpenAI documentation: alloy, echo, fable, onyx, nova, shimmer
DEFAULT_VOICES = ["am_adam", "am_michael", "af_bella", "af_sarah", "bf_emma", "bf_isabella", "bm_george", "bm_lewis"]


class DockerTTSInterface:
    """
    Interface for interacting with an OpenAI-compatible Text-to-Speech REST API.
    """

    def __init__(self, base_url="http://localhost:8000/v1/audio/speech", voice="am_adam", model="tts-1"):
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

    def generate_audio(self, text, voice=None, speed=1.0, response_format="wav"):
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

        except requests.exceptions.RequestException as e:
            print(f"Error during API request: {e}")
            # Attempt to get more details from the response if available
            try:
                error_body = response.text
                print(f"Error response body: {error_body}")
            except Exception:
                pass  # Ignore if response object doesn't exist or has no text
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None


# Example Usage (optional, for testing)
if __name__ == "__main__":
    # Ensure you have a compatible API running at the specified URL
    # Example: uvicorn your_tts_api_server:app --port 8880
    # Or use the actual OpenAI API if you have a key (requires different auth)

    # Assuming a local server like the one used in background.js
    # Note: The default port in background.js was 8880, adjust if needed.
    api_url = "http://localhost:8880/v1/audio/speech"
    tts_interface = DockerTTSInterface(base_url=api_url, voice="am_adam")  # Using a voice from background.js example

    sample_text = "Hello, this is a test of the OpenAI compatible text-to-speech interface in Python."
    audio_bytes = tts_interface.generate_audio(sample_text, speed=1.2, response_format="wav")

    if audio_bytes:
        try:
            # Example: Save to a file
            output_filename = "openai_output.wav"
            with open(output_filename, "wb") as f:
                f.write(audio_bytes)
            print(f"Audio saved to {output_filename}")

            # Example: Play using a library like sounddevice or simpleaudio (if installed)
            import sounddevice as sd
            import soundfile as sf

            data, samplerate = sf.read(io.BytesIO(audio_bytes))
            print(f"Playing audio ({len(data)/samplerate:.2f}s)...")
            sd.play(data, samplerate)
            sd.wait()
            print("Playback finished.")

        except ImportError:
            print("Install 'sounddevice' and 'soundfile' to play audio directly: pip install sounddevice soundfile")
        except Exception as e:
            print(f"Error saving or playing audio: {e}")
    else:
        print("Failed to generate audio.")
