"""
Logging configuration for YouTube Audio Downloader.

This module sets up structured logging with both console and file handlers,
supporting different log levels and automatic log rotation.
"""

import logging
import logging.handlers
from pathlib import Path


# Log file location
LOG_DIR = Path.home() / ".config" / "youtube-audio-downloader"
LOG_FILE = LOG_DIR / "app.log"


def setup_logger(name: str = "youtubeaudiodownloader", level: int = logging.INFO) -> logging.Logger:
    """
    Set up and configure the application logger.

    Args:
        name: Logger name (default: "youtubeaudiodownloader")
        level: Logging level (default: logging.INFO)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Create console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # Create file handler for production with rotation
    try:
        # Create log directory if it doesn't exist
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Rotating file handler: max 5MB per file, keep 3 backup files
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        # If we can't create the file handler, just continue with console logging
        logger.warning(f"Could not set up file logging: {e}")

    return logger


def get_logger(name: str = "youtubeaudiodownloader") -> logging.Logger:
    """
    Get or create a logger instance.

    Args:
        name: Logger name (default: "youtubeaudiodownloader")

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
