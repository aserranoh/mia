import asyncio
from asyncio import Task
from dataclasses import dataclass, field
import logging
from pathlib import Path

from mia import Configuration, ConfigurationManager, Settings

from .bus import Bus
from .llm import GeminiLLM
from .pipeline import Pipeline
from .stt import WhisperSpeechToTextEngine
from .tts import PiperTextToSpeechEngine, get_voice_file_from_language


logger = logging.getLogger("PipelineSupervisor")

SPEAKER_ID = 1
NUDGE_TOPIC = "maia.interaction.toggle"


@dataclass
class PipelineSupervisor:
    """Manage pipeline lifecycle and reload it when configuration changes."""

    settings: Settings
    poll_interval_seconds: float = 1.0
    debounce_seconds: float = 0.5
    stop_timeout_seconds: float = 5.0

    _bus: Bus = field(init=False, default_factory=Bus)
    _pipeline: Pipeline | None = field(init=False, default=None)
    _pipeline_task: Task[None] | None = field(init=False, default=None)
    _watch_task: Task[None] | None = field(init=False, default=None)
    _reload_lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)
    _running: bool = field(init=False, default=False)
    _active_signature: tuple[int, int] | None = field(init=False, default=None)
    _failed_signature: tuple[int, int] | None = field(init=False, default=None)

    async def start(self) -> None:
        """Load configuration, start pipeline, and begin polling for changes."""
        if self._running:
            return

        self._running = True
        await self._bus.subscribe(NUDGE_TOPIC, self._toggle_callback)
        started = await self.reload("startup")
        if not started:
            self._running = False
            raise RuntimeError("Unable to start pipeline from current configuration")
        self._watch_task = asyncio.create_task(
            self._watch_config_file_loop(),
            name="config-file-watcher",
        )

    async def stop(self) -> None:
        """Stop watcher and active pipeline."""
        if not self._running:
            return

        self._running = False

        if self._watch_task is not None:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            finally:
                self._watch_task = None

        await self._stop_pipeline()

    def nudge(self) -> None:
        """Forward interaction nudges to the currently running pipeline."""
        if self._pipeline is None:
            logger.warning("Ignoring nudge: pipeline is not running")
            return
        self._pipeline.nudge()

    async def _toggle_callback(self, _msg) -> None:
        """Handle interaction-toggle messages from the bus."""
        self.nudge()

    async def reload(self, reason: str) -> bool:
        """Rebuild and restart the pipeline from current configuration."""
        async with self._reload_lock:
            if not self._running:
                return False

            signature = self._read_config_signature(self.settings.config_path)
            if signature is not None and signature == self._failed_signature:
                return False

            try:
                configuration = self._load_configuration()
                new_pipeline = self._build_pipeline(configuration)
            except Exception:
                self._failed_signature = signature
                logger.exception("Pipeline reload failed (%s)", reason)
                return False

            old_pipeline = self._pipeline
            old_pipeline_task = self._pipeline_task

            if old_pipeline is not None and old_pipeline_task is not None:
                old_pipeline.stop()
                try:
                    await asyncio.wait_for(old_pipeline_task, timeout=self.stop_timeout_seconds)
                except asyncio.TimeoutError:
                    logger.error("Timed out while stopping previous pipeline instance")
                except Exception:
                    logger.exception("Previous pipeline stopped with an error")

            self._pipeline = new_pipeline
            self._pipeline_task = asyncio.create_task(
                new_pipeline.run(),
                name="voice-pipeline",
            )

            self._active_signature = signature
            self._failed_signature = None
            logger.info("Pipeline reload successful (%s)", reason)

            return True

    async def _stop_pipeline(self) -> None:
        """Stop and await the active pipeline task."""
        pipeline = self._pipeline
        pipeline_task = self._pipeline_task

        self._pipeline = None
        self._pipeline_task = None

        if pipeline is None or pipeline_task is None:
            return

        pipeline.stop()
        try:
            await asyncio.wait_for(pipeline_task, timeout=self.stop_timeout_seconds)
        except asyncio.TimeoutError:
            logger.error("Timed out while stopping pipeline")
        except Exception:
            logger.exception("Pipeline stopped with an error")

    async def _watch_config_file_loop(self) -> None:
        """Poll the configuration file and reload on meaningful changes."""
        while self._running:
            await asyncio.sleep(self.poll_interval_seconds)

            current_signature = self._read_config_signature(self.settings.config_path)
            if current_signature is None:
                continue
            if current_signature == self._active_signature:
                continue
            if current_signature == self._failed_signature:
                continue

            await asyncio.sleep(self.debounce_seconds)
            stable_signature = self._read_config_signature(self.settings.config_path)
            if stable_signature is None:
                continue
            if stable_signature != current_signature:
                continue
            if stable_signature == self._active_signature:
                continue

            await self.reload("configuration file changed")

    def _load_configuration(self) -> Configuration:
        """Load configuration from disk."""
        return ConfigurationManager(
            configuration_path=self.settings.config_path,
        ).configuration

    def _build_pipeline(self, configuration: Configuration) -> Pipeline:
        """Construct a new pipeline instance from configuration."""
        return Pipeline(
            stt_engine=WhisperSpeechToTextEngine(
                model=configuration.get_whisper_model(),
                language=configuration.language,
            ),
            llm=GeminiLLM(
                system_prompt=configuration.system_prompt,
                model=configuration.gemini_model,
                api_key=configuration.gemini_key,
            ),
            tts_engine=PiperTextToSpeechEngine(
                voice_file=get_voice_file_from_language(
                    configuration.language,
                    self.settings.voices_dir,
                ),
                speaker_id=SPEAKER_ID,
            ),
            bus=self._bus,
        )

    @staticmethod
    def _read_config_signature(config_path: Path) -> tuple[int, int] | None:
        """Return a compact file signature based on mtime and size."""
        try:
            stat = config_path.stat()
        except FileNotFoundError:
            return None
        return (stat.st_mtime_ns, stat.st_size)