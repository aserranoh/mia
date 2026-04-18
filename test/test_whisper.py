import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel

# Parameters
SAMPLE_RATE = 16000
DURATION = 5  # seconds

print("Recording...")

# Record audio
audio = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype='float32'  # <-- IMPORTANT
)

sd.wait()

print("Recording finished")

# audio shape: (samples, 1) → convert to (samples,)
audio = np.squeeze(audio)

# Ensure correct dtype (just in case)
audio = audio.astype(np.float32)

# Load model
model = WhisperModel("base.en", compute_type="float32")

# Transcribe directly from numpy
segments, info = model.transcribe(audio, beam_size=5)

print("Detected language:", info.language)

for segment in segments:
    print(segment.text)