from TTS.api import TTS
import sounddevice as sd

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

sd.play(wav, blocking=True, samplerate=44100)
# sd.play(wav, blocking=True, samplerate=22050)


# generate speech by cloning a voice using default settings
tts.tts_to_file(
    text="It took me quite a long time to develop a voice, and now that I have it I'm not going to be silent.",
    file_path="output.wav",
    # language="en",
    split_sentences=True,
)

print("Speech generated successfully")
