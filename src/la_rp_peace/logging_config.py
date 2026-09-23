"""Configure structured console logging for the application."""

import structlog
import structlog.stdlib
import structlog.typing

_LEVELS = {
    "notset": 0,
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
    "critical": 50,
}

# structlog dispatches on the method name, which is not always a level name:
# `.exception()` logs at error level and `.warn()` is a legacy alias.
# Unmapped methods must never raise, so callers cannot crash the app by logging.
_METHOD_LEVELS = {
    **_LEVELS,
    "exception": _LEVELS["error"],
    "warn": _LEVELS["warning"],
}


def configure_logging(level: str = "INFO") -> None:
    """Configure structured console logging once.

    Args:
        level: Case-insensitive minimum level: NOTSET, DEBUG, INFO, WARNING,
            ERROR, or CRITICAL. Subsequent calls preserve the configuration.

    Raises:
        ValueError: If the level is unsupported, even when already configured.
    """
    normalized_level = level.lower()
    if normalized_level not in _LEVELS:
        raise ValueError(f"Invalid log level {level!r}; expected one of: {', '.join(_LEVELS).upper()}")

    if structlog.is_configured():
        return

    minimum_level = _LEVELS[normalized_level]

    def _filter_level(
        _logger: object,
        method_name: str,
        event_dict: structlog.typing.EventDict,
    ) -> structlog.typing.EventDict:
        if _METHOD_LEVELS.get(method_name, minimum_level) < minimum_level:
            raise structlog.DropEvent
        return event_dict

    structlog.configure(
        processors=[
            _filter_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a logger with its name bound as context.

    Call configure_logging before obtaining application loggers.

    Args:
        name: Name identifying the module or component emitting events.

    Returns:
        A bound logger with the supplied name in its logger field.
    """
    return structlog.stdlib.get_logger(name).bind(logger=name)
