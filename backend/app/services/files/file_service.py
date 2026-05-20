"""
File service module.
Handles file upload, download, and management.
"""
import aiofiles
import json
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from app.schemas.file import FileData
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
        # Resolve to absolute at startup so all downstream file paths are
        # absolute — frontend/Electron reads them directly without re-resolving
        # against their own cwd (which differs from backend's).
        self._upload_dir = (base_temp / "uploads").resolve()
        self._output_dir = (base_temp / "results").resolve()

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
        from app.handler.exceptions import FileNotFoundError_
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError_(f"File not found: {file_path}")

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
        """Get file information; returns None if not registered (use `require_file`
        for the raise-on-missing path)."""
        return self._files.get(file_id)

    def get_file_name(self, file_id: Optional[str]) -> Optional[str]:
        """Resolve a file_id to its original filename, or None.

        Shared resolve helper for task responses / history persistence:
        a ``None`` file_id or an unregistered file both yield ``None`` (no raise).
        """
        if not file_id:
            return None
        fd = self.get_file(file_id)
        return fd.original_filename if fd else None

    def list_files(self) -> list[FileData]:
        """Return all registered files (avoids route-layer access to _files dict)."""
        return list(self._files.values())

    def set_saved_path(self, file_id: str, saved_path: str) -> None:
        """Persist the user-chosen save destination to FileData.metadata + sidecar.

        Raises FileNotFoundError_ if the file is not registered.
        Raises ValueError if saved_path is not absolute.
        Raises OSError if sidecar write fails.
        """
        if not Path(saved_path).is_absolute():
            raise ValueError("saved_path must be absolute")
        fd = self.require_file(file_id)
        fd.metadata = {**(fd.metadata or {}), "saved_path": saved_path}
        self.write_sidecar(file_id)

    def require_file(self, file_id: str) -> FileData:
        """Get file information; raises FileNotFoundError_ (→ 404) if not registered.

        Use this in submit/execute paths that need the file to exist. Keep
        `get_file` for optional lookups (e.g. best-effort preview reads).
        """
        from app.handler.exceptions import FileNotFoundError_

        fd = self._files.get(file_id)
        if fd is None:
            raise FileNotFoundError_(f"File not found: {file_id}")
        return fd

    def require_file_on_disk(self, file_id: str) -> FileData:
        """Get file information and verify the on-disk payload exists.

        Raises FileNotFoundError_ (→ 404) if either registration or disk file
        is missing. Used by the download endpoint to serve bytes.
        """
        from app.handler.exceptions import FileNotFoundError_

        fd = self.require_file(file_id)
        if not Path(fd.file_path).exists():
            raise FileNotFoundError_(f"File not found on disk: {file_id}")
        return fd

    def get_file_path(self, file_id: str) -> Optional[Path]:
        """Get file path."""
        file_info = self._files.get(file_id)
        if file_info:
            return Path(file_info.file_path)
        return None

    def read_text(self, file_id: str) -> Optional[str]:
        """Read a registered output file as UTF-8 text.

        Returns None if the file_id is not registered, the path is missing,
        or any I/O / decode error occurs.
        """
        info = self.get_file(file_id)
        if info is None or not info.file_path:
            return None
        try:
            with open(info.file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError) as e:
            logger.debug(f"read_text({file_id}) failed: {e}")
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
            from app.handler.exceptions import FileNotFoundError_
            raise FileNotFoundError_(f"Output file not found: {file_path}")

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

    # ── Sidecar metadata (Results drawer) ──────────────────────────

    def _sidecar_path(self, file_id: str) -> Path:
        return self._output_dir / f"{file_id}.meta.json"

    def write_sidecar(self, file_id: str) -> None:
        """Serialize a registered output's FileData to a sidecar .meta.json.

        Called after metadata is filled in (tool_id, source_file_id, show_in_results).
        """
        fd = self._files.get(file_id)
        if fd is None:
            return
        payload = {
            "file_id": fd.file_id,
            "filename": fd.filename,
            "original_filename": fd.original_filename,
            "file_path": fd.file_path,
            "file_size": fd.file_size,
            "mime_type": fd.mime_type,
            "source_dir": fd.source_dir,
            "created_at": fd.created_at.isoformat(),
            "metadata": fd.metadata or {},
        }
        try:
            self._sidecar_path(file_id).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            # In-memory registration is still usable; just log and continue so
            # the caller's task doesn't crash post-success.
            logger.warning(f"write_sidecar failed for {file_id}: {e}")

    def tag_as_result(
        self,
        file_id: str,
        tool_id: str,
        source_file_id: Optional[str] = None,
    ) -> None:
        """Mark a registered output as Results-visible and persist sidecar.

        Single entry point for both TaskManager's auto-tag and one-off
        endpoints (e.g. audio.midi.render which bypasses TaskManager).
        """
        fd = self._files.get(file_id)
        if fd is None:
            return
        fd.metadata = {
            **(fd.metadata or {}),
            "tool_id": tool_id,
            "source_file_id": source_file_id,
            "show_in_results": True,
        }
        self.write_sidecar(file_id)

    def scan_output_dir(self) -> None:
        """On startup, rebuild _files from sidecars in output_dir.

        Only files that have a matching `<file_id>.meta.json` are loaded.
        Orphan files (history-policy leftovers from previous sessions) are
        skipped — they remain on disk until the user clears temp manually.
        """
        for sidecar in self._output_dir.glob("*.meta.json"):
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                file_path = Path(data["file_path"])
                if not file_path.exists():
                    # File gone but sidecar remains — clean up orphan sidecar
                    sidecar.unlink(missing_ok=True)
                    continue
                fd = FileData(
                    file_id=data["file_id"],
                    filename=data["filename"],
                    original_filename=data["original_filename"],
                    file_path=data["file_path"],
                    file_size=data["file_size"],
                    mime_type=data["mime_type"],
                    source_dir=data.get("source_dir"),
                    created_at=datetime.fromisoformat(data["created_at"]),
                    metadata=data.get("metadata") or {},
                )
                if fd.file_id in self._files:
                    logger.warning(
                        f"Duplicate sidecar for file_id {fd.file_id} (keeping later)"
                    )
                self._files[fd.file_id] = fd
                logger.info(f"Restored output from sidecar: {fd.file_id} ({fd.filename})")
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                # Unparseable sidecar — quarantine rather than spam the log
                # on every restart.
                logger.warning(f"Removing unparseable sidecar {sidecar.name}: {e}")
                sidecar.unlink(missing_ok=True)

    def get_output_files(self) -> list[FileData]:
        """Return Results outputs sorted newest-first (stable across restart,
        since dict insertion order depends on sidecar glob order)."""
        files = [
            fd for fd in self._files.values()
            if (fd.metadata or {}).get("show_in_results") is True
        ]
        files.sort(key=lambda f: f.created_at, reverse=True)
        return files

    def get_temp_stats(self) -> dict:
        """Return byte size of upload/output directories."""
        def _dir_size(d: Path) -> int:
            return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
        upload_bytes = _dir_size(self._upload_dir)
        output_bytes = _dir_size(self._output_dir)
        return {
            "upload_bytes": upload_bytes,
            "output_bytes": output_bytes,
            "total_bytes": upload_bytes + output_bytes,
        }

    def delete_file(self, file_id: str) -> None:
        """Delete a registered file. Raises FileNotFoundError_ if unknown."""
        file_info = self.require_file(file_id)

        file_path = Path(file_info.file_path)
        # Only delete files within the temp directory to avoid deleting user's original files (from register_local_file)
        is_managed = (
            str(file_path).startswith(str(self._upload_dir)) or
            str(file_path).startswith(str(self._output_dir))
        )
        if is_managed and file_path.exists():
            file_path.unlink()

        self._sidecar_path(file_id).unlink(missing_ok=True)
        del self._files[file_id]
        logger.info(f"File deleted: {file_id}")

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
