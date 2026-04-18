
from abc import ABC, abstractmethod
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from numpy import ndarray
from piper import PiperVoice, SynthesisConfig


class TextToSpeechEngine(ABC):
    """Interface for text-to-speech engines."""

    @abstractmethod
    def synthesize(self, text: str) -> AsyncIterator[ndarray]:
        """Synthesize speech from text, yielding audio chunks as float32 numpy arrays."""
        ...


@dataclass
class PiperTextToSpeechEngine(TextToSpeechEngine):
    """Text-to-speech engine using Piper voice models."""

    voice_file: Path
    speaker_id: int | None = None

    _voice: PiperVoice = field(init=False)
    _config: SynthesisConfig | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Load the Piper voice model after initialization."""
        self._voice = PiperVoice.load(self.voice_file)
        if self.speaker_id is not None:
            self._config = SynthesisConfig(speaker_id=self.speaker_id)

    async def synthesize(self, text: str) -> AsyncIterator[ndarray]:
        """Wrap Piper sync synthesis into an async generator yielding float32 chunks."""
        iterator = iter(self._voice.synthesize(text, self._config))
        while True:
            chunk = await asyncio.to_thread(next, iterator, None)
            if chunk is None:
                return
            yield chunk.audio_float_array


def get_voice_file_from_language(language: str, voices_path: Path) -> Path:
    """Return the appropriate Piper voice file based on the language."""
    voices_by_language = list(voices_path.glob(f"{language}_*.onnx"))
    if not voices_by_language:
        voices = list(voices_path.glob("*.onnx"))
        if not voices:
            err_msg = f"No Piper voice files found in {voices_path}"
            raise FileNotFoundError(err_msg)
        return voices[0]
    return voices_by_language[0]