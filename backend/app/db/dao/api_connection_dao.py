"""
Remote API connection settings DAO.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.db.database import get_engine
from app.db.models.api_connection import ApiConnection

logger = logging.getLogger(__name__)


class ApiConnectionDAO:
    """Remote API connection settings data access."""

    def create(
        self,
        provider: str,
        name: str,
        endpoint: str,
        api_key: Optional[str] = None,
    ) -> ApiConnection:
        """Add a connection setting."""
        with Session(get_engine()) as session:
            conn = ApiConnection(
                provider=provider,
                name=name,
                endpoint=endpoint,
                api_key=api_key,
            )
            session.add(conn)
            session.commit()
            session.refresh(conn)
            logger.info(f"API connection created: {provider} - {name}")
            return conn

    def get_by_id(self, conn_id: int) -> Optional[ApiConnection]:
        """Get a single connection."""
        with Session(get_engine()) as session:
            return session.get(ApiConnection, conn_id)

    def get_by_provider(self, provider: str) -> list[ApiConnection]:
        """Get all connections for a specific provider."""
        with Session(get_engine()) as session:
            stmt = select(ApiConnection).where(ApiConnection.provider == provider)
            return list(session.exec(stmt).all())

    def get_all(self) -> list[ApiConnection]:
        """Get all connections."""
        with Session(get_engine()) as session:
            stmt = select(ApiConnection).order_by(ApiConnection.provider)
            return list(session.exec(stmt).all())

    def get_enabled(self, provider: Optional[str] = None) -> list[ApiConnection]:
        """Get all enabled connections."""
        with Session(get_engine()) as session:
            stmt = select(ApiConnection).where(ApiConnection.enabled == True)
            if provider:
                stmt = stmt.where(ApiConnection.provider == provider)
            return list(session.exec(stmt).all())

    def update(
        self,
        conn_id: int,
        name: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> Optional[ApiConnection]:
        """Update a connection setting."""
        with Session(get_engine()) as session:
            conn = session.get(ApiConnection, conn_id)
            if not conn:
                return None
            if name is not None:
                conn.name = name
            if endpoint is not None:
                conn.endpoint = endpoint
            # Security: only overwrite the stored key when a non-empty value is
            # supplied. Both None (omitted) and "" (blank field) mean "keep the
            # existing key" — a blank value must never silently wipe a secret.
            if api_key:
                conn.api_key = api_key
            if enabled is not None:
                conn.enabled = enabled
            conn.updated_at = datetime.now().isoformat()
            session.commit()
            session.refresh(conn)
            logger.info(f"API connection updated: {conn.provider} - {conn.name}")
            return conn

    def delete(self, conn_id: int) -> bool:
        """Delete a connection setting."""
        with Session(get_engine()) as session:
            conn = session.get(ApiConnection, conn_id)
            if not conn:
                return False
            session.delete(conn)
            session.commit()
            logger.info(f"API connection deleted: {conn.provider} - {conn.name}")
            return True
