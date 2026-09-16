"""Structured logging configuration for SWE Agent.

This module configures structlog for JSON-formatted structured logging.
Based on SYSTEM_DESIGN.md Section 8.3: Log Strategy.
"""

import logging
import sys
from typing import Any

import structlog


def setup_logging(level: str = "INFO") -> structlog.BoundLogger:
    """Configure and setup structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured structlog logger
    """
    # Convert string level to logging constant
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=log_level,
    )

    # Configure structlog processors
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


def get_logger(name: str = "") -> structlog.BoundLogger:
    """Get a logger instance with optional name.

    Args:
        name: Logger name (component/module identifier)

    Returns:
        Structlog logger instance
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger_name=name)
    return logger
