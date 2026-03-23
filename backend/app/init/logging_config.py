"""
日誌配置
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
設定 logging 格式、handler、以及 frozen 模式下的 error log 檔案。
"""
import logging
import os
from pathlib import Path


def configure_logging(is_frozen: bool) -> None:
    """配置日誌系統"""
    log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    handlers: list[logging.Handler] = [logging.StreamHandler()]  # stdout → Electron pipe

    if is_frozen:
        appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
        error_log = os.environ.get('MEDIATRANX_ERROR_LOG')
        if not error_log:
            error_log = str(Path(appdata) / 'MediaTranX' / 'logs' / 'core_error.log')
        Path(error_log).parent.mkdir(parents=True, exist_ok=True)

        error_handler = logging.FileHandler(error_log, encoding='utf-8')
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(log_formatter)
        handlers.append(error_handler)

    for h in handlers:
        h.setFormatter(log_formatter)

    logging.basicConfig(level=logging.INFO, handlers=handlers)

    if is_frozen:
        logging.info(f"Backend started in frozen mode. Error log: {error_log}")
