"""
Logger fino sobre `loguru`. Envuelto en una clase pequeña (en vez de usar
`loguru.logger` directamente) para poder añadir contexto estructurado
(`get_logger("module.name")`) de forma consistente con backend2.
"""

import sys
from typing import Any

from loguru import logger as _loguru_logger

_configured = False


def _configure_once() -> None:
    global _configured
    if _configured:
        return
    _loguru_logger.remove()
    _loguru_logger.add(sys.stdout, level="INFO", enqueue=True, backtrace=False)
    _configured = True


class _ScopedLogger:
    def __init__(self, name: str):
        self._logger = _loguru_logger.bind(module=name)

    def info(self, message: str, **kwargs: Any) -> None:
        self._logger.bind(**kwargs).info(message)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._logger.bind(**kwargs).warning(message)

    def error(self, message: str, **kwargs: Any) -> None:
        self._logger.bind(**kwargs).error(message)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._logger.bind(**kwargs).debug(message)


def get_logger(name: str) -> _ScopedLogger:
    _configure_once()
    return _ScopedLogger(name)
