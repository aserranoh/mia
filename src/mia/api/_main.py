
import argparse
import logging
from pathlib import Path

from fastapi import FastAPI
import uvicorn
from mia import Settings, load_settings

from .routers.configuration import router as configuration_router
from .routers.files import router as files_router


DEFAULT_CONFIG_FILE = Path("/etc/maia/config.json")


def _load_args() -> argparse.Namespace:
    """Parse command-line arguments for the API server."""
    parser = argparse.ArgumentParser(description="Run the Mia configuration API server.")
    parser.add_argument(
        "--settings",
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help="Path to the configuration file.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host interface to bind the API server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port where the API server listens.",
    )
    return parser.parse_args()


def create_app(settings: Settings) -> FastAPI:
    """Create and configure the API application instance."""
    app = FastAPI(title="Mia Configuration API")
    app.state.settings = settings
    app.include_router(configuration_router)
    app.include_router(files_router)
    return app


def main() -> None:
    """Main entry point for the Mia configuration API server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    command_line_args = _load_args()
    settings = load_settings(command_line_args.settings)

    app = create_app(settings)
    uvicorn.run(app, host=command_line_args.host, port=command_line_args.port)


if __name__ == "__main__":
    main()
