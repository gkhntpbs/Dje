import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Configure project-wide logging. Ensures logs are written to both console and
# a rotating file under the repository's logs directory.
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "dje.log"


def setup_logging(level: int = logging.INFO) -> None:
    """Initialize root logger with console and file handlers."""
    root_logger = logging.getLogger()

    # Avoid adding duplicate handlers when setup_logging is called multiple times.
    if root_logger.handlers:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.captureWarnings(True)


__all__ = ["setup_logging", "LOG_DIR", "LOG_FILE"]
