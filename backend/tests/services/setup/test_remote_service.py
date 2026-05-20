"""Tests for RemoteService — API connection CRUD + provider dispatch."""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from app.services.setup.remote_service import RemoteService


@pytest.fixture
def fake_dao():
    with patch("app.services.setup.remote_service.ApiConnectionDAO") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance
        yield instance


def _conn_obj(**fields):
    """Build a fake connection with `.model_dump()`."""
    obj = MagicMock()
    obj.model_dump.return_value = fields
    for k, v in fields.items():
        setattr(obj, k, v)
    return obj


class TestGetConnections:
    def test_no_filter_returns_all(self, fake_dao):
        fake_dao.get_all.return_value = [_conn_obj(id=1, provider="openai")]
        result = RemoteService().get_connections()
        assert result == [{"id": 1, "provider": "openai"}]
        fake_dao.get_all.assert_called_once()

    def test_filtered_by_provider(self, fake_dao):
        fake_dao.get_by_provider.return_value = [_conn_obj(id=2, provider="ollama")]
        result = RemoteService().get_connections(provider="ollama")
        assert result == [{"id": 2, "provider": "ollama"}]
        fake_dao.get_by_provider.assert_called_once_with("ollama")


class TestAddConnection:
    def test_creates_with_fields(self, fake_dao):
        fake_dao.create.return_value = _conn_obj(id=1, provider="openai", name="prod")
        result = RemoteService().add_connection(
            provider="openai", name="prod", endpoint="https://api.openai.com", api_key="sk-x",
        )
        assert result["id"] == 1
        fake_dao.create.assert_called_once_with(
            provider="openai", name="prod", endpoint="https://api.openai.com", api_key="sk-x",
        )


class TestUpdateConnection:
    def test_updates_and_returns(self, fake_dao):
        fake_dao.update.return_value = _conn_obj(id=3, name="new")
        result = RemoteService().update_connection(3, name="new")
        assert result["name"] == "new"
        fake_dao.update.assert_called_once_with(3, name="new")

    def test_missing_raises_not_found(self, fake_dao):
        from app.handler.exceptions import NotFoundError
        fake_dao.update.return_value = None
        with pytest.raises(NotFoundError, match="Connection not found"):
            RemoteService().update_connection(999, name="x")


class TestDeleteConnection:
    def test_deletes_existing(self, fake_dao):
        fake_dao.delete.return_value = True
        RemoteService().delete_connection(1)
        fake_dao.delete.assert_called_once_with(1)

    def test_missing_raises_not_found(self, fake_dao):
        from app.handler.exceptions import NotFoundError
        fake_dao.delete.return_value = False
        with pytest.raises(NotFoundError):
            RemoteService().delete_connection(999)


class TestProviderDispatch:
    def test_unknown_provider_raises(self, fake_dao):
        with pytest.raises(ValueError, match="Unknown provider"):
            RemoteService()._get_provider("bogus", "http://x", None)

    @pytest.mark.parametrize("provider,patch_path,class_name", [
        ("ollama", "app.adapters.ai.remote.ollama.OllamaProvider", "OllamaProvider"),
        ("openai", "app.adapters.ai.remote.openai.OpenAIProvider", "OpenAIProvider"),
        ("gemini", "app.adapters.ai.remote.gemini.GeminiProvider", "GeminiProvider"),
    ])
    def test_known_provider_instantiates(self, fake_dao, provider, patch_path, class_name):
        with patch(patch_path) as MockProvider:
            instance = MagicMock()
            MockProvider.return_value = instance
            result = RemoteService()._get_provider(provider, "http://x", "key")
        assert result is instance
        MockProvider.assert_called_once_with("http://x", "key")


class TestTestConnection:
    def test_returns_connected_with_models(self, fake_dao):
        fake_provider = MagicMock()
        fake_provider.is_available.return_value = True
        fake_provider.list_models.return_value = [
            MagicMock(id="m1", name="Model One", size=1, parameter_size="8B",
                      quantization="Q4_K_M", capabilities=["text"]),
        ]
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider):
            result = RemoteService().test_connection("openai", "http://x", "k")
        assert result["connected"] is True
        assert result["models"][0]["id"] == "m1"

    def test_returns_disconnected_no_models(self, fake_dao):
        fake_provider = MagicMock()
        fake_provider.is_available.return_value = False
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider):
            result = RemoteService().test_connection("openai", "http://x", None)
        assert result["connected"] is False
        assert result["models"] == []
        fake_provider.list_models.assert_not_called()


class TestGetProviderForConnection:
    def test_with_conn_id_uses_dao_lookup(self, fake_dao):
        conn = _conn_obj(id=5, provider="openai", endpoint="http://x", api_key="k")
        fake_dao.get_by_id.return_value = conn
        fake_provider = MagicMock()
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider) as mock_get:
            result = RemoteService().get_provider_for_connection(5, "openai")
        assert result is fake_provider
        mock_get.assert_called_once_with("openai", "http://x", "k")

    def test_conn_id_none_uses_first_active(self, fake_dao):
        active = _conn_obj(id=1, provider="ollama", endpoint="http://o", api_key=None, is_active=True)
        fake_dao.get_by_provider.return_value = [active]
        fake_provider = MagicMock()
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider):
            result = RemoteService().get_provider_for_connection(None, "ollama")
        assert result is fake_provider

    def test_no_active_connection_returns_none(self, fake_dao):
        fake_dao.get_by_provider.return_value = []
        result = RemoteService().get_provider_for_connection(None, "ollama")
        assert result is None
