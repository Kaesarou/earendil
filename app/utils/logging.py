import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(
    level: str = 'INFO',
    log_file_path: str = 'data/logs/goblin.log',
) -> None:
    resolved_level = getattr(logging, level.upper(), logging.INFO)

    log_format = '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(formatter)

    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
