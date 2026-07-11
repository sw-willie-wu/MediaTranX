"""Pipeline recipe service — thin CRUD over PipelineRecipeDAO.

Route → (DI) Service → DAO layering, mirroring AgentSessionService:
the service owns its DAO internally; routes get the service via AppContainer.
"""
import logging

from app.db.dao.pipeline_recipe_dao import PipelineRecipeDAO
from app.db.models.pipeline_recipe import PipelineRecipe

logger = logging.getLogger(__name__)


class PipelineRecipeService:
    def __init__(self):
        self._dao = PipelineRecipeDAO()
        logger.info("PipelineRecipeService initialized")

    def list_recipes(self) -> list[PipelineRecipe]:
        return self._dao.list_recipes()

    def get(self, recipe_id: str) -> PipelineRecipe | None:
        return self._dao.get(recipe_id)

    def create(self, name: str, graph: str) -> PipelineRecipe:
        return self._dao.create(name=name, graph=graph)

    def update(self, recipe_id: str, *, name: str | None = None, graph: str | None = None) -> PipelineRecipe | None:
        return self._dao.update(recipe_id, name=name, graph=graph)

    def delete(self, recipe_id: str) -> bool:
        return self._dao.delete(recipe_id)
