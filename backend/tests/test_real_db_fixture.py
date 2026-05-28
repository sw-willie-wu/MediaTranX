def test_real_db_roundtrips_a_connection(real_db):
    from app.db.dao.api_connection_dao import ApiConnectionDAO
    dao = ApiConnectionDAO()
    created = dao.create(provider="openai", name="t", endpoint="http://x", api_key="raw")
    got = dao.get_by_id(created.id)
    assert got is not None and got.api_key == "raw"   # DAO stores verbatim
