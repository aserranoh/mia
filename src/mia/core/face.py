
from dataclasses import dataclass, field
from pathlib import Path
import struct
from typing import Tuple

import numpy as np
from numpy.typing import NDArray
from scipy.io import wavfile
import zmq


TIME_WINDOW = 0.02


@dataclass
class SpeechMessage:
    timestamps: NDArray[np.integer]
    amplitude_samples: NDArray[np.floating]
    header: str = field(default="face/speech", init=False)

    def to_bytes(self) -> bytes:
        payload = bytearray()

        # header
        payload += self.header.encode("utf-8") + b" "

        # number of samples
        length = len(self.amplitude_samples)
        payload += struct.pack("i", length)

        for ts, amp in zip(self.timestamps, self.amplitude_samples):
            payload += struct.pack("if", int(ts), float(amp))

        return bytes(payload)


def send_amplitudes_to_face(audio_file_path: Path) -> None:
    """Read an audio file, compute RMS amplitudes, and send them to the face via ZMQ."""
    samplerate, data = wavfile.read(audio_file_path)

    # Convert to mono if stereo
    if len(data.shape) > 1:
        data = data.mean(axis=1)

    data = data.astype(np.float32, copy=False)

    # Normalize samples
    max_val = np.max(np.abs(data))
    if max_val > 0:
        data /= max_val

    timestamps, amplitudes = _compute_rms_amplitudes(data, samplerate, TIME_WINDOW)
    _send_amplitudes(socket, timestamps, amplitudes)


def _compute_rms_amplitudes(
    samples: NDArray[np.floating],
    samplerate: int,
    window_sec: float,
) -> Tuple[NDArray[np.int32], NDArray[np.float32]]:
    """Compute RMS amplitudes for the given audio samples."""
    window_size = int(window_sec * samplerate)
    if window_size <= 0:
        raise ValueError(f"window_sec too small for samplerate: {window_sec=}, {samplerate=}")

    num_windows = len(samples) // window_size
    samples = samples[:num_windows * window_size]

    windows = samples.reshape(num_windows, window_size)

    # RMS computation
    rms = np.sqrt(np.mean(np.square(windows), axis=1))

    # normalize 0..1
    max_val = np.max(rms)
    if max_val > 0:
        rms = rms / max_val

    rms = rms.astype(np.float32)

    # timestamps in microseconds
    timestamps_us = (np.arange(num_windows, dtype=np.int64) * window_sec * 1_000_000).astype(
        np.int64
    )
    timestamps = timestamps_us.astype(np.int32)

    return timestamps, rms


def _send_amplitudes(
    socket: zmq.Socket,
    timestamps: NDArray[np.integer],
    amplitudes: NDArray[np.floating],
) -> None:
    """Send the computed amplitudes to the face via ZMQ."""
    msg = SpeechMessage(
        timestamps=timestamps,
        amplitude_samples=amplitudes,
    )
    socket.send(msg.to_bytes())


ctx = zmq.Context()
socket = ctx.socket(zmq.PUB)
socket.bind("tcp://*:5555")
