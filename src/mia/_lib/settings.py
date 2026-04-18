
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """Application settings loaded from command-line arguments."""
    
    config_path: Path = Path("/var/lib/maia/config.json")
    voices_dir: Path = Path("/var/lib/maia/voices")
    files_dir: Path = Path("/var/lib/maia/files")


def load_settings(settings_file: Path) -> Settings:
    """Load settings from JSON and mutate the existing module-level settings."""
    return Settings.model_validate_json(settings_file.read_text())