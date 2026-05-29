"""Schema-creation test for the agent persistence tables."""
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine


def test_agent_tables_created():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Importing the models registers them on SQLModel.metadata before create_all.
    import app.db.models.agent_session  # noqa: F401
    import app.db.models.agent_message  # noqa: F401

    SQLModel.metadata.create_all(engine)

    names = sa_inspect(engine).get_table_names()
    assert "agent_sessions" in names
    assert "agent_messages" in names


def test_agent_message_columns():
    from app.db.models.agent_message import AgentMessage

    cols = AgentMessage.model_fields.keys()
    for c in ("id", "session_id", "seq", "role", "content", "tool_calls", "tool_call_id", "created_at"):
        assert c in cols
