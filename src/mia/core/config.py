
from typing import Literal

from pydantic import BaseModel


class Configuration(BaseModel):
    """Configuration model for the Mia robot core."""
    
    whisper_model: Literal["base", "small"] = "base"
    language: Literal["es_ES", "es_MX", "en", "ca"] = "en"
    system_prompt: str = ""
    gemini_model: Literal[
        "gemini-3-flash-preview",
        "gemini-2.5-flash-lite",
    ] = "gemini-2.5-flash-lite"
    gemini_key: str = ""

    def get_whisper_model(self) -> str:
        """Return the appropriate Whisper model name based on the language."""
        if self.language == "en":
            return f"{self.whisper_model}.en"
        return self.whisper_model