"""
File service module.
Handles file upload, download, and management.
"""
import aiofiles
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from app.models.file import FileData
from app.init.configs import SETTINGS

logger = logging.getLogger(__name__)


class FileService:
    """File upload, output registration, and lifecycle management service."""

    def __init__(self, base_dir: Optional[str] = None):
        # Set base directory (all intermediate files go to temp; user picks destination via saveFileDialog)
        if base_dir:
            base_temp = Path(base_dir) / "temp"
        else:
            base_temp = SETTINGS.path.temp
            base_temp.mkdir(parents=True, exist_ok=True)
        self._upload_dir = base_temp / "uploads"
        self._output_dir = base_temp / "results"

        # Ensure directories exist
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # File index
        self._files: Dict[str, FileData] = {}

        logger.info(f"FileService initialized. Upload dir: {self._upload_dir}")

    @property
    def upload_dir(self) -> Path:
        return self._upload_dir

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    async def save_upload(
        self,
        filename: str,
        content: bytes,
        mime_type: Optional[str] = None,
        source_dir: Optional[str] = None
    ) -> FileData:
        """
        Save an uploaded file.

        Args:
            filename: Original filename
            content: File content bytes
            mime_type: MIME type (optional, auto-detected)
            source_dir: Source directory (original directory on the user's machine)

        Returns:
            FileData: File information
        """
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        file_path = self._upload_dir / safe_filename

        # Write file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        # Detect MIME type
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type is None:
                mime_type = "application/octet-stream"

        # Create file info
        file_info = FileData(
            file_id=file_id,
            filename=safe_filename,
            original_filename=filename,
            file_path=str(file_path),
            file_size=len(content),
            mime_type=mime_type,
            source_dir=source_dir,
            created_at=datetime.utcnow()
        )

        self._files[file_id] = file_info
        logger.info(f"File uploaded: {file_id} ({filename}, {len(content)} bytes)")

        return file_info

    def register_local_file(self, file_path: str) -> FileData:
        """
        Register a local file directly (no copy), for Electron local environment.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_id = str(uuid4())
        mime_type, _ = mimetypes.guess_type(path.name)
        if mime_type is None:
            mime_type = "application/octet-stream"

        file_info = FileData(
            file_id=file_id,
            filename=path.name,
            original_filename=path.name,
            file_path=str(path),
            file_size=path.stat().st_size,
            mime_type=mime_type,
            source_dir=str(path.parent),
            created_at=datetime.utcnow()
        )

        self._files[file_id] = file_info
        logger.info(f"File registered (local): {file_id} ({path.name}, {file_info.file_size} bytes)")
        return file_info

    async def save_upload_stream(
        self,
        filename: str,
        file_stream,
        mime_type: Optional[str] = None
    ) -> FileData:
        """
        Save an uploaded file via streaming.

        Args:
            filename: Original filename
            file_stream: File stream (SpooledTemporaryFile or similar)
            mime_type: MIME type

        Returns:
            FileData: File information
        """
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        file_path = self._upload_dir / safe_filename

        # Stream write
        file_size = 0
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file_stream.read(1024 * 1024):  # 1MB chunks
                await f.write(chunk)
                file_size += len(chunk)

        # Detect MIME type
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type is None:
                mime_type = "application/octet-stream"

        file_info = FileData(
            file_id=file_id,
            filename=safe_filename,
            original_filename=filename,
            file_path=str(file_path),
            file_size=file_size,
            mime_type=mime_type,
            created_at=datetime.utcnow()
        )

        self._files[file_id] = file_info
        logger.info(f"File uploaded (stream): {file_id} ({filename}, {file_size} bytes)")

        return file_info

    def get_file(self, file_id: str) -> Optional[FileData]:
        """Get file information."""
        return self._files.get(file_id)

    def get_file_path(self, file_id: str) -> Optional[Path]:
        """Get file path."""
        file_info = self._files.get(file_id)
        if file_info:
            return Path(file_info.file_path)
        return None

    def create_output_path(
        self,
        original_filename: str,
        suffix: str = "",
        ext: Optional[str] = None
    ) -> tuple[str, Path]:
        """
        Create an output file path.

        Args:
            original_filename: Original filename
            suffix: Filename suffix (e.g., "_upscaled")
            ext: Extension (optional, keeps original by default)

        Returns:
            (file_id, file_path)
        """
        file_id = str(uuid4())
        original_path = Path(original_filename)

        if ext is None:
            ext = original_path.suffix

        output_filename = f"{original_path.stem}{suffix}_{file_id[:8]}{ext}"
        output_path = self._output_dir / output_filename

        return file_id, output_path

    def register_output(
        self,
        file_id: str,
        file_path: Path,
        original_filename: str,
        mime_type: Optional[str] = None
    ) -> FileData:
        """
        Register an output file.

        Args:
            file_id: File ID
            file_path: File path
            original_filename: Original filename
            mime_type: MIME type

        Returns:
            FileData: File information
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Output file not found: {file_path}")

        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type is None:
                mime_type = "application/octet-stream"

        file_info = FileData(
            file_id=file_id,
            filename=file_path.name,
            original_filename=original_filename,
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            mime_type=mime_type,
            created_at=datetime.utcnow()
        )

        self._files[file_id] = file_info
        logger.info(f"Output registered: {file_id} ({file_path.name})")

        return file_info

    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file.

        Args:
            file_id: File ID

        Returns:
            Whether deletion was successful
        """
        file_info = self._files.get(file_id)
        if file_info is None:
            return False

        try:
            file_path = Path(file_info.file_path)
            # Only delete files within the temp directory to avoid deleting user's original files (from register_local_file)
            is_managed = (
                str(file_path).startswith(str(self._upload_dir)) or
                str(file_path).startswith(str(self._output_dir))
            )
            if is_managed and file_path.exists():
                file_path.unlink()

            del self._files[file_id]
            logger.info(f"File deleted: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False

    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """
        Clean up expired temporary files (upload_dir only, filtered by age).

        Args:
            max_age_hours: Maximum retention time (hours)

        Returns:
            Number of files cleaned up
        """
        now = datetime.utcnow()
        to_delete = []

        for file_id, file_info in self._files.items():
            if str(self._upload_dir) in file_info.file_path:
                age = (now - file_info.created_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_delete.append(file_id)

        for file_id in to_delete:
            self.delete_file(file_id)

        return len(to_delete)

    def cleanup_all(self) -> int:
        """
        Remove all temporary files for this session (upload_dir + output_dir).
        Called when the application shuts down.

        Returns:
            Number of files cleaned up
        """
        to_delete = list(self._files.keys())
        for file_id in to_delete:
            self.delete_file(file_id)

        # Clean up remaining physical files in directories (not indexed)
        for directory in (self._upload_dir, self._output_dir):
            try:
                for f in directory.iterdir():
                    if f.is_file():
                        f.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"cleanup_all: failed to clean {directory}: {e}")

        logger.info(f"cleanup_all: removed {len(to_delete)} session files")
        return len(to_delete)
