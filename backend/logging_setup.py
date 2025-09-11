import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging() -> logging.Logger:
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / os.getenv("LOG_FILE", "app.log")
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger("hos")
    if logger.handlers:
        return logger
    logger.setLevel(level)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logger.addHandler(ch)

    # Rotating file handler
    fh = RotatingFileHandler(str(log_path), maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logger.addHandler(fh)

    logger.info(json.dumps({"event": "logging_initialized", "path": str(log_path), "level": level_name}))
    return logger


