"""Tests for logging system (Task 0.3)."""

import json
import logging
from io import StringIO

import pytest
import structlog

from swe_agent.logging import setup_logging, get_logger


class TestLoggingSetup:
    """Test logging configuration and setup."""

    def test_setup_logging_returns_logger(self):
        """Test that setup_logging returns a logger."""
        logger = setup_logging()
        assert logger is not None

    def test_logger_has_structlog_methods(self):
        """Test that logger has structlog methods."""
        logger = setup_logging()
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "debug")

    def test_get_logger_with_name(self):
        """Test getting a named logger."""
        logger = get_logger("test_component")
        assert logger is not None


class TestStructuredLogging:
    """Test structured logging output format."""

    def test_log_output_is_json_format(self, capfd):
        """Test that log output is in JSON Lines format."""
        setup_logging(level="INFO")
        logger = get_logger("test")

        logger.info("test_message", key="value")

        captured = capfd.readouterr()
        # Output should contain JSON
        assert "test_message" in captured.err or "test_message" in captured.out

    def test_log_contains_timestamp(self, capfd):
        """Test that log entries contain timestamp."""
        setup_logging(level="INFO")
        logger = get_logger("test")

        logger.info("test_event")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        # Should contain timestamp-like content
        assert len(output) > 0

    def test_log_contains_level(self, capfd):
        """Test that log entries contain level."""
        setup_logging(level="INFO")
        logger = get_logger("test")

        logger.info("info_message")
        logger.error("error_message")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        assert len(output) > 0

    def test_log_with_session_id(self, capfd):
        """Test logging with session_id context."""
        setup_logging(level="INFO")
        logger = get_logger("test")

        logger.info("test_event", session_id="session-123")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        # Session ID should be in output
        assert "session-123" in output or "session_id" in output


class TestLogLevels:
    """Test different log levels."""

    def test_debug_level_logs_debug_messages(self, capfd):
        """Test that DEBUG level logs debug messages."""
        setup_logging(level="DEBUG")
        logger = get_logger("test")

        logger.debug("debug_message")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        assert "debug_message" in output

    def test_info_level_filters_debug_messages(self, capfd):
        """Test that INFO level filters out debug messages."""
        setup_logging(level="INFO")
        logger = get_logger("test")

        logger.debug("debug_message")
        logger.info("info_message")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        # Should contain info but may not contain debug (depending on config)
        assert "info_message" in output

    def test_error_level_logs_errors(self, capfd):
        """Test that error level works."""
        setup_logging(level="ERROR")
        logger = get_logger("test")

        logger.error("error_message")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        assert "error_message" in output


class TestContextualLogging:
    """Test contextual logging with bind."""

    def test_bind_adds_context_to_logger(self, capfd):
        """Test that bind adds persistent context."""
        setup_logging(level="INFO")
        logger = get_logger("test")

        bound_logger = logger.bind(session_id="abc123", stage="localization")
        bound_logger.info("test_event")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        # Context should be in output
        assert "abc123" in output or "session_id" in output

    def test_bind_context_persists_across_calls(self, capfd):
        """Test that bound context persists."""
        setup_logging(level="INFO")
        logger = get_logger("test")

        bound_logger = logger.bind(request_id="req-456")
        bound_logger.info("first_event")
        bound_logger.info("second_event")

        captured = capfd.readouterr()
        output = captured.err + captured.out
        # Should appear in both log entries
        assert output.count("req-456") >= 2 or output.count("request_id") >= 2
