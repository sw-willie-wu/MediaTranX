"""
Remote API connection management routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.setup.remote_service import RemoteService

router = APIRouter()


class ConnectionCreate(BaseModel):
    provider: str
    name: str
    endpoint: str
    api_key: Optional[str] = None


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None


class ConnectionTest(BaseModel):
    provider: str
    endpoint: str
    api_key: Optional[str] = None


@router.get("/remote/connections")
@inject
async def get_connections(
    provider: Optional[str] = None,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """Get all connection settings."""
    return {"connections": service.get_connections(provider)}


@router.post("/remote/connections")
@inject
async def add_connection(
    data: ConnectionCreate,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """Add a new connection."""
    conn = service.add_connection(
        provider=data.provider,
        name=data.name,
        endpoint=data.endpoint,
        api_key=data.api_key,
    )
    return conn


@router.put("/remote/connections/{conn_id}")
@inject
async def update_connection(
    conn_id: int,
    data: ConnectionUpdate,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """Update a connection."""
    return service.update_connection(
        conn_id,
        **data.model_dump(exclude_none=True),
    )


@router.delete("/remote/connections/{conn_id}")
@inject
async def delete_connection(
    conn_id: int,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """Delete a connection."""
    service.delete_connection(conn_id)
    return {"ok": True}


@router.post("/remote/test")
@inject
async def test_connection(
    data: ConnectionTest,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """Test a connection."""
    return service.test_connection(
        provider=data.provider,
        endpoint=data.endpoint,
        api_key=data.api_key,
    )


@router.get("/remote/models")
@inject
async def list_remote_models(
    conn_id: int,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """List available models for a SAVED connection.

    Takes conn_id only — the api_key is resolved server-side. Previously this
    accepted provider/endpoint/api_key as query params, which leaked the key
    into the URL → uvicorn access logs in plaintext.
    """
    return {"models": service.list_remote_models_by_conn(conn_id)}
