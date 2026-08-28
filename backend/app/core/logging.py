"""Structured logging.

Every log line is JSON in production and human-readable in development. A
request_id is bound to the context at the start of each request and appears on
every subsequent line, so one query can be traced end to end through the RAG
pipeline — which is exactly what the report's pipeline walkthrough needs.
"""

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    """Configure stdlib logging and structlog. Call once, at startup."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Uvicorn's own loggers are noisy at INFO; let them through at WARNING.
    for noisy in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for a module."""
    return structlog.stdlib.get_logger(name)  # type: ignore[no-any-return]
