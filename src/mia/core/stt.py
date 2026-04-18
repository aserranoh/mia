
from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field

from faster_whisper import WhisperModel
from numpy import ndarray


class SpeechToTextEngine(ABC):
    """Abstract base class for speech-to-text engines."""

    @abstractmethod
    async def transcribe(self, audio: ndarray, prompt: str | None = None) -> str:
        """Transcribe the given audio and return the text."""
        ...


@dataclass
class WhisperSpeechToTextEngine(SpeechToTextEngine):
    """Speech-to-text engine using the Faster Whisper library."""

    model: str
    beam_size: int = 5
    language: str | None = None

    _whisper_model: WhisperModel = field(init=False)

    def __post_init__(self) -> None:
        """Load the Whisper model after initialization."""
        self._whisper_model = WhisperModel(self.model, device="cpu", compute_type="int8")
    
    async def transcribe(self, audio: ndarray, prompt: str | None = None) -> str:
        """Transcribe the given audio and return the text."""
        return await asyncio.to_thread(self._transcribe, audio, prompt)
    
    def _transcribe(self, audio: ndarray, prompt: str | None) -> str:
        """Run Whisper transcription for one chunk and return normalized text."""
        segments, _ = self._whisper_model.transcribe(
            audio,
            initial_prompt=prompt,
            beam_size=self.beam_size,
            language=self.language,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text).strip()