"""Pipeline recipe DAO — CRUD over saved pipeline graphs."""
import logging

from sqlmodel import Session, select

from app.db.database import get_engine
from app.db.models.pipeline_recipe import PipelineRecipe, _now_iso

logger = logging.getLogger(__name__)


class PipelineRecipeDAO:
    """Saved pipeline recipes data access."""

    def list_recipes(self) -> list[PipelineRecipe]:
        """All recipes, newest updated first."""
        with Session(get_engine()) as session:
            stmt = select(PipelineRecipe).order_by(PipelineRecipe.updated_at.desc())
            return list(session.exec(stmt).all())

    def get(self, recipe_id: str) -> PipelineRecipe | None:
        with Session(get_engine()) as session:
            return session.get(PipelineRecipe, recipe_id)

    def create(self, name: str, graph: str) -> PipelineRecipe:
        rec = PipelineRecipe(name=name, graph=graph)
        with Session(get_engine()) as session:
            session.add(rec)
            session.commit()
            session.refresh(rec)
        logger.info(f"Pipeline recipe created: {rec.id} ({name!r})")
        return rec

    def update(self, recipe_id: str, *, name: str | None = None, graph: str | None = None) -> PipelineRecipe | None:
        with Session(get_engine()) as session:
            rec = session.get(PipelineRecipe, recipe_id)
            if rec is None:
                return None
            if name is not None:
                rec.name = name
            if graph is not None:
                rec.graph = graph
            rec.updated_at = _now_iso()
            session.add(rec)
            session.commit()
            session.refresh(rec)
        return rec

    def delete(self, recipe_id: str) -> bool:
        with Session(get_engine()) as session:
            rec = session.get(PipelineRecipe, recipe_id)
            if rec is None:
                return False
            session.delete(rec)
            session.commit()
        logger.info(f"Pipeline recipe deleted: {recipe_id}")
        return True
