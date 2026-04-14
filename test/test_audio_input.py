from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
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

# Set these to a device index/name if you want to force a specific device.
INPUT_DEVICE: int | str | None = None
OUTPUT_DEVICE: int | str | None = None


def _describe_device(index: int) -> str:
	"""Return a readable device description for a PortAudio device index."""
	info = sd.query_devices(index)
	hostapi_index = int(info["hostapi"])
	hostapi_name = sd.query_hostapis(hostapi_index)["name"]
	return f"[{index}] {info['name']} (hostapi: {hostapi_name})"


def _extract_device_index(device: int | tuple[int | None, int | None], kind: str) -> int:
	"""Extract input/output index from a stream.device value."""
	if isinstance(device, tuple):
		index = device[0] if kind == "input" else device[1]
		if index is None:
			raise RuntimeError(f"Unable to resolve {kind} device index")
		return int(index)
	return int(device)


def print_selected_devices() -> None:
	"""Print the exact input/output devices that streams will use."""
	with sd.InputStream(
		samplerate=RECORD_SAMPLE_RATE,
		channels=RECORD_CHANNELS,
		dtype=RECORD_DTYPE,
		blocksize=RECORD_BLOCKSIZE,
		device=INPUT_DEVICE,
	) as input_stream:
		input_device_index = _extract_device_index(input_stream.device, "input")

	with sd.OutputStream(
		samplerate=PLAY_SAMPLE_RATE,
		channels=RECORD_CHANNELS,
		dtype=RECORD_DTYPE,
		device=OUTPUT_DEVICE,
	) as output_stream:
		output_device_index = _extract_device_index(output_stream.device, "output")

	print(f"Input device in use: {_describe_device(input_device_index)}")
	print(f"Output device in use: {_describe_device(output_device_index)}")


def _resample_audio(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
	"""Resample mono audio with linear interpolation."""
	if source_rate == target_rate or audio.size == 0:
		return audio

	duration = audio.size / float(source_rate)
	target_size = max(1, int(round(duration * target_rate)))

	source_x = np.linspace(0.0, duration, num=audio.size, endpoint=False)
	target_x = np.linspace(0.0, duration, num=target_size, endpoint=False)
	resampled = np.interp(target_x, source_x, audio)
	return resampled.astype(np.float32)


def print_sounddevice_devices() -> None:
	"""List all sounddevice devices so index-to-name mapping is explicit."""
	devices = sd.query_devices()
	hostapis = sd.query_hostapis()
	input_default, output_default = sd.default.device

	print("sounddevice devices:")
	for index, info in enumerate(devices):
		hostapi_name = hostapis[int(info["hostapi"])]["name"]
		in_ch = int(info["max_input_channels"])
		out_ch = int(info["max_output_channels"])

		flags: list[str] = []
		if input_default is not None and int(input_default) == index:
			flags.append("default-input")
		if output_default is not None and int(output_default) == index:
			flags.append("default-output")

		flag_text = f" [{' '.join(flags)}]" if flags else ""
		print(
			f"  {index}: {info['name']} | hostapi={hostapi_name} | "
			f"in={in_ch} out={out_ch}{flag_text}"
		)


def _print_alsa_devices(command: str, title: str) -> None:
	"""Print ALSA capture/playback devices using system tools."""
	binary = shutil.which(command)
	if binary is None:
		print(f"{title}: command '{command}' not found")
		return

	result = subprocess.run(
		[binary, "-l"],
		capture_output=True,
		text=True,
		check=False,
	)

	print(f"\n{title} ({command} -l):")
	if result.stdout.strip():
		print(result.stdout.strip())
	else:
		print("No ALSA devices reported.")

	if result.returncode != 0 and result.stderr.strip():
		print(f"{command} stderr: {result.stderr.strip()}")


def print_alsa_device_lists() -> None:
	"""Print ALSA capture and playback device names in familiar CLI format."""
	_print_alsa_devices("arecord", "ALSA capture devices")
	_print_alsa_devices("aplay", "ALSA playback devices")


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
		device=INPUT_DEVICE,
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
	audio = _resample_audio(audio, RECORD_SAMPLE_RATE, PLAY_SAMPLE_RATE)

	print("Playing back recording...")
	sd.play(audio, samplerate=PLAY_SAMPLE_RATE, device=OUTPUT_DEVICE)
	sd.wait()
	print("Playback finished")


def parse_args() -> argparse.Namespace:
	"""Parse command line options for input and output devices."""
	parser = argparse.ArgumentParser(description="Record 5s audio and play it back.")
	parser.add_argument(
		"-i",
		"--input-device",
		type=int,
		help="sounddevice input device index to use for capture",
	)
	parser.add_argument(
		"-o",
		"--output-device",
		type=int,
		help="sounddevice output device index to use for playback",
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	global INPUT_DEVICE, OUTPUT_DEVICE
	INPUT_DEVICE = args.input_device
	OUTPUT_DEVICE = args.output_device

	print_sounddevice_devices()
	print()
	print_alsa_device_lists()
	print()
	print_selected_devices()

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
