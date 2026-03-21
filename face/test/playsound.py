
import argparse
from dataclasses import dataclass, field
from pathlib import Path
import struct
from typing import Tuple

import numpy as np
from numpy.typing import NDArray
import zmq
import sounddevice as sd
from scipy.io import wavfile

import matplotlib
import matplotlib.pyplot as plt


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


def compute_rms_amplitudes(
    samples: NDArray[np.floating],
    samplerate: int,
    window_sec: float,
) -> Tuple[NDArray[np.int32], NDArray[np.float32]]:
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


def plot_amplitudes(
    timestamps_us: NDArray[np.integer],
    amplitudes: NDArray[np.floating],
    *,
    out_path: Path,
) -> None:
    t_sec = (timestamps_us.astype(np.float64) / 1_000_000.0).astype(np.float64)

    fig, ax = plt.subplots(figsize=(10, 3), dpi=120)
    ax.plot(t_sec, amplitudes, linewidth=1)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("normalized RMS")
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    fig.savefig(out_path)
    print(f"Saved amplitude plot to {out_path}")

    # Try to show interactively when possible, but don't block the script.
    backend = matplotlib.get_backend().lower()
    if "agg" not in backend:
        try:
            plt.show(block=False)
            plt.pause(0.001)
        except Exception:
            pass


def send_amplitudes(
    socket: zmq.Socket,
    timestamps: NDArray[np.integer],
    amplitudes: NDArray[np.floating],
) -> None:
    msg = SpeechMessage(
        timestamps=timestamps,
        amplitude_samples=amplitudes,
    )
    socket.send(msg.to_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("wavfile")
    parser.add_argument(
        "--window",
        type=float,
        default=0.02,
        help="RMS window size in seconds (default: 0.02)",
    )

    parser.add_argument(
        "--addr",
        default="tcp://127.0.0.1:5555",
        help="ZMQ PUB address",
    )

    args = parser.parse_args()

    wav_path = Path(args.wavfile)
    samplerate, data = wavfile.read(wav_path)

    # Convert to mono if stereo
    if len(data.shape) > 1:
        data = data.mean(axis=1)

    data = data.astype(np.float32, copy=False)

    # Normalize samples
    max_val = np.max(np.abs(data))
    if max_val > 0:
        data /= max_val

    timestamps, amplitudes = compute_rms_amplitudes(
        data,
        samplerate,
        args.window,
    )

    print(f"Computed {len(amplitudes)} amplitude samples")

    ctx = zmq.Context()
    socket = ctx.socket(zmq.PUB)
    socket.bind(args.addr)

    # allow subscribers to connect
    input("Hit enter to continue...")

    # Plot amplitudes before publishing.
    plot_amplitudes(timestamps, amplitudes, out_path=Path("amplitudes.png"))
    send_amplitudes(socket, timestamps, amplitudes)

    print("Amplitude + timestamp data sent")

    # play sound
    sd.play(data, samplerate)
    sd.wait()


if __name__ == "__main__":
    main()