import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LOG_DIR, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT


def setup_logging() -> logging.Logger:
    """初始化日志系统，返回配置好的 logger"""
    LOG_DIR.mkdir(exist_ok=True)

    _logger = logging.getLogger("pdf-tools")
    _logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # 避免重复添加 handler（reload 场景）
    if not any(isinstance(h, RotatingFileHandler) for h in _logger.handlers):
        file_handler = RotatingFileHandler(
            LOG_DIR / "app.log",
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        _logger.addHandler(file_handler)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
               for h in _logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        _logger.addHandler(console)

    return _logger
