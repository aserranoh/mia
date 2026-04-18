
from fastapi import Depends, HTTPException, Request

from mia import ConfigurationManager, FilesManager, Settings


def get_settings(request: Request) -> Settings:
    """Return runtime settings loaded at application startup."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(status_code=500, detail="Application settings are not initialized")
    return settings


def get_configuration_manager(
    settings: Settings = Depends(get_settings),
) -> ConfigurationManager:
    """Load the configuration from the specified file."""
    try:
        return ConfigurationManager(configuration_path=settings.config_path)
    except ValueError as exc:
        print(f"Error reading configuration file: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Error reading configuration file: {exc}",
        ) from exc


def get_files_manager(
    configuration_manager: ConfigurationManager = Depends(get_configuration_manager),
    settings: Settings = Depends(get_settings),
) -> "FilesManager":
    """Initialize and return a FilesManager instance."""
    files_manager = FilesManager(
        root_path=settings.files_dir,
        files_descriptors=configuration_manager.configuration.uploaded_files,
    )
    files_manager.updated_descriptors_callback.append(
        configuration_manager.update_files,
    )
    return files_manager