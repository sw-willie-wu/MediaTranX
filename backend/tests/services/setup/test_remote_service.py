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
        # api_key is never present here; redaction adds has_api_key=False + key_hint=None
        assert result == [{"id": 1, "provider": "openai", "has_api_key": False, "key_hint": None}]
        fake_dao.get_all.assert_called_once()

    def test_filtered_by_provider(self, fake_dao):
        fake_dao.get_by_provider.return_value = [_conn_obj(id=2, provider="ollama")]
        result = RemoteService().get_connections(provider="ollama")
        assert result == [{"id": 2, "provider": "ollama", "has_api_key": False, "key_hint": None}]
        fake_dao.get_by_provider.assert_called_once_with("ollama")

    def test_redacts_api_key_and_sets_has_api_key_flag(self, fake_dao, fake_cipher):
        # Security: the plaintext api_key must NEVER appear in the response
        # body — only a boolean telling the UI whether a key is set.
        fake_dao.get_all.return_value = [
            _conn_obj(id=1, provider="openai", endpoint="http://x", api_key="sk-secret"),
            _conn_obj(id=2, provider="ollama", endpoint="http://o", api_key=None),
        ]
        result = RemoteService().get_connections()
        assert "api_key" not in result[0]
        assert "api_key" not in result[1]
        assert result[0]["has_api_key"] is True
        assert result[1]["has_api_key"] is False
        # The secret value must not leak anywhere in the serialized result
        assert "sk-secret" not in str(result)


class TestAddConnection:
    def test_creates_with_fields(self, fake_dao, fake_cipher):
        fake_dao.create.return_value = _conn_obj(id=1, provider="openai", name="prod")
        result = RemoteService().add_connection(
            provider="openai", name="prod", endpoint="https://api.openai.com", api_key="sk-x",
        )
        assert result["id"] == 1
        # encrypt-on-write: DAO receives the encrypted value ("sk-x" reversed = "x-ks")
        fake_dao.create.assert_called_once_with(
            provider="openai", name="prod", endpoint="https://api.openai.com",
            api_key="enc:fake:x-ks", chunk_ctx_budget=None,
        )

    def test_response_redacts_api_key(self, fake_dao, fake_cipher):
        # Security: the add response must not echo the plaintext key back.
        fake_dao.create.return_value = _conn_obj(
            id=1, provider="openai", name="prod", api_key="sk-secret",
        )
        result = RemoteService().add_connection(
            provider="openai", name="prod", endpoint="https://api.openai.com", api_key="sk-secret",
        )
        assert "api_key" not in result
        assert result["has_api_key"] is True
        assert "sk-secret" not in str(result)


class TestUpdateConnection:
    def test_updates_and_returns(self, fake_dao):
        fake_dao.update.return_value = _conn_obj(id=3, name="new")
        result = RemoteService().update_connection(3, name="new")
        assert result["name"] == "new"
        fake_dao.update.assert_called_once_with(3, name="new")

    def test_response_redacts_api_key(self, fake_dao, fake_cipher):
        # Security: a PUT that only changes name/endpoint/enabled must NOT
        # echo the stored plaintext key back in the response.
        fake_dao.update.return_value = _conn_obj(
            id=3, name="new", provider="openai", api_key="sk-stored",
        )
        result = RemoteService().update_connection(3, name="new")
        assert "api_key" not in result
        assert result["has_api_key"] is True
        assert "sk-stored" not in str(result)

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

    @pytest.mark.parametrize("provider,patch_path,class_name,extra_kwargs", [
        ("ollama", "app.adapters.ai.remote.ollama.OllamaProvider", "OllamaProvider", {"chunk_ctx_budget": None}),
        ("openai", "app.adapters.ai.remote.openai.OpenAIProvider", "OpenAIProvider", {}),
        ("gemini", "app.adapters.ai.remote.gemini.GeminiProvider", "GeminiProvider", {}),
    ])
    def test_known_provider_instantiates(self, fake_dao, provider, patch_path, class_name, extra_kwargs):
        with patch(patch_path) as MockProvider:
            instance = MagicMock()
            MockProvider.return_value = instance
            result = RemoteService()._get_provider(provider, "http://x", "key")
        assert result is instance
        MockProvider.assert_called_once_with("http://x", "key", **extra_kwargs)


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

    def test_degrades_when_list_models_raises(self, fake_dao):
        """is_available True but list_models raises RemoteApiError → connected
        stays True, models empty, no exception escapes (contract preserved)."""
        from app.handler.exceptions import RemoteApiError
        fake_provider = MagicMock()
        fake_provider.is_available.return_value = True
        fake_provider.list_models.side_effect = RemoteApiError("connection_failed", "boom")
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider):
            result = RemoteService().test_connection("openai", "http://x", "k")
        assert result["connected"] is True
        assert result["models"] == []


class TestGetProviderForConnection:
    def test_with_conn_id_uses_dao_lookup(self, fake_dao):
        conn = _conn_obj(id=5, provider="openai", endpoint="http://x", api_key="k", chunk_ctx_budget=None)
        fake_dao.get_by_id.return_value = conn
        fake_provider = MagicMock()
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider) as mock_get:
            result = RemoteService().get_provider_for_connection(5, "openai")
        assert result is fake_provider
        mock_get.assert_called_once_with("openai", "http://x", "k", None)

    def test_conn_id_none_uses_first_active(self, fake_dao):
        active = _conn_obj(id=1, provider="ollama", endpoint="http://o", api_key=None, enabled=True)
        fake_dao.get_by_provider.return_value = [active]
        fake_provider = MagicMock()
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider):
            result = RemoteService().get_provider_for_connection(None, "ollama")
        assert result is fake_provider

    def test_no_active_connection_returns_none(self, fake_dao):
        fake_dao.get_by_provider.return_value = []
        result = RemoteService().get_provider_for_connection(None, "ollama")
        assert result is None


class _FakeCipher:
    scheme = "fake"
    def encrypt(self, p):
        return f"enc:fake:{p[::-1]}" if p else p
    def decrypt(self, t):
        if not t: return t
        if not t.startswith("enc:"): return t
        scheme, _, payload = t[4:].partition(":")
        if scheme != "fake":
            from app.adapters.security.secret_cipher import SecretDecryptError
            raise SecretDecryptError("wrong scheme")
        return payload[::-1]


@pytest.fixture
def fake_cipher(monkeypatch):
    c = _FakeCipher()
    monkeypatch.setattr("app.services.setup.remote_service.get_secret_cipher", lambda: c)
    return c


class TestEncryptOnWrite:
    def test_add_encrypts_key_before_dao(self, fake_dao, fake_cipher):
        fake_dao.create.return_value = _conn_obj(id=1, provider="openai", api_key="enc:fake:1-ks")
        RemoteService().add_connection(provider="openai", name="n", endpoint="http://x", api_key="sk-1")
        # DAO received the ENCRYPTED value, not the plaintext
        _, kwargs = fake_dao.create.call_args
        assert kwargs["api_key"] == "enc:fake:1-ks"
        assert kwargs["api_key"] != "sk-1"

    def test_update_encrypts_key_when_present(self, fake_dao, fake_cipher):
        fake_dao.update.return_value = _conn_obj(id=2, name="n", api_key="enc:fake:2-ks")
        RemoteService().update_connection(2, name="n", api_key="sk-2")
        _, kwargs = fake_dao.update.call_args
        assert kwargs["api_key"] == "enc:fake:2-ks"

    def test_update_without_key_does_not_touch_api_key(self, fake_dao, fake_cipher):
        fake_dao.update.return_value = _conn_obj(id=3, name="n")
        RemoteService().update_connection(3, name="n")
        _, kwargs = fake_dao.update.call_args
        assert "api_key" not in kwargs


class TestKeyHint:
    def test_get_connections_returns_masked_hint_no_full_key(self, fake_dao, fake_cipher):
        # stored value is fake-encrypted "sk-LONGKEY" -> reversed
        fake_dao.get_all.return_value = [_conn_obj(id=1, provider="openai", api_key="enc:fake:" + "sk-LONGKEY"[::-1])]
        result = RemoteService().get_connections()
        assert "api_key" not in result[0]
        assert result[0]["has_api_key"] is True
        # head 3 + tail 3, fixed-width mask between (length-hiding)
        assert result[0]["key_hint"] == "sk-•••KEY"
        assert "sk-LONGKEY" not in str(result)

    def test_short_key_is_fully_masked(self, fake_dao, fake_cipher):
        # keys < 8 chars: head+tail would expose most of the secret -> fully masked
        fake_dao.get_all.return_value = [_conn_obj(id=1, provider="openai", api_key="enc:fake:" + "short"[::-1])]
        result = RemoteService().get_connections()
        assert result[0]["key_hint"] == "•••"
        assert "short" not in str(result)

    def test_hint_none_when_no_key(self, fake_dao, fake_cipher):
        fake_dao.get_all.return_value = [_conn_obj(id=1, provider="ollama", api_key=None)]
        r = RemoteService().get_connections()
        assert r[0]["has_api_key"] is False
        assert r[0]["key_hint"] is None

    def test_hint_marks_undecryptable(self, fake_dao, fake_cipher):
        fake_dao.get_all.return_value = [_conn_obj(id=1, provider="openai", api_key="enc:dpapi:xxxx")]
        r = RemoteService().get_connections()
        assert r[0]["has_api_key"] is True
        assert r[0]["key_hint"] == "⚠ undecryptable"


class TestDecryptOnRead:
    def test_get_provider_decrypts_stored_key(self, fake_dao, fake_cipher):
        conn = _conn_obj(id=5, provider="openai", endpoint="http://x",
                         api_key="enc:fake:" + "sk-X"[::-1], chunk_ctx_budget=None)
        fake_dao.get_by_id.return_value = conn
        with patch.object(RemoteService, "_get_provider", return_value=MagicMock()) as mg:
            RemoteService().get_provider_for_connection(5, "openai")
        mg.assert_called_once_with("openai", "http://x", "sk-X", None)   # decrypted, budget forwarded

    def test_get_provider_undecryptable_raises_remote_error(self, fake_dao, fake_cipher):
        from app.handler.exceptions import RemoteApiError
        fake_dao.get_by_id.return_value = _conn_obj(id=6, provider="openai", endpoint="http://x", api_key="enc:dpapi:xxx")
        with pytest.raises(RemoteApiError) as exc_info:
            RemoteService().get_provider_for_connection(6, "openai")
        assert exc_info.value.code == "key_undecryptable"

    def test_reveal_key_returns_plaintext(self, fake_dao, fake_cipher):
        fake_dao.get_by_id.return_value = _conn_obj(id=7, api_key="enc:fake:" + "sk-REVEAL"[::-1])
        assert RemoteService().reveal_key(7) == "sk-REVEAL"

    def test_reveal_key_no_key_returns_none(self, fake_dao, fake_cipher):
        fake_dao.get_by_id.return_value = _conn_obj(id=8, provider="ollama", api_key=None)
        assert RemoteService().reveal_key(8) is None

    def test_reveal_key_missing_raises_not_found(self, fake_dao, fake_cipher):
        from app.handler.exceptions import NotFoundError
        fake_dao.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            RemoteService().reveal_key(999)


class TestEnabledFallback:
    def test_conn_id_none_uses_enabled_attr(self, fake_dao):
        active = _conn_obj(id=1, provider="ollama", endpoint="http://o", api_key=None, enabled=True)
        fake_dao.get_by_provider.return_value = [active]
        with patch.object(RemoteService, "_get_provider", return_value=MagicMock()) as mg:
            RemoteService().get_provider_for_connection(None, "ollama")
        mg.assert_called_once()


class TestListRemoteModelsByConn:
    """Security: model listing for a saved connection resolves the api_key
    server-side from conn_id — the key is never accepted from / echoed to the
    client (no more api_key in the request URL → no more plaintext in logs)."""

    def test_resolves_key_server_side_and_lists(self, fake_dao):
        conn = _conn_obj(id=7, provider="openai", endpoint="http://x", api_key="sk-secret")
        fake_dao.get_by_id.return_value = conn
        fake_provider = MagicMock()
        fake_provider.list_models.return_value = [
            MagicMock(id="m1", name="Model One", size=1, parameter_size="8B",
                      quantization="Q4_K_M", capabilities=["text"]),
        ]
        with patch.object(RemoteService, "_get_provider", return_value=fake_provider) as mock_get:
            result = RemoteService().list_remote_models_by_conn(7)
        # key looked up from the stored connection, not passed by the caller
        mock_get.assert_called_once_with("openai", "http://x", "sk-secret")
        fake_dao.get_by_id.assert_called_once_with(7)
        assert result[0]["id"] == "m1"

    def test_unknown_conn_raises_not_found(self, fake_dao):
        from app.handler.exceptions import NotFoundError
        fake_dao.get_by_id.return_value = None
        with pytest.raises(NotFoundError, match="Connection not found"):
            RemoteService().list_remote_models_by_conn(999)


def test_test_connection_uses_test_timeout(monkeypatch):
    from app.adapters.ai.remote.base import TEST_TIMEOUT
    from app.services.setup.remote_service import RemoteService

    seen = {}

    class _Recorder:
        def is_available(self, timeout=None):
            seen["available_timeout"] = timeout
            return True

        def list_models(self, timeout=None):
            seen["list_timeout"] = timeout
            return []

    svc = RemoteService.__new__(RemoteService)  # bypass __init__ (no DAO needed)
    monkeypatch.setattr(svc, "_get_provider", lambda *a, **k: _Recorder())

    svc.test_connection("ollama", "http://x", None)
    assert seen["available_timeout"] == TEST_TIMEOUT
    assert seen["list_timeout"] == TEST_TIMEOUT
