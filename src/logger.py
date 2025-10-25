"""
logger.py
Simple logger factory:
 - par défaut : handler sur stdout
 - API simple pour ajouter des handlers (file, rotating, json...) ou charger une config dictConfig
 - usage recommandé : from logger import get_logger; log = get_logger(__name__)
"""

from logging import (
    Logger,
    StreamHandler,
    FileHandler,
    Formatter,
    getLogger,
    DEBUG,
    INFO,
    WARNING,
    ERROR,
    CRITICAL,
    Handler,
)
from logging.handlers import RotatingFileHandler
from logging.config import dictConfig
import sys
from typing import Optional, Dict, Any


DEFAULT_LEVEL = INFO
DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _default_stream_handler(level: int = DEFAULT_LEVEL,
                            fmt: str = DEFAULT_FORMAT,
                            datefmt: str = DEFAULT_DATEFMT) -> StreamHandler:
    h = StreamHandler(stream=sys.stdout)
    h.setLevel(level)
    h.setFormatter(Formatter(fmt=fmt, datefmt=datefmt))
    return h


def configure_basic(level: int = DEFAULT_LEVEL,
                    fmt: str = DEFAULT_FORMAT,
                    datefmt: str = DEFAULT_DATEFMT,
                    root_name: str = None) -> None:
    """
    Configure root logger.
    Need to be called only one time at startup
    """
    root = getLogger(root_name) if root_name else getLogger()
    root.setLevel(level)

    # # Élimine handlers existants si on recharge la config
    # for h in list(root.handlers):
    #     root.removeHandler(h)

    root.addHandler(_default_stream_handler(level=level, fmt=fmt, datefmt=datefmt))


def get_logger(name: Optional[str] = None) -> Logger:
    """
    Create a new logger with desired name.
    Add stdout handler if none has been created yet.
    """
    logger = getLogger(name)
    if not logger.handlers:
        logger.addHandler(_default_stream_handler())
        logger.setLevel(DEFAULT_LEVEL)
    return logger


def add_file_handler(logger_name: str,
                     filename: str,
                     level: int = DEFAULT_LEVEL,
                     fmt: str = DEFAULT_FORMAT,
                     datefmt: str = DEFAULT_DATEFMT,
                     mode: str = "a") -> Handler:
    """Adds a FileHandler on specified logger"""
    logger = get_logger(logger_name)
    fh = FileHandler(filename, mode=mode)
    fh.setLevel(level)
    fh.setFormatter(Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(fh)
    return fh


def add_rotating_file_handler(logger_name: str,
                              filename: str,
                              max_bytes: int = 10 * 1024 * 1024,
                              backup_count: int = 5,
                              level: int = DEFAULT_LEVEL,
                              fmt: str = DEFAULT_FORMAT,
                              datefmt: str = DEFAULT_DATEFMT) -> RotatingFileHandler:
    """Adds a RotatingFileHandler on specified logger"""
    logger = get_logger(logger_name)
    rfh = RotatingFileHandler(filename, maxBytes=max_bytes, backupCount=backup_count)
    rfh.setLevel(level)
    rfh.setFormatter(Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(rfh)
    return rfh


# def configure_from_dict(cfg: Dict[str, Any]) -> None:
#     """
#     Configure logging via dictConfig. Utile pour configurations avancées (niveau par module, handlers multiples, formatters).
#     Exemple: voir documentation Python logging.dictConfig.
#     """
#     dictConfig(cfg)
