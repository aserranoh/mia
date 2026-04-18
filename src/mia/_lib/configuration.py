
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .files import UploadedFileMetadata


class WhisperModel(StrEnum):
    """Enumeration of supported Whisper models."""
    
    BASE = "base"
    SMALL = "small"


class GeminiModel(StrEnum):
    """Enumeration of supported Gemini models."""
    
    FLASH_3_PREVIEW = "gemini-3-flash-preview"
    FLASH_2_5_LITE = "gemini-2.5-flash-lite"


class Configuration(BaseModel):
    """Configuration model for the Mia robot core."""
    
    whisper_model: WhisperModel = WhisperModel.BASE
    language: str = "en"
    system_prompt: str = ""
    gemini_model: GeminiModel = GeminiModel.FLASH_2_5_LITE
    gemini_key: str = ""
    uploaded_files: list[UploadedFileMetadata] = []

    def get_whisper_model(self) -> str:
        """Return the appropriate Whisper model name based on the language."""
        if self.language == "en":
            return f"{self.whisper_model}.en"
        return self.whisper_model


class ConfigurationManager(BaseModel):
    """Manager for loading and saving the configuration to disk."""

    configuration_path: Path
    configuration: Configuration = Field(init=False, default_factory=Configuration)

    def model_post_init(self, context: Any) -> None:
        """Load the configuration from disk after initialization."""
        self.configuration = Configuration.model_validate_json(
            self.configuration_path.read_text(),
        )

    def write_configuration(self) -> None:
        """Persist configuration model to disk."""
        self.configuration_path.parent.mkdir(parents=True, exist_ok=True)
        self.configuration_path.write_text(self.configuration.model_dump_json(indent=2))

    def update_files(self, files_descriptors: list[UploadedFileMetadata]) -> None:
        """Update the list of uploaded files in the configuration."""
        self.configuration.uploaded_files = files_descriptors
        self.write_configuration()