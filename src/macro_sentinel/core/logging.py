from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"


def configure_logging(level_name: str = "INFO", log_file: str = "logs/macro.log") -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level=level_name.upper(),
        colorize=True,
        format=CONSOLE_FORMAT,
        backtrace=False,
        diagnose=False,
    )
    logger.add(
        log_file,
        level=level_name.upper(),
        rotation="10 MB",
        retention="10 days",
        encoding="utf-8",
        enqueue=True,
        format=FILE_FORMAT,
        backtrace=False,
        diagnose=False,
    )
