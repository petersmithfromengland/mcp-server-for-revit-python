# -*- coding: utf-8 -*-
"""
Centralised logging configuration for the Revit MCP Server.

Call ``setup_logging()`` once at startup (in main.py) before any other
module-level loggers are used.  Every module then simply does::

    import logging
    logger = logging.getLogger(__name__)

Logs are written to a rotating text file at:
    C:\\Users\\psmith\\AppData\\Roaming\\BVN\\revit-mcp-test\\revit_mcp.log
"""

import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.environ.get("APPDATA", ""), "BVN", "revit-mcp-test")
_LOG_FILE = os.path.join(_LOG_DIR, "revit_mcp.log")

_FORMAT = "%(asctime)s | %(process)d | %(levelname)-8s | %(name)-35s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 5 MB per file, keep 3 rotated backups
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


def setup_logging(level: int = logging.DEBUG) -> str:
    """Configure the root logger with a file handler.

    Returns the path to the log file.
    """
    os.makedirs(_LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Avoid adding duplicate handlers on reload
    if any(
        isinstance(h, RotatingFileHandler)
        and getattr(h, "baseFilename", "") == os.path.abspath(_LOG_FILE)
        for h in root.handlers
    ):
        return _LOG_FILE

    handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    root.addHandler(handler)

    return _LOG_FILE
