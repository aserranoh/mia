
import asyncio
import argparse
import logging
from pathlib import Path
import signal

from mia import Settings

from .supervisor import PipelineSupervisor


DEFAULT_CONFIG_FILE = Path("/etc/maia/config.json")


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
    supervisor = PipelineSupervisor(settings=settings)

    loop = asyncio.get_running_loop()
    stop_requested = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, stop_requested.set)
    loop.add_signal_handler(signal.SIGTERM, stop_requested.set)

    await supervisor.start()
    try:
        await stop_requested.wait()
    finally:
        await supervisor.stop()


def main() -> None:
    """Synchronous entry point for the Mia robot core."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()