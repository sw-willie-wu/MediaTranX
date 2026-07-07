"""
Pipeline recipe model.

One row per saved pipeline graph. `graph` stores the frontend Recipe JSON
verbatim (nodes/edges/params/positions) — the frontend re-validates on load
(revalidate-on-load tolerance), so no schema coupling here.
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import SQLModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid4())


class PipelineRecipe(SQLModel, table=True):
    """A saved pipeline graph."""
    __tablename__ = "pipeline_recipes"

    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str = Field(default="")
    graph: str = Field(default="{}")  # Recipe JSON (frontend-owned shape)
    created_at: str = Field(default_factory=_now_iso)  # ISO 8601
    updated_at: str = Field(default_factory=_now_iso)  # ISO 8601
