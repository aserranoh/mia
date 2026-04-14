from __future__ import annotations

import os
import queue
import tempfile
import wave

import numpy as np
import sounddevice as sd


# Match AudioCaptureTask configuration in core/src/app/pipeline.py
RECORD_SAMPLE_RATE = 16000
RECORD_CHANNELS = 1
RECORD_DTYPE = "float32"
RECORD_BLOCKSIZE = 1024
RECORD_SECONDS = 5

# Match AudioPlayTask configuration in core/src/app/pipeline.py
PLAY_SAMPLE_RATE = 22050


def record_audio_to_wave(path: str) -> None:
	audio_queue: queue.Queue[np.ndarray] = queue.Queue()

	def callback(indata, frames, time_info, status):
		if status:
			print(f"Input stream status: {status}")
		audio_queue.put(indata[:, 0].copy())

	print(f"Recording for {RECORD_SECONDS} seconds...")
	with sd.InputStream(
		samplerate=RECORD_SAMPLE_RATE,
		channels=RECORD_CHANNELS,
		dtype=RECORD_DTYPE,
		blocksize=RECORD_BLOCKSIZE,
		callback=callback,
	):
		sd.sleep(int(RECORD_SECONDS * 1000))

	blocks: list[np.ndarray] = []
	while not audio_queue.empty():
		blocks.append(audio_queue.get_nowait())

	if not blocks:
		raise RuntimeError("No audio captured from input device.")

	audio = np.concatenate(blocks).astype(np.float32)
	pcm16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)

	with wave.open(path, "wb") as wf:
		wf.setnchannels(RECORD_CHANNELS)
		wf.setsampwidth(2)
		wf.setframerate(RECORD_SAMPLE_RATE)
		wf.writeframes(pcm16.tobytes())

	print(f"Saved recording to {path}")


def play_wave(path: str) -> None:
	with wave.open(path, "rb") as wf:
		channels = wf.getnchannels()
		sampwidth = wf.getsampwidth()
		frames = wf.getnframes()
		raw = wf.readframes(frames)

	if sampwidth != 2:
		raise ValueError("This script expects 16-bit PCM WAV files.")

	audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
	if channels > 1:
		audio = audio.reshape(-1, channels).mean(axis=1)

	print("Playing back recording...")
	sd.play(audio, samplerate=PLAY_SAMPLE_RATE)
	sd.wait()
	print("Playback finished")


def main() -> None:
	with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
		temp_wav_path = tmp.name

	try:
		record_audio_to_wave(temp_wav_path)
		play_wave(temp_wav_path)
	finally:
		try:
			os.remove(temp_wav_path)
			print(f"Deleted temporary file: {temp_wav_path}")
		except FileNotFoundError:
			pass


if __name__ == "__main__":
	main()
