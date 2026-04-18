
import asyncio
import argparse
import logging
from pathlib import Path
import signal

from mia import ConfigurationManager, Settings
from nats.aio.msg import Msg

from .bus import Bus
from .llm import GeminiLLM, DummyLLM
from .pipeline import Pipeline
from .stt import WhisperSpeechToTextEngine
from .tts import PiperTextToSpeechEngine, get_voice_file_from_language


DEFAULT_CONFIG_FILE = Path("/etc/maia/config.json")
NUDGE_TOPIC = "maia.interaction.toggle"
SPEAKER_ID = 1


async def _run_pipeline(pipeline: Pipeline) -> None:
    """Run pipeline workers until interrupted."""
    loop = asyncio.get_running_loop()
    stop_requested = asyncio.Event()

    loop.add_signal_handler(signal.SIGINT, stop_requested.set)
    loop.add_signal_handler(signal.SIGTERM, stop_requested.set)
    pipeline_task = asyncio.create_task(pipeline.run())

    try:
        await stop_requested.wait()
    finally:
        pipeline.stop()
        await pipeline_task


def _load_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Mia robot core.")
    parser.add_argument(
        "--settings",
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help="Path to the configuration file.",
    )
    return parser.parse_args()


async def async_main() -> None:
    """Main entry point for the Mia robot core."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = _load_args()
    settings = Settings.model_validate_json(args.settings.read_text())
    config = ConfigurationManager(
        configuration_path=settings.config_path,
    ).configuration

    bus = Bus()
    async def _toggle_callback(msg: Msg) -> None:
        pipeline.nudge()
    await bus.subscribe(NUDGE_TOPIC, _toggle_callback)

    pipeline = Pipeline(
        stt_engine=WhisperSpeechToTextEngine(
            model=config.get_whisper_model(),
            language=config.language,
        ),
        llm=GeminiLLM(
            system_prompt=config.system_prompt,
            model=config.gemini_model,
            api_key=config.gemini_key,
        ),
        #llm=DummyLLM(),
        tts_engine=PiperTextToSpeechEngine(
            voice_file=get_voice_file_from_language(
                config.language,
                settings.voices_dir,
            ),
            speaker_id=SPEAKER_ID,
        ),
        bus=bus,
    )

    await _run_pipeline(pipeline)


def main() -> None:
    """Synchronous entry point for the Mia robot core."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()