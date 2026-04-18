
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Form
from mia import Settings

from mia import Configuration, DirectoryEntry, FilesManager
from mia.api.routers import configuration
from ..dependencies import get_files_manager


router = APIRouter(prefix="/files", tags=["files"])

@router.get("/")
def list_entries(
    path: str,
    files_manager: FilesManager = Depends(get_files_manager),
) -> list[DirectoryEntry]:
    """List files and folders directly inside the requested folder."""
    return files_manager.list_entries(Path(path))


@router.post("/folders/")
def create_folder(
    path: str = Body(
        description="Parent path where the folder will be created (empty for root)",
        default="",
        embed=True,
    ),
    name: str = Body(
        description="Name of the folder to create",
        pattern=r"^[^/]+$",
        embed=True,
    ),
    files_manager: FilesManager = Depends(get_files_manager),
) -> list[DirectoryEntry]:
    """Create a new folder path under files directory (supports nested paths)."""
    if name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Folder name cannot be '.' or '..'.")

    target_path = Path(path) / name

    try:
        files_manager.create_folder(target_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return files_manager.list_entries(target_path.parent)


@router.patch("/rename")
def rename_entry(
    path: str = Body(description="Current path of the file or folder to rename", embed=True),
    new_name: str = Body(
        description="New name for the file or folder",
        pattern=r"^[^/]+$",
        embed=True,
    ),
    files_manager: FilesManager = Depends(get_files_manager),
) -> list[DirectoryEntry]:
    """Rename either a folder or a file in files directory."""
    if new_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="New name cannot be '.' or '..'.")
    entry_path = Path(path)
    try:
        files_manager.rename_entry(entry_path, new_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return files_manager.list_entries(entry_path.parent)


@router.patch("/description")
def update_file_description(
    path: str = Body(description="Path of the file whose description will be updated", embed=True),
    description: str = Body(description="New description for the file", default="", embed=True),
    files_manager: FilesManager = Depends(get_files_manager),
) -> list[DirectoryEntry]:
    """Update description metadata for a file in files directory."""
    try:
        updated = files_manager.update_file_description(path, description)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return files_manager.list_entries(updated.path.parent)


@router.delete("/")
def delete_entry(
    path: str,
    files_manager: FilesManager = Depends(get_files_manager),
) -> list[DirectoryEntry]:
    """Delete a folder or file from files directory."""
    if Path(path) in {Path(""), Path(".")}:
        raise HTTPException(status_code=400, detail="Root directory cannot be deleted")
    entry = Path(path)
    try:
        files_manager.delete_entry(entry)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return files_manager.list_entries(entry.parent)


@router.post("/")
def upload_file(
    file: UploadFile = File(...),
    path: str = Form(
        description="Relative path of the folder to upload the file to (leave empty for root)",
        default="",
    ),
    description: str = Form(
        description="Optional description for the uploaded file",
        default="",
    ),
    files_manager: FilesManager = Depends(get_files_manager),
) -> list[DirectoryEntry]:
    """Upload a file to root or a nested folder and store metadata in configuration."""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename")
    target_path = Path(path)
    try:
        files_manager.add_file(
            path=target_path,
            filename=file.filename,
            content_type=file.content_type,
            data=file.file,
            description=description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return files_manager.list_entries(target_path)