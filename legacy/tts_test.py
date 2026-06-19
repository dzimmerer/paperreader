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

from TTS.api import TTS
import sounddevice as sd
import warnings

print(TTS().list_models())


tts = TTS("tts_models/en/jenny/jenny")
# tts = TTS("tts_models/en/vctk/vits")
# tts = TTS("tts_models/en/ljspeech/vits")
# tts = TTS("tts_models/en/ljspeech/vits--neon")
# tts = TTS("tts_models/multilingual/multi-dataset/your_tts")

# tts = tts.to("mps")


print("TTs model loaded successfully")

# wav = tts.tts(text="Hello world!", speaker_wav="my/cloning/audio.wav", language="en")
wav = tts.tts(
    text="It took me quite a long time to develop a voice, and now that I have it I'm not going to be silent.",
    # language="en",
    split_sentences=True,
    # speaker="p225",
)

sd.play(wav, blocking=True, samplerate=44100 * 1.2)
# sd.play(wav, blocking=True, samplerate=22050)


# # generate speech by cloning a voice using default settings
# tts.tts_to_file(
#     text="It took me quite a long time to develop a voice, and now that I have it I'm not going to be silent.",
#     file_path="output.wav",
#     # language="en",
#     split_sentences=True,
# )

print("Speech generated successfully")
