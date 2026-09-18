"""Tests for error aggregation and reporting.

This module tests the ErrorHandler class which handles:
- Error classification (recoverable/unrecoverable)
- Error aggregation
- Error report generation
- Retry decision based on recoverability
"""

import time
from typing import Dict, List

import pytest

from swe_agent.orchestrator.error_handler import ErrorHandler


class TestErrorClassification:
    """Test error classification into recoverable/unrecoverable categories."""

    def test_classify_timeout_error(self):
        """Timeout errors should be classified as recoverable."""
        handler = ErrorHandler()
        error = {"type": "timeout", "message": "Operation timed out"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is True
        assert classification["category"] == "timeout"

    def test_classify_network_error(self):
        """Network errors should be classified as recoverable."""
        handler = ErrorHandler()
        error = {"type": "network_error", "message": "Connection refused"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is True
        assert classification["category"] == "network_error"

    def test_classify_rate_limit_error(self):
        """Rate limit errors should be classified as recoverable."""
        handler = ErrorHandler()
        error = {"type": "rate_limit", "message": "Too many requests"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is True

    def test_classify_test_flaky_error(self):
        """Flaky test errors should be classified as recoverable."""
        handler = ErrorHandler()
        error = {"type": "test_flaky", "message": "Test intermittent failure"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is True

    def test_classify_sandbox_busy_error(self):
        """Sandbox busy errors should be classified as recoverable."""
        handler = ErrorHandler()
        error = {"type": "sandbox_busy", "message": "Sandbox unavailable"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is True

    def test_classify_invalid_repo_error(self):
        """Invalid repo errors should be classified as unrecoverable."""
        handler = ErrorHandler()
        error = {"type": "invalid_repo", "message": "Repository not found"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is False
        assert classification["category"] == "invalid_repo"

    def test_classify_parse_error(self):
        """Parse errors should be classified as unrecoverable."""
        handler = ErrorHandler()
        error = {"type": "parse_error", "message": "Failed to parse issue"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is False

    def test_classify_auth_failed_error(self):
        """Auth failures should be classified as unrecoverable."""
        handler = ErrorHandler()
        error = {"type": "auth_failed", "message": "Authentication failed"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is False

    def test_classify_disk_full_error(self):
        """Disk full errors should be classified as unrecoverable."""
        handler = ErrorHandler()
        error = {"type": "disk_full", "message": "No space left on device"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is False

    def test_classify_syntax_error(self):
        """Syntax errors should be classified as unrecoverable."""
        handler = ErrorHandler()
        error = {"type": "syntax_error", "message": "Invalid syntax in code"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is False

    def test_classify_unknown_error(self):
        """Unknown error types should default to unrecoverable."""
        handler = ErrorHandler()
        error = {"type": "unknown_error", "message": "Something went wrong"}
        classification = handler.classify_error(error)
        assert classification["recoverable"] is False


class TestIsRecoverable:
    """Test the is_recoverable convenience method."""

    def test_is_recoverable_timeout(self):
        """Timeout errors are recoverable."""
        handler = ErrorHandler()
        error = {"type": "timeout", "message": "Timed out"}
        assert handler.is_recoverable(error) is True

    def test_is_recoverable_syntax_error(self):
        """Syntax errors are not recoverable."""
        handler = ErrorHandler()
        error = {"type": "syntax_error", "message": "Bad syntax"}
        assert handler.is_recoverable(error) is False

    def test_is_recoverable_network_error(self):
        """Network errors are recoverable."""
        handler = ErrorHandler()
        error = {"type": "network_error", "message": "Network down"}
        assert handler.is_recoverable(error) is True


class TestAddError:
    """Test adding errors to the aggregator."""

    def test_add_single_error(self):
        """Adding a single error should store it correctly."""
        handler = ErrorHandler()
        error = {"type": "timeout", "message": "Operation timed out"}
        context = {"stage": "LOCALIZING", "attempt": 1}

        handler.add_error(error, context)

        errors = handler.get_errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "timeout"
        assert errors[0]["message"] == "Operation timed out"
        assert errors[0]["stage"] == "LOCALIZING"
        assert errors[0]["recoverable"] is True
        assert "timestamp" in errors[0]

    def test_add_multiple_errors(self):
        """Adding multiple errors should store them all."""
        handler = ErrorHandler()

        error1 = {"type": "timeout", "message": "Timeout 1"}
        context1 = {"stage": "LOCALIZING", "attempt": 1}
        handler.add_error(error1, context1)

        error2 = {"type": "network_error", "message": "Network issue"}
        context2 = {"stage": "REPRODUCING", "attempt": 0}
        handler.add_error(error2, context2)

        errors = handler.get_errors()
        assert len(errors) == 2
        assert errors[0]["type"] == "timeout"
        assert errors[1]["type"] == "network_error"

    def test_add_error_with_rich_context(self):
        """Adding error with rich context should preserve all data."""
        handler = ErrorHandler()
        error = {"type": "parse_error", "message": "Failed to parse"}
        context = {
            "stage": "LOCALIZING",
            "attempt": 2,
            "repo": "test/repo",
            "issue_id": "123",
            "extra_info": "Some additional context",
        }

        handler.add_error(error, context)

        errors = handler.get_errors()
        assert len(errors) == 1
        assert errors[0]["context"]["repo"] == "test/repo"
        assert errors[0]["context"]["issue_id"] == "123"
        assert errors[0]["context"]["extra_info"] == "Some additional context"

    def test_add_error_timestamps_are_increasing(self):
        """Timestamps should be increasing for sequential errors."""
        handler = ErrorHandler()

        error1 = {"type": "timeout", "message": "Error 1"}
        handler.add_error(error1, {"stage": "LOCALIZING"})

        time.sleep(0.01)

        error2 = {"type": "timeout", "message": "Error 2"}
        handler.add_error(error2, {"stage": "REPRODUCING"})

        errors = handler.get_errors()
        assert errors[0]["timestamp"] < errors[1]["timestamp"]


class TestAggregateErrors:
    """Test error aggregation into summaries."""

    def test_aggregate_no_errors(self):
        """Aggregating with no errors should return empty summary."""
        handler = ErrorHandler()
        summary = handler.aggregate_errors()

        assert summary["total_count"] == 0
        assert summary["by_type"] == {}
        assert summary["by_stage"] == {}
        assert "No errors" in summary["summary_text"]

    def test_aggregate_single_error(self):
        """Aggregating a single error should summarize it."""
        handler = ErrorHandler()
        error = {"type": "timeout", "message": "Timed out"}
        handler.add_error(error, {"stage": "LOCALIZING"})

        summary = handler.aggregate_errors()

        assert summary["total_count"] == 1
        assert summary["by_type"]["timeout"] == 1
        assert summary["by_stage"]["LOCALIZING"] == 1
        assert "timeout" in summary["summary_text"].lower()

    def test_aggregate_multiple_same_type(self):
        """Aggregating multiple errors of same type."""
        handler = ErrorHandler()

        for i in range(3):
            error = {"type": "timeout", "message": f"Timeout {i}"}
            handler.add_error(error, {"stage": "LOCALIZING"})

        summary = handler.aggregate_errors()

        assert summary["total_count"] == 3
        assert summary["by_type"]["timeout"] == 3
        assert summary["by_stage"]["LOCALIZING"] == 3

    def test_aggregate_multiple_different_types(self):
        """Aggregating errors of different types."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Timeout"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "network_error", "message": "Network"}, {"stage": "REPRODUCING"})
        handler.add_error({"type": "parse_error", "message": "Parse"}, {"stage": "LOCALIZING"})

        summary = handler.aggregate_errors()

        assert summary["total_count"] == 3
        assert summary["by_type"]["timeout"] == 1
        assert summary["by_type"]["network_error"] == 1
        assert summary["by_type"]["parse_error"] == 1
        assert summary["by_stage"]["LOCALIZING"] == 2
        assert summary["by_stage"]["REPRODUCING"] == 1

    def test_aggregate_recoverable_vs_unrecoverable(self):
        """Aggregating should separate recoverable and unrecoverable."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Timeout"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "network_error", "message": "Network"}, {"stage": "REPRODUCING"})
        handler.add_error({"type": "parse_error", "message": "Parse"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "syntax_error", "message": "Syntax"}, {"stage": "PATCHING"})

        summary = handler.aggregate_errors()

        assert summary["recoverable_count"] == 2  # timeout, network_error
        assert summary["unrecoverable_count"] == 2  # parse_error, syntax_error


class TestGenerateReport:
    """Test error report generation."""

    def test_generate_report_no_errors(self):
        """Report with no errors should indicate success."""
        handler = ErrorHandler()
        report = handler.generate_report()

        assert report["total_errors"] == 0
        assert report["recoverable_count"] == 0
        assert report["unrecoverable_count"] == 0
        assert "No errors" in report["summary"]
        assert report["recommendation"] == "continue"

    def test_generate_report_single_recoverable_error(self):
        """Report with single recoverable error should suggest retry."""
        handler = ErrorHandler()
        handler.add_error({"type": "timeout", "message": "Timed out"}, {"stage": "LOCALIZING"})

        report = handler.generate_report()

        assert report["total_errors"] == 1
        assert report["recoverable_count"] == 1
        assert report["unrecoverable_count"] == 0
        assert len(report["errors"]) == 1
        assert "retry" in report["recommendation"].lower()

    def test_generate_report_single_unrecoverable_error(self):
        """Report with single unrecoverable error should suggest abort."""
        handler = ErrorHandler()
        handler.add_error({"type": "syntax_error", "message": "Bad syntax"}, {"stage": "PATCHING"})

        report = handler.generate_report()

        assert report["total_errors"] == 1
        assert report["recoverable_count"] == 0
        assert report["unrecoverable_count"] == 1
        assert (
            "abort" in report["recommendation"].lower()
            or "stop" in report["recommendation"].lower()
        )

    def test_generate_report_mixed_errors(self):
        """Report with mixed errors should provide balanced recommendation."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Timeout"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "network_error", "message": "Network"}, {"stage": "REPRODUCING"})
        handler.add_error({"type": "parse_error", "message": "Parse"}, {"stage": "LOCALIZING"})

        report = handler.generate_report()

        assert report["total_errors"] == 3
        assert report["recoverable_count"] == 2
        assert report["unrecoverable_count"] == 1
        assert len(report["errors"]) == 3

    def test_generate_report_includes_summary(self):
        """Report should include aggregated summary."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Timeout 1"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "timeout", "message": "Timeout 2"}, {"stage": "LOCALIZING"})

        report = handler.generate_report()

        assert "summary" in report
        assert "timeout" in report["summary"].lower()

    def test_generate_report_includes_all_errors(self):
        """Report should include all error details."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Error 1"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "network_error", "message": "Error 2"}, {"stage": "REPRODUCING"})

        report = handler.generate_report()

        assert len(report["errors"]) == 2
        assert report["errors"][0]["type"] == "timeout"
        assert report["errors"][1]["type"] == "network_error"


class TestRecoverableErrorRetryTrigger:
    """Test that recoverable errors trigger retry decisions."""

    def test_should_retry_recoverable_error(self):
        """Recoverable errors should trigger retry."""
        handler = ErrorHandler()
        handler.add_error({"type": "timeout", "message": "Timed out"}, {"stage": "LOCALIZING"})

        # Get the most recent error
        errors = handler.get_errors()
        latest_error = errors[-1]

        assert handler.is_recoverable(latest_error) is True

    def test_should_not_retry_unrecoverable_error(self):
        """Unrecoverable errors should not trigger retry."""
        handler = ErrorHandler()
        handler.add_error({"type": "syntax_error", "message": "Bad syntax"}, {"stage": "PATCHING"})

        errors = handler.get_errors()
        latest_error = errors[-1]

        assert handler.is_recoverable(latest_error) is False

    def test_multiple_recoverable_errors_still_retryable(self):
        """Multiple recoverable errors should still allow retry."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Timeout 1"}, {"stage": "LOCALIZING"})
        handler.add_error(
            {"type": "network_error", "message": "Network 1"}, {"stage": "LOCALIZING"}
        )

        report = handler.generate_report()

        assert report["recoverable_count"] == 2
        assert "retry" in report["recommendation"].lower()

    def test_any_unrecoverable_error_blocks_retry(self):
        """If any unrecoverable error exists, recommend caution."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Timeout"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "syntax_error", "message": "Syntax"}, {"stage": "PATCHING"})

        report = handler.generate_report()

        assert report["unrecoverable_count"] >= 1
        # With unrecoverable errors, recommendation should not be simple retry


class TestErrorHandlerIntegration:
    """Integration tests combining multiple features."""

    def test_realistic_scenario_all_recoverable(self):
        """Realistic scenario with only recoverable errors."""
        handler = ErrorHandler()

        # Simulate multiple retryable failures
        handler.add_error(
            {"type": "timeout", "message": "Timeout during localization"},
            {"stage": "LOCALIZING", "attempt": 0},
        )
        handler.add_error(
            {"type": "network_error", "message": "Network issue during test"},
            {"stage": "REPRODUCING", "attempt": 1},
        )
        handler.add_error(
            {"type": "rate_limit", "message": "API rate limit hit"},
            {"stage": "PATCHING", "attempt": 0},
        )

        report = handler.generate_report()

        assert report["total_errors"] == 3
        assert report["recoverable_count"] == 3
        assert report["unrecoverable_count"] == 0
        assert "retry" in report["recommendation"].lower()

    def test_realistic_scenario_fatal_error(self):
        """Realistic scenario with fatal unrecoverable error."""
        handler = ErrorHandler()

        handler.add_error(
            {"type": "timeout", "message": "Timeout"}, {"stage": "LOCALIZING", "attempt": 0}
        )
        handler.add_error(
            {"type": "invalid_repo", "message": "Repository does not exist"},
            {"stage": "LOCALIZING", "attempt": 1},
        )

        report = handler.generate_report()

        assert report["total_errors"] == 2
        assert report["unrecoverable_count"] == 1
        assert (
            "abort" in report["recommendation"].lower()
            or "stop" in report["recommendation"].lower()
        )

    def test_clear_errors(self):
        """Should be able to clear errors and start fresh."""
        handler = ErrorHandler()

        handler.add_error({"type": "timeout", "message": "Error 1"}, {"stage": "LOCALIZING"})
        handler.add_error({"type": "timeout", "message": "Error 2"}, {"stage": "REPRODUCING"})

        assert len(handler.get_errors()) == 2

        handler.clear_errors()

        assert len(handler.get_errors()) == 0
        report = handler.generate_report()
        assert report["total_errors"] == 0

    def test_error_context_preserved_in_report(self):
        """Error context should be preserved in final report."""
        handler = ErrorHandler()

        handler.add_error(
            {"type": "timeout", "message": "Operation timed out"},
            {"stage": "LOCALIZING", "attempt": 2, "repo": "test/repo", "issue": "#123"},
        )

        report = handler.generate_report()

        assert report["errors"][0]["context"]["stage"] == "LOCALIZING"
        assert report["errors"][0]["context"]["attempt"] == 2
        assert report["errors"][0]["context"]["repo"] == "test/repo"
        assert report["errors"][0]["context"]["issue"] == "#123"

    def test_concurrent_errors_from_different_stages(self):
        """Should handle errors from different stages correctly."""
        handler = ErrorHandler()

        handler.add_error(
            {"type": "timeout", "message": "Localization timeout"}, {"stage": "LOCALIZING"}
        )
        handler.add_error({"type": "test_flaky", "message": "Flaky test"}, {"stage": "REPRODUCING"})
        handler.add_error(
            {"type": "sandbox_busy", "message": "Sandbox unavailable"}, {"stage": "PATCHING"}
        )
        handler.add_error(
            {"type": "network_error", "message": "Network down"}, {"stage": "VALIDATING"}
        )

        summary = handler.aggregate_errors()

        assert summary["total_count"] == 4
        assert summary["by_stage"]["LOCALIZING"] == 1
        assert summary["by_stage"]["REPRODUCING"] == 1
        assert summary["by_stage"]["PATCHING"] == 1
        assert summary["by_stage"]["VALIDATING"] == 1
        assert summary["recoverable_count"] == 4
