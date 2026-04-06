"""
Remote API 連線管理路由
"""
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.init.container import AppContainer
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
    """取得所有連線設定"""
    return {"connections": service.get_connections(provider)}


@router.post("/remote/connections")
@inject
async def add_connection(
    data: ConnectionCreate,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """新增連線"""
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
    """更新連線"""
    conn = service.update_connection(
        conn_id,
        **data.model_dump(exclude_none=True),
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn


@router.delete("/remote/connections/{conn_id}")
@inject
async def delete_connection(
    conn_id: int,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """刪除連線"""
    if not service.delete_connection(conn_id):
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"ok": True}


@router.post("/remote/test")
@inject
async def test_connection(
    data: ConnectionTest,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """測試連線"""
    try:
        return service.test_connection(
            provider=data.provider,
            endpoint=data.endpoint,
            api_key=data.api_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/remote/models")
@inject
async def list_remote_models(
    provider: str,
    endpoint: str,
    api_key: Optional[str] = None,
    service: RemoteService = Depends(Provide[AppContainer.remote_service]),
):
    """列舉遠端可用模型"""
    try:
        return {"models": service.list_remote_models(provider, endpoint, api_key)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
