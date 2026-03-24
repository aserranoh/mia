import wave
from pathlib import Path
from piper import PiperVoice
import soundfile
import sounddevice

current_directory = Path(__file__).parent
voices_directory = current_directory / ".." / "voices"

text = "This is a test with English language and a British accent."
audio_file_path = current_directory / "test.wav"

def find_bluetooth_output():
    devices = sounddevice.query_devices()
    print(devices)
    for idx, dev in enumerate(devices):
        name = dev["name"].lower()
        if dev["max_output_channels"] > 0 and (
            "bluealsa" in name or "bluetooth" in name or "a2dp" in name
        ):
            return idx, dev["name"]
    return None, None

def main() -> None:
    voice = PiperVoice.load(voices_directory / "en_GB-cori-high.onnx")

    bt_idx, _ = find_bluetooth_output()
    if bt_idx is None:
        print("Bluetooth output device not found. Available devices:")
        print(sounddevice.query_devices())
        return

    with wave.open(audio_file_path.as_posix(), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)

    find_bluetooth_output()

    with audio_file_path.open("rb") as audio_file:
        data, sample_rate = soundfile.read(audio_file, dtype="float32")
        sounddevice.play(data, sample_rate)
        sounddevice.wait()

if __name__ == "__main__":
    main()