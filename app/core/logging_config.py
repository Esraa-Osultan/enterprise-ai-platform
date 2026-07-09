"""
One place to configure logging so every module just does:

    import logging
    logger = logging.getLogger(__name__)

and gets consistent formatting, both to console and to a file.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()

    os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    # Avoid duplicate handlers if setup_logging() is called more than once
    # (this happens in tests when the app is re-imported).
    if root_logger.handlers:
        return

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        settings.log_file, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Quiet down noisy third-party loggers a bit.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
