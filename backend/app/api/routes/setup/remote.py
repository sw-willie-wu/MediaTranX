"""
Remote API connection management routes.
"""
from __future__ import annotations
import asyncio
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, Response
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
    chunk_ctx_budget: Optional[int] = None


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    enabled: Optional[bool] = None
    chunk_ctx_budget: Optional[int] = None


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
        chunk_ctx_budget=data.chunk_ctx_budget,
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
        **data.model_dump(exclude_unset=True),
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
    return await asyncio.to_thread(
        service.test_connection, data.provider, data.endpoint, data.api_key
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
    models = await asyncio.to_thread(service.list_remote_models_by_conn, conn_id)
    return {"models": models}


@router.post("/remote/connections/{conn_id}/key")
@inject
async def reveal_connection_key(
    conn_id: int,
    response: Response,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """Reveal the full plaintext key for ONE connection (user-initiated,
    loopback). Secret is in the response body (not URL) -> not access-logged.
    POST + no-store so intermediaries/history don't cache the secret."""
    response.headers["Cache-Control"] = "no-store"
    return {"api_key": service.reveal_key(conn_id)}
