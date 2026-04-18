
from pathlib import Path
from typing import BinaryIO, Callable, Literal

from pydantic import BaseModel, Field


class UploadedFileMetadata(BaseModel):
    """Metadata for files uploaded to the Maia files directory."""

    path: Path = Field(default_factory=Path)
    description: str = ""
    content_type: str | None = None


class DirectoryEntry(BaseModel):
    """A single folder or file item in a directory listing."""

    path: Path
    type: Literal["folder", "file"]
    description: str = ""


UpdatedDescriptorsCallback = Callable[[list[UploadedFileMetadata]], None]


class FilesManager(BaseModel):
    """Manager for handling file operations and metadata in the files directory."""

    root_path: Path
    files_descriptors: list[UploadedFileMetadata] = Field(default_factory=list)
    updated_descriptors_callback: list[UpdatedDescriptorsCallback] = Field(
        default_factory=list,
    )


    def list_files(self, path: Path) -> list[DirectoryEntry]:
        """Helper function to list only files in a given path from the configuration."""
        requested_path = Path(path)
        return [
            DirectoryEntry(
                path=f.path,
                type="file",
                description=f.description,
            )
            for f in self.files_descriptors
            if Path(f.path).parent == requested_path
        ]

    def list_directories(self, path: Path) -> list[DirectoryEntry]:
        """Helper function to list only directories in a given path."""
        absolute_path = self.root_path / path
        if not absolute_path.is_relative_to(self.root_path) or not absolute_path.is_dir():
            return []
        return [
            DirectoryEntry(
                path=child.relative_to(self.root_path),
                type="folder",
            )
            for child in absolute_path.iterdir()
            if child.is_dir()
        ]
    
    def list_entries(self, path: Path) -> list[DirectoryEntry]:
        """List files and folders directly inside the requested folder."""
        files = sorted(self.list_files(path), key=lambda x: x.path.name)
        directories = sorted(self.list_directories(path), key=lambda x: x.path.name)
        return directories + files

    def create_folder(self, path: Path) -> None:
        """Create a new folder path under files directory (supports nested paths)."""
        new_folder_path = self.root_path / path
        if not new_folder_path.is_relative_to(self.root_path):
            raise ValueError("Invalid folder path")
        new_folder_path.mkdir()
    
    def rename_entry(self, path: Path, new_name: str) -> None:
        """Rename either a folder or a file in files directory."""
        old_path = self.root_path / path
        if not old_path.is_relative_to(self.root_path):
            raise ValueError("File or folder to rename does not exist")
        if old_path.is_dir():
            self._rename_directory(old_path, new_name)
        else:
            relative_old_path = old_path.relative_to(self.root_path)
            file_entry = self._get_file_entry(relative_old_path)
            if file_entry is None:
                raise ValueError("File metadata not found for the file to rename")
            self._rename_file(new_name, file_entry)

    def delete_entry(self, path: Path) -> None:
        """Delete a folder or file from files directory."""
        target_path = self.root_path / path
        if not target_path.is_relative_to(self.root_path) or not target_path.exists():
            raise ValueError("File or folder to delete does not exist")
        if target_path.is_dir():
            self._delete_directory(target_path)
        else:
            self._delete_file(target_path)

    def update_file_description(
        self,
        path: str,
        description: str,
    ) -> UploadedFileMetadata:
        """Update metadata description for a single uploaded file and return its relative path."""
        target_path = self.root_path / path
        if not target_path.is_relative_to(self.root_path) or target_path.is_dir() or not target_path.exists():
            raise ValueError("File to update does not exist")

        relative_path = target_path.relative_to(self.root_path)
        file_entry = self._get_file_entry(relative_path)
        if file_entry is None:
            raise ValueError("File metadata not found for the file to update")

        file_entry.description = description
        for callback in self.updated_descriptors_callback:
            callback(self.files_descriptors)
        return file_entry

    def add_file(
        self,
        path: Path,
        filename: str,
        content_type: str | None,
        data: BinaryIO,
        description: str,
    ) -> None:
        """Upload a file into the requested path and persist its metadata."""
        if not filename:
            raise ValueError("Uploaded file must have a filename")

        upload_dir = self.root_path / path
        if not upload_dir.is_relative_to(self.root_path):
            raise ValueError("Invalid upload path")
        if not upload_dir.is_dir():
            raise ValueError("Upload path does not exist")

        destination = upload_dir / filename
        if destination.exists():
            raise ValueError("A file with the same filename already exists in this path")

        destination.write_bytes(data.read())

        self.files_descriptors.append(
            UploadedFileMetadata(
                path=destination.relative_to(self.root_path),
                description=description,
                content_type=content_type,
            )
        )
        for callback in self.updated_descriptors_callback:
            callback(self.files_descriptors)

    def _get_file_entry(self, file_path: Path) -> UploadedFileMetadata | None:
        """Helper function to get the file metadata entry for a given file path."""
        for entry in self.files_descriptors:
            if Path(entry.path) == file_path:
                return entry
        return None

    def _rename_directory(self, old_path: Path, new_name: str) -> None:
        """Helper function to rename a directory."""
        new_path = old_path.parent / new_name
        if new_path.exists():
            raise ValueError("A file or folder with the new name already exists")
        old_path.rename(new_path)

    def _rename_file(self, new_name: str, file_entry: UploadedFileMetadata) -> None:
        """Helper function to rename a file and update its metadata."""
        old_path = self.root_path / file_entry.path
        new_path = old_path.parent / new_name
        if new_path.exists():
            raise ValueError("A file or folder with the new name already exists")
        old_path.rename(new_path)
        file_entry.path = new_path.relative_to(self.root_path)

        for callback in self.updated_descriptors_callback:
            callback(self.files_descriptors)
    
    def _delete_directory(self, target_path: Path) -> None:
        """Helper function to delete a directory."""
        if any(target_path.iterdir()):
            raise ValueError("Only empty directories can be deleted")
        target_path.rmdir()
    
    def _delete_file(self, target_path: Path) -> None:
        """Helper function to delete a file and its metadata."""
        relative_path = target_path.relative_to(self.root_path)
        self.files_descriptors = [
            entry
            for entry in self.files_descriptors
            if Path(entry.path) != relative_path
        ]
        target_path.unlink()
        for callback in self.updated_descriptors_callback:
            callback(self.files_descriptors)