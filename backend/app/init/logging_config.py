"""
Logging configuration.
"""
import logging
from pathlib import Path

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'


def configure_logging(settings) -> None:
    """Configure logging system based on settings."""
    log_formatter = logging.Formatter(LOG_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if settings.is_frozen:
        error_log = str(settings.path.data / 'logs' / 'core_error.log')
        Path(error_log).parent.mkdir(parents=True, exist_ok=True)

        error_handler = logging.FileHandler(error_log, encoding='utf-8')
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(log_formatter)
        handlers.append(error_handler)

    for h in handlers:
        h.setFormatter(log_formatter)

    logging.basicConfig(level=logging.INFO, handlers=handlers)

    # Unify uvicorn logger format
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    if settings.is_frozen:
        logging.info(f"Backend started in frozen mode. Error log: {error_log}")
