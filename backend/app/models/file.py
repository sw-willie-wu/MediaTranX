"""
跨層共用的檔案 domain models

FileData 供 services、api 層共用，
避免 services 反向依賴 api.schemas。
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class FileData:
    """檔案內部狀態（供 FileService 使用）"""
    file_id: str
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    source_dir: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[dict] = None
