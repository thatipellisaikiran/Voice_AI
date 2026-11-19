"""Structured application logging."""

import logging
import sys

from app.config import settings


def get_logger(name: str = "voice_assistant") -> logging.Logger:
    """Create or return a configured logger."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        log.addHandler(handler)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log.setLevel(level)
    log.propagate = False
    return log


logger = get_logger()

