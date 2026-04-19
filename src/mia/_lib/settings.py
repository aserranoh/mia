
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """Application settings loaded from command-line arguments."""
    
    config_path: Path = Path("/var/lib/maia/config.json")
    voices_dir: Path = Path("/usr/share/maia/voices")
    files_dir: Path = Path("/var/lib/maia/files")
    ui_dir: Path = Path("/usr/share/maia/ui")


def load_settings(settings_file: Path) -> Settings:
    """Load settings from JSON and mutate the existing module-level settings."""
    return Settings.model_validate_json(settings_file.read_text())