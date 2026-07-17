"""
Logging configuration.
"""
import logging
import os
import re
import sys
from pathlib import Path

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

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
    # Packaged core.exe 的 stdout/stderr 是非 tty pipe → CPython 預設 block buffer
    # （4–8KB 才落地），任務期間 app.log 整批延後。改 line buffering，讓 Electron
    # pipe 端逐行收到。非標準 stream（測試 capsys、未知 runtime）無 reconfigure 則跳過。
    for _stream in (sys.stdout, sys.stderr):
        _reconfigure = getattr(_stream, "reconfigure", None)
        if callable(_reconfigure):
            try:
                _reconfigure(line_buffering=True)
            except Exception:
                # best-effort 優化——任何失敗（非標準 wrapper 簽名不吃 kwarg 拋
                # TypeError、stream 不可 reconfigure 拋 ValueError/OSError 等）都靜默降級，
                # 絕不讓它擋住 bootstrap。
                pass

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


def apply_runtime_levels(mode: str) -> None:
    """Set log levels once the run mode is known (after CLI parsing).

    Production: ROOT → WARNING (suppresses uvicorn/third-party INFO noise such as
    the access log), but our own ``app.*`` loggers stay at INFO so startup
    diagnostics (the System Info block), background warmup, and task logs still
    reach the root StreamHandler (stderr, which Electron pipes into app.log).
    They are NOT written to core_error.log, whose FileHandler stays
    WARNING-level. dev: DEBUG everywhere.

    MEDIATRANX_LOG_LEVEL (case-insensitive) overrides both if present and valid—
    dev channel's packaged build injects debug via Electron to improve problem
    report diagnostics.
    """
    override = os.environ.get("MEDIATRANX_LOG_LEVEL", "").strip().upper()
    if override in _VALID_LEVELS:
        level = getattr(logging, override)
        logging.getLogger().setLevel(level)
        logging.getLogger("app").setLevel(level)
        return
    is_dev = mode == "dev"
    logging.getLogger().setLevel(logging.DEBUG if is_dev else logging.WARNING)
    logging.getLogger("app").setLevel(logging.DEBUG if is_dev else logging.INFO)
