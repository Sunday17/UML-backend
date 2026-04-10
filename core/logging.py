"""Structured logging configuration for the application."""

import sys
import structlog
from structlog.types import EventDict, Processor
from structlog.typing import WrappedLogger

from core.config import settings


def add_app_context(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Add static application context to all log events."""
    event_dict["project"] = settings.PROJECT_NAME
    event_dict["version"] = settings.VERSION
    return event_dict


def configure_logging():
    """Configure structlog with environment-appropriate settings."""
    log_level = settings.LOG_LEVEL.upper() if hasattr(settings, "LOG_LEVEL") else "INFO"
    log_format = settings.LOG_FORMAT if hasattr(settings, "LOG_FORMAT") else "console"

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_app_context,
    ]

    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


logger = configure_logging()
