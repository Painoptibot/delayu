"""Общие утилиты CLI-скриптов PY-01…PY-07 (логирование, коды выхода)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_RUNTIME = 2
EXIT_CONFIG = 3


def setup_py_logger(name: str, log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger
