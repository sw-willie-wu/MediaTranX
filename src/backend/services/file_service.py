"""
檔案服務模組
處理檔案上傳、下載和管理
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

from backend.api.schemas.common import FileInfo

logger = logging.getLogger(__name__)


class FileService:
    """
    檔案服務
    管理上傳檔案和處理結果
    """

    _instance: Optional["FileService"] = None

    def __new__(cls, *args, **kwargs):
        """單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, base_dir: Optional[str] = None):
        if self._initialized:
            return

        # 設定基礎目錄
        if base_dir:
            self._base_dir = Path(base_dir)
        else:
            # 預設使用專案根目錄下的 temp 和 output
            project_root = Path(__file__).parent.parent.parent.parent
            self._base_dir = project_root

        self._upload_dir = self._base_dir / "temp" / "uploads"
        self._output_dir = self._base_dir / "output"

        # 確保目錄存在
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # 檔案索引
        self._files: Dict[str, FileInfo] = {}

        self._initialized = True
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
        mime_type: Optional[str] = None
    ) -> FileInfo:
        """
        儲存上傳的檔案

        Args:
            filename: 原始檔名
            content: 檔案內容
            mime_type: MIME 類型（可選，會自動偵測）

        Returns:
            FileInfo: 檔案資訊
        """
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        file_path = self._upload_dir / safe_filename

        # 寫入檔案
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        # 偵測 MIME 類型
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type is None:
                mime_type = "application/octet-stream"

        # 建立檔案資訊
        file_info = FileInfo(
            file_id=file_id,
            filename=safe_filename,
            original_filename=filename,
            file_path=str(file_path),
            file_size=len(content),
            mime_type=mime_type,
            created_at=datetime.utcnow()
        )

        self._files[file_id] = file_info
        logger.info(f"File uploaded: {file_id} ({filename}, {len(content)} bytes)")

        return file_info

    async def save_upload_stream(
        self,
        filename: str,
        file_stream,
        mime_type: Optional[str] = None
    ) -> FileInfo:
        """
        串流方式儲存上傳的檔案

        Args:
            filename: 原始檔名
            file_stream: 檔案串流（SpooledTemporaryFile 或類似物件）
            mime_type: MIME 類型

        Returns:
            FileInfo: 檔案資訊
        """
        file_id = str(uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        file_path = self._upload_dir / safe_filename

        # 串流寫入
        file_size = 0
        async with aiofiles.open(file_path, 'wb') as f:
            while chunk := await file_stream.read(1024 * 1024):  # 1MB chunks
                await f.write(chunk)
                file_size += len(chunk)

        # 偵測 MIME 類型
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type is None:
                mime_type = "application/octet-stream"

        file_info = FileInfo(
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

    def get_file(self, file_id: str) -> Optional[FileInfo]:
        """取得檔案資訊"""
        return self._files.get(file_id)

    def get_file_path(self, file_id: str) -> Optional[Path]:
        """取得檔案路徑"""
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
        建立輸出檔案路徑

        Args:
            original_filename: 原始檔名
            suffix: 檔名後綴（如 "_upscaled"）
            ext: 副檔名（可選，預設保持原本）

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
    ) -> FileInfo:
        """
        註冊輸出檔案

        Args:
            file_id: 檔案 ID
            file_path: 檔案路徑
            original_filename: 原始檔名
            mime_type: MIME 類型

        Returns:
            FileInfo: 檔案資訊
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Output file not found: {file_path}")

        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type is None:
                mime_type = "application/octet-stream"

        file_info = FileInfo(
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
        刪除檔案

        Args:
            file_id: 檔案 ID

        Returns:
            是否成功刪除
        """
        file_info = self._files.get(file_id)
        if file_info is None:
            return False

        try:
            file_path = Path(file_info.file_path)
            if file_path.exists():
                file_path.unlink()

            del self._files[file_id]
            logger.info(f"File deleted: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False

    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """
        清理過期的暫存檔案

        Args:
            max_age_hours: 最大保留時間（小時）

        Returns:
            清理的檔案數量
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


# 全域檔案服務實例
_file_service: Optional[FileService] = None


def get_file_service() -> FileService:
    """取得全域檔案服務實例"""
    global _file_service
    if _file_service is None:
        _file_service = FileService()
    return _file_service
