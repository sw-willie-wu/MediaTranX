"""Pipeline recipe CRUD routes（route → DI service → DAO，照 agent sessions 模式）."""
from __future__ import annotations

from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.handler.exceptions import NotFoundError
from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.pipeline.recipe_service import PipelineRecipeService

router = APIRouter()


class RecipeIn(BaseModel):
    name: str = Field(default="", max_length=200)
    graph: str = Field(default="{}")  # Recipe JSON 原文（前端 revalidate-on-load）


class RecipePatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    graph: str | None = None


class RecipeListItem(BaseModel):
    """清單 DTO——不含 graph blob（客戶端清單只用 meta）。"""
    id: str
    name: str
    created_at: str
    updated_at: str


class RecipeOut(RecipeListItem):
    graph: str


@router.get("/recipes", response_model=list[RecipeListItem])
@inject
async def list_recipes(
    service: PipelineRecipeService = Depends(Provide[AppContainer.pipeline_recipe_service]),
):
    return [RecipeListItem(**r.model_dump(exclude={"graph"})) for r in service.list_recipes()]


@router.get("/recipes/{recipe_id}", response_model=RecipeOut)
@inject
async def get_recipe(
    recipe_id: str,
    service: PipelineRecipeService = Depends(Provide[AppContainer.pipeline_recipe_service]),
):
    rec = service.get(recipe_id)
    if rec is None:
        raise NotFoundError(f"Recipe not found: {recipe_id}")
    return RecipeOut(**rec.model_dump())


@router.post("/recipes", response_model=RecipeOut)
@inject
async def create_recipe(
    body: RecipeIn,
    service: PipelineRecipeService = Depends(Provide[AppContainer.pipeline_recipe_service]),
):
    rec = service.create(name=body.name, graph=body.graph)
    return RecipeOut(**rec.model_dump())


@router.put("/recipes/{recipe_id}", response_model=RecipeOut)
@inject
async def update_recipe(
    recipe_id: str,
    body: RecipePatch,
    service: PipelineRecipeService = Depends(Provide[AppContainer.pipeline_recipe_service]),
):
    rec = service.update(recipe_id, name=body.name, graph=body.graph)
    if rec is None:
        raise NotFoundError(f"Recipe not found: {recipe_id}")
    return RecipeOut(**rec.model_dump())


@router.delete("/recipes/{recipe_id}")
@inject
async def delete_recipe(
    recipe_id: str,
    service: PipelineRecipeService = Depends(Provide[AppContainer.pipeline_recipe_service]),
):
    if not service.delete(recipe_id):
        raise NotFoundError(f"Recipe not found: {recipe_id}")
    return {"ok": True}
