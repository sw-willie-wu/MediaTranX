"""
Cross-layer shared file domain models.

FileData is shared by services and api layers
to avoid services depending on the API layer.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class FileData:
    """File internal state (used by FileService)."""
    file_id: str
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    mime_type: str
    source_dir: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[dict] = None
