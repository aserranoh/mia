
from abc import ABC, abstractmethod
import asyncio
from asyncio import Event, Queue
from dataclasses import dataclass, field
from enum import StrEnum
import logging
from logging import Logger
import struct
from typing import Any

import numpy as np
from numpy import ndarray
from numpy.typing import NDArray
import sounddevice
from sounddevice import InputStream

from .bus import Bus
from .llm import LLM
from .nlp import markdown_to_plain, remove_emojis, sentence_tokenizer
from .stt import SpeechToTextEngine
from .tts import TextToSpeechEngine


class AudioCaptureTaskState(StrEnum):
    """States for the audio capture task state machine."""

    IDLE = "idle"
    RECORDING = "recording"


class TerminatePipeline(Exception):
    """Exception used to terminate the pipeline task group gracefully."""


async def force_terminate_pipeline() -> None:
    """Raise an exception that stops the task group."""
    raise TerminatePipeline()


@dataclass
class Task[T: Any](ABC):
    """A protocol for tasks that can be run in the pipeline."""

    next_tasks: "list[Task]" = field(init=False, default_factory=list)
    queue: Queue[T] = field(init=False, default_factory=Queue)
    _logger: Logger = field(init=False)

    def __post_init__(self):
        """Initialize the logger for the task."""
        self._logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def run(self) -> None:
        """Run the task."""
        ...

    def connect(self, next_task: "Task") -> None:
        """Connect this task to the next task in the pipeline."""
        self.next_tasks.append(next_task)

    def enqueue(self, item: T) -> None:
        """Enqueue an item to be processed by the task."""
        self.queue.put_nowait(item)

    def send_downstream(self, item: Any) -> None:
        """Send an item to all connected downstream tasks."""
        for next_task in self.next_tasks:
            next_task.enqueue(item)

    def log(self, level: int, message: str, *args: Any) -> None:
        """Log a message with the task's logger."""
        self._logger.log(level, message, *args)


@dataclass
class AudioCaptureTask(Task[Any]):
    """A long-lived task that captures microphone audio while in the recording state."""

    sample_rate: int = 16000

    next_tasks: list[Task[np.ndarray]] = field(init=False, default_factory=list)
    _stream: InputStream | None = field(init=False, default=None)
    _loop: asyncio.AbstractEventLoop = field(init=False)
    _state: AudioCaptureTaskState = field(init=False, default=AudioCaptureTaskState.IDLE)

    async def run(self) -> None:
        """Keep running and apply queued state transition requests."""
        self._loop = asyncio.get_running_loop()
        try:
            while True:
                await self.queue.get()
                try:
                    self._toggle_state()
                finally:
                    self.queue.task_done()
        finally:
            self._stop_stream()
            self._state = AudioCaptureTaskState.IDLE

    def _callback(self, indata, frames, time_info, status):
        """Callback function for the InputStream."""
        if status:
            self.log(logging.WARNING, str(status))
        mono = indata[:, 0].copy()
        self._loop.call_soon_threadsafe(self._enqueue_block, mono)

    def _enqueue_block(self, block: np.ndarray) -> None:
        """Enqueue one block of audio data to the next task."""
        if self._state == AudioCaptureTaskState.RECORDING:
            self.send_downstream(block)

    def _toggle_state(self) -> None:
        """Apply the requested state transition if needed."""
        if self._state == AudioCaptureTaskState.IDLE:
            self._start_stream()
        else:
            self._stop_stream()

    def _start_stream(self) -> None:
        """Create and start the input stream if it is not already active."""
        self._stream = InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=self._callback,
        )
        self._stream.start()
        self._state = AudioCaptureTaskState.RECORDING
        self.log(logging.INFO, "Audio recording started")

    def _stop_stream(self) -> None:
        """Stop and close the input stream if it exists."""
        self._state = AudioCaptureTaskState.IDLE
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.send_downstream(np.array([], dtype=np.float32))
        self.log(logging.INFO, "Audio recording stopped")


@dataclass
class AudioChunkerTask(Task[ndarray]):
    """A task that takes raw audio arrays, buffers them, and emits fixed-size overlapping chunks."""

    sample_rate: int = 16000
    chunk_seconds: float = 3.0
    overlap_seconds: float = 0.15

    next_tasks: list[Task[ndarray]] = field(init=False, default_factory=list)
    _buffer: ndarray = field(init=False, default_factory=lambda: np.empty(0, dtype=np.float32))
    _chunk_samples: int = field(init=False)
    _overlap_samples: int = field(init=False)

    def __post_init__(self):
        """Calculate the number of samples for chunks and overlap based on the sample rate."""
        super().__post_init__()
        self._chunk_samples = int(self.chunk_seconds * self.sample_rate)
        self._overlap_samples = int(self.overlap_seconds * self.sample_rate)
        if self._overlap_samples >= self._chunk_samples:
            raise ValueError("overlap_seconds must be smaller than chunk_seconds")

    async def run(self):
        """Main loop: consume audio blocks and emit chunks."""
        while True:
            block = await self.queue.get()
            try:
                self._process_block(block)
            finally:
                self.queue.task_done()

    def _process_block(self, block: ndarray) -> None:
        """Buffer incoming audio and emit chunks when enough data is available."""
        if block.size == 0:
            self._flush()
            self.send_downstream(np.empty(0, dtype=np.float32))
            return
        self._buffer = np.concatenate((self._buffer, block))
        while len(self._buffer) >= self._chunk_samples:
            self._emit_chunk()

    def _emit_chunk(self):
        """Emit one chunk and keep overlap."""
        chunk = self._buffer[:self._chunk_samples]
        self.log(logging.DEBUG, "Emitting audio chunk of length %s", len(chunk))
        self.send_downstream(chunk)
        overlap_start = self._chunk_samples - self._overlap_samples
        self._buffer = self._buffer[overlap_start:]

    def _flush(self):
        """Flush remaining audio as final chunk."""
        if len(self._buffer) > 0:
            self.send_downstream(self._buffer)
            self._buffer = np.empty(0, dtype=np.float32)


@dataclass
class SpeechToTextTask(Task[ndarray]):
    """A task that transcribes audio chunks and emits one final text request."""

    stt_engine: SpeechToTextEngine
    prompt_max_words: int = 30

    next_tasks: list[Task[str]] = field(init=False, default_factory=list)
    _transcript_buffer: list[str] = field(init=False, default_factory=list)

    async def run(self) -> None:
        """Continuously transcribe chunks and emit a concatenated transcription."""
        while True:
            audio = await self.queue.get()
            try:
                await self._process_chunk(audio)
            finally:
                self.queue.task_done()

    async def _process_chunk(self, audio: ndarray) -> None:
        """Transcribe one chunk of audio and buffer the text, emitting a final request on empty input."""
        if audio.size > 0:
            prompt = self._build_prompt()
            self.log(logging.INFO, "Processing chunk (length=%s): %s", len(audio), prompt)
            text = await self.stt_engine.transcribe(audio, prompt)
            if text:
                self._transcript_buffer.append(text)
        else:
            self._emit_transcription()

    def _emit_transcription(self) -> None:
        """Concatenate buffered transcriptions and emit as one request."""
        full_text = " ".join(self._transcript_buffer).strip()
        if not full_text:
            self.log(logging.INFO, "No transcription for this segment")
        else:
            self.log(logging.INFO, "Final transcription: %s", full_text)
            self.send_downstream(full_text)
            self._transcript_buffer.clear()

    def _build_prompt(self) -> str | None:
        """Build a bounded prompt from the latest transcribed words."""
        if not self._transcript_buffer or self.prompt_max_words <= 0:
            return None
        words = " ".join(self._transcript_buffer).split()
        return " ".join(words[-self.prompt_max_words :])


@dataclass
class LLMChatTask(Task[str]):
    """A task that sends requests to Gemini chat and streams tokenized sentences."""

    llm: LLM

    next_tasks: list[Task[str]] = field(init=False, default_factory=list)

    async def run(self) -> None:
        """Continuously process queued prompts and stream sentence chunks downstream."""
        while True:
            text = await self.queue.get()
            try:
                await self._process_request(text)
            finally:
                self.queue.task_done()

    async def _process_request(self, text: str) -> None:
        """Send one request to the LLM and stream tokenized sentences downstream."""
        async for sentence in sentence_tokenizer(self.llm.send_message_stream(text)):
            self.send_downstream(sentence)


@dataclass
class TextToSpeechTask(Task[str]):

    tts_engine: TextToSpeechEngine

    next_tasks: list[Task[ndarray]] = field(init=False, default_factory=list)

    async def run(self) -> None:
        """Continuously convert text to speech and enqueue synthesized audio arrays."""
        while True:
            text = await self.queue.get()
            try:
                await self._process_sentence(text)
            finally:
                self.queue.task_done()

    async def _process_sentence(self, sentence: str) -> None:
        """Synthesize one sentence and enqueue generated audio chunks incrementally."""
        text = remove_emojis(markdown_to_plain(sentence))
        async for audio in self.tts_engine.synthesize(text):
            self.send_downstream(audio)


@dataclass
class AudioPlayTask(Task[ndarray]):
    """A task that plays synthesized audio arrays."""

    bus: Bus
    sample_rate: int = 22050
    window_size: float = 0.02

    _is_playing: bool = field(init=False, default=False)

    async def run(self) -> None:
        """Continuously play audio arrays from the queue."""
        while True:
            audio = await self.queue.get()
            self._is_playing = True
            await self._publish_mouth_animation(audio)
            await asyncio.to_thread(self._play_audio, audio)
            self._is_playing = False
            self.queue.task_done()

            # Sleep for a short time to avoid overwhelming the audio device with back-to-back play calls.
            await asyncio.sleep(0.5)

    async def wait(self) -> None:
        """Wait until all queued audio arrays have been played."""
        await self.queue.join()

    def _play_audio(self, audio: ndarray) -> None:
        """Play one audio array using the configured sample rate."""
        output = np.asarray(audio, dtype=np.float32)
        if output.ndim != 1:
            output = output.reshape(-1)
        if output.size == 0:
            return
        sounddevice.play(output, self.sample_rate)
        sounddevice.wait()

    async def _publish_mouth_animation(self, audio: ndarray) -> None:
        """Publish a mouth animation envelope when a chunk starts playback."""
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim != 1:
            samples = samples.reshape(-1)
        if samples.size == 0:
            return

        timestamps, amplitudes = self._compute_rms_amplitudes(samples)
        if timestamps.size == 0:
            return

        try:
            await self.bus.publish(
                "maia.mouth",
                self._encode_animation_message(timestamps, amplitudes),
            )
        except Exception as exc:
            self.log(logging.WARNING, "Failed to publish mouth animation: %s", exc)

    def _compute_rms_amplitudes(
        self,
        samples: NDArray[np.floating],
    ) -> tuple[NDArray[np.int32], NDArray[np.float32]]:
        """Compute RMS amplitudes and corresponding timestamps from audio samples."""
        window_size = int(self.window_size * self.sample_rate)
        if window_size <= 0:
            raise ValueError(f"window_size too small for samplerate: {window_size}")

        num_windows = len(samples) // window_size
        if num_windows == 0:
            return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.float32)

        samples = samples[:num_windows * window_size]
        windows = samples.reshape(num_windows, window_size)

        rms = np.sqrt(np.mean(np.square(windows), axis=1))
        max_val = np.max(rms)
        if max_val > 0:
            rms = rms / max_val
        rms = rms.astype(np.float32)

        timestamps_us = (
            np.arange(num_windows, dtype=np.int64) * self.window_size * 1_000_000
        ).astype(np.int64)
        timestamps = timestamps_us.astype(np.int32)

        return timestamps, rms

    def _encode_animation_message(
        self,
        timestamps: NDArray[np.int32],
        amplitudes: NDArray[np.float32],
    ) -> bytes:
        """Encode timestamps and amplitudes into a byte message for mouth animation."""
        payload = bytearray()

        length = len(timestamps)
        payload += struct.pack("i", length)

        for ts, amp in zip(timestamps, amplitudes):
            payload += struct.pack("if", int(ts), float(amp))
        return bytes(payload)


@dataclass
class Pipeline:
    """Orchestrate the long-lived tasks that compose the voice pipeline."""

    stt_engine: SpeechToTextEngine
    llm: LLM
    tts_engine: TextToSpeechEngine
    bus: Bus
    
    _audio_capture_task: AudioCaptureTask = field(init=False, default_factory=AudioCaptureTask)
    _audio_chunker_task: AudioChunkerTask = field(init=False, default_factory=AudioChunkerTask)
    _speech_to_text_task: SpeechToTextTask = field(init=False)
    _llm_chat_task: LLMChatTask = field(init=False)
    _text_to_speech_task: TextToSpeechTask = field(init=False)
    _audio_play_task: AudioPlayTask = field(init=False)
    _stop_event: Event = field(init=False, default_factory=Event)

    def __post_init__(self) -> None:
        """Initialize internal tasks and connect the pipeline."""
        self._speech_to_text_task = SpeechToTextTask(stt_engine=self.stt_engine)
        self._llm_chat_task = LLMChatTask(llm=self.llm)
        self._text_to_speech_task = TextToSpeechTask(tts_engine=self.tts_engine)
        self._audio_play_task = AudioPlayTask(bus=self.bus)

        self._audio_capture_task.connect(self._audio_chunker_task)
        self._audio_chunker_task.connect(self._speech_to_text_task)
        self._speech_to_text_task.connect(self._llm_chat_task)
        self._llm_chat_task.connect(self._text_to_speech_task)
        self._text_to_speech_task.connect(self._audio_play_task)

    async def run(self) -> None:
        """Run all pipeline tasks concurrently as long-lived workers."""
        self._stop_event.clear()
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self._audio_capture_task.run())
                group.create_task(self._audio_chunker_task.run())
                group.create_task(self._speech_to_text_task.run())
                group.create_task(self._llm_chat_task.run())
                group.create_task(self._text_to_speech_task.run())
                group.create_task(self._audio_play_task.run())
                await self._stop_event.wait()
                group.create_task(force_terminate_pipeline())
        except* TerminatePipeline:
            pass

    def nudge(self) -> None:
        """Nudge the pipeline by toggling the audio capture state."""
        self._audio_capture_task.enqueue(None)

    def stop(self) -> None:
        """Request a graceful pipeline shutdown."""
        self._stop_event.set()
