"""The container exposes ollama_settings_service and it resolves to the real class."""
from app.init.container import AppContainer
from app.services.setup.ollama_settings_service import OllamaSettingsService


def test_container_provides_ollama_settings_service():
    container = AppContainer()
    svc = container.ollama_settings_service()
    assert isinstance(svc, OllamaSettingsService)


def test_ollama_settings_service_is_singleton():
    container = AppContainer()
    assert container.ollama_settings_service() is container.ollama_settings_service()
