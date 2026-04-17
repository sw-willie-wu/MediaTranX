"""Video summary feature subpackage (single-consumer helpers).

Public entry point: `VideoSummaryService` (from `service`). Parse helpers and
markdown composition live in sibling modules.
"""
from app.services.video.summary.service import VideoSummaryService

__all__ = ["VideoSummaryService"]
