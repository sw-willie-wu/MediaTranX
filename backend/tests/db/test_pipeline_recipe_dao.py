"""PipelineRecipe model + DAO CRUD（uses real_db fixture）。"""
import time

from app.db.dao.pipeline_recipe_dao import PipelineRecipeDAO


def test_create_and_get_roundtrip(real_db):
    dao = PipelineRecipeDAO()
    rec = dao.create(name="影片轉GIF", graph='{"version":1,"nodes":[],"edges":[]}')
    assert rec.id
    got = dao.get(rec.id)
    assert got is not None
    assert got.name == "影片轉GIF"
    assert got.graph == '{"version":1,"nodes":[],"edges":[]}'
    assert got.created_at and got.updated_at


def test_list_orders_by_updated_desc(real_db):
    dao = PipelineRecipeDAO()
    a = dao.create(name="a", graph="{}")
    time.sleep(0.01)
    b = dao.create(name="b", graph="{}")
    ids = [r.id for r in dao.list_recipes()]
    assert ids.index(b.id) < ids.index(a.id)
    time.sleep(0.01)
    dao.update(a.id, name="a2")
    ids = [r.id for r in dao.list_recipes()]
    assert ids.index(a.id) < ids.index(b.id)


def test_update_partial_and_missing(real_db):
    dao = PipelineRecipeDAO()
    rec = dao.create(name="x", graph="{}")
    out = dao.update(rec.id, graph='{"version":1}')
    assert out.name == "x"
    assert out.graph == '{"version":1}'
    assert dao.update("nope", name="y") is None


def test_delete(real_db):
    dao = PipelineRecipeDAO()
    rec = dao.create(name="gone", graph="{}")
    assert dao.delete(rec.id) is True
    assert dao.get(rec.id) is None
    assert dao.delete(rec.id) is False
