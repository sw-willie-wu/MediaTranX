"""
日誌配置
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
設定 logging 格式、handler、以及 frozen 模式下的 error log 檔案。
"""
import logging
import os
from pathlib import Path


LOG_FORMAT = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'


def configure_logging(is_frozen: bool) -> None:
    """配置日誌系統（app + uvicorn 統一格式）"""
    log_formatter = logging.Formatter(LOG_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler()]  # stdout → Electron pipe

    if is_frozen:
        error_log = os.environ.get('MEDIATRANX_ERROR_LOG')
        if not error_log:
            from app.engine.paths import get_base_data_dir
            error_log = str(get_base_data_dir() / 'logs' / 'core_error.log')
        Path(error_log).parent.mkdir(parents=True, exist_ok=True)

        error_handler = logging.FileHandler(error_log, encoding='utf-8')
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(log_formatter)
        handlers.append(error_handler)

    for h in handlers:
        h.setFormatter(log_formatter)

    logging.basicConfig(level=logging.INFO, handlers=handlers)

    # 統一 uvicorn logger 格式（覆蓋 uvicorn 預設的 formatter）
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True  # 讓 uvicorn 的 log 走 root logger

    if is_frozen:
        logging.info(f"Backend started in frozen mode. Error log: {error_log}")
