"""
Logging configuration.
"""
import logging
import re
from pathlib import Path

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

# Secret query-string params whose VALUE must never be written to a log.
# uvicorn's access log records the full request line (incl. query string), so
# a key in a URL would land in stdout / app.log / core_error.log verbatim.
_SECRET_QS_RE = re.compile(
    r'\b((?:api[_-]?key|token|password|secret|key)=)[^&\s"\']+',
    re.IGNORECASE,
)


class RedactSecretsFilter(logging.Filter):
    """Redact secret query-string VALUES (api_key=... → api_key=***) from log
    records before they are formatted/emitted.

    Defense-in-depth for the remote-API-key leak: the frontend no longer puts
    the key in a URL, but a stale build / third-party client / mistake still
    must not write a plaintext key into the access log. Attached to the
    uvicorn loggers (the access logger carries the request line in record.args)
    so the redaction happens before the record propagates to the root handlers.
    """

    @staticmethod
    def _scrub(value):
        if isinstance(value, str):
            return _SECRET_QS_RE.sub(r'\1***', value)
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._scrub(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: self._scrub(v) for k, v in record.args.items()}
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        return True


def configure_logging(settings) -> None:
    """Configure logging system based on settings."""
    log_formatter = logging.Formatter(LOG_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if settings.is_frozen:
        error_log = str(settings.path.log / 'core_error.log')
        Path(error_log).parent.mkdir(parents=True, exist_ok=True)

        error_handler = logging.FileHandler(error_log, encoding='utf-8')
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(log_formatter)
        handlers.append(error_handler)

    for h in handlers:
        h.setFormatter(log_formatter)

    logging.basicConfig(level=logging.INFO, handlers=handlers)

    # Unify uvicorn logger format + redact secrets from the access log.
    redact_filter = RedactSecretsFilter()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
        # Logger-level filter runs in handle() before propagation, so the
        # redacted record is what reaches the root handlers.
        uv_logger.addFilter(redact_filter)

    if settings.is_frozen:
        logging.info(f"Backend started in frozen mode. Error log: {error_log}")
