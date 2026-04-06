"""
Application configuration service.
Reads from pydantic-settings, writes path overrides to .env file.
"""
import logging
logger = logging.getLogger(__name__)


class ConfigService:
    """Application configuration service."""

    def __init__(self):
        logger.info("ConfigService initialized")

    def get_config(self) -> dict:
        """Get current configuration with effective paths."""
        from app.init.configs import SETTINGS
        return {
            "models_dir": SETTINGS.path.models,
            "temp_dir": SETTINGS.path.temp,
        }

    def update_config(self, models_dir: str = "", temp_dir: str = "") -> dict:
        """Write path overrides to .env file. Requires restart to take effect."""
        from app.init.configs import SETTINGS
        env_path = SETTINGS.path.data / ".env"

        lines: list[str] = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        updates = {}
        if models_dir:
            updates["MEDIATRANX_PATH__MODELS"] = models_dir
        if temp_dir:
            updates["MEDIATRANX_PATH__TEMP"] = temp_dir

        if not updates:
            return {"ok": True, "restart_required": False}

        for env_key, value in updates.items():
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{env_key}="):
                    lines[i] = f"{env_key}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{env_key}={value}")

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True, "restart_required": True}
