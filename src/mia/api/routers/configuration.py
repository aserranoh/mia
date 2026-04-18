
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from mia import (
    Configuration,
    ConfigurationManager,
    WhisperModel,
    GeminiModel,
    Settings,
    list_language_options,
)

from ..dependencies import get_configuration_manager, get_settings


class ConfigurationPatch(BaseModel):
    """Partial configuration update model."""

    whisper_model: WhisperModel | None = None
    language: str | None = None
    system_prompt: str | None = None
    gemini_model: GeminiModel | None = None
    gemini_key: str | None = None


router = APIRouter(
    prefix="/configuration",
    tags=["configuration"],
)


@router.get("", response_model=Configuration)
def read_configuration(
    configuration_manager: ConfigurationManager = Depends(
        get_configuration_manager,
    ),
) -> Configuration:
    """Endpoint to retrieve the current configuration."""
    return configuration_manager.configuration


@router.patch("", response_model=Configuration)
def update_configuration(
    update: ConfigurationPatch,
    configuration_manager: ConfigurationManager = Depends(get_configuration_manager),
) -> Configuration:
    """Endpoint to update the current configuration."""
    changes = update.model_dump(exclude_unset=True, exclude_none=True)
    updated = configuration_manager.configuration.model_copy(update=changes)
    configuration_manager.configuration = updated
    configuration_manager.write_configuration()
    return updated


@router.get("/options/whisper-models/", response_model=list[str])
def list_whisper_models() -> list[str]:
    """List all available whisper models from the enum options."""
    return [model.value for model in WhisperModel]


@router.get("/options/languages/", response_model=list[str])
def list_languages(settings: Settings = Depends(get_settings)) -> list[str]:
    """List available languages inferred from .onnx files in the voices folder."""
    voices_dir = settings.voices_dir
    if not voices_dir.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Voices directory not found: {voices_dir}",
        )
    return list_language_options(voices_dir)


@router.get("/options/gemini-models/", response_model=list[str])
def list_gemini_models() -> list[str]:
    """List all available Gemini models from the enum options."""
    return [model.value for model in GeminiModel]