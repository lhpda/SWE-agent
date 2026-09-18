"""Error aggregation and reporting for pipeline execution.

This module implements error classification, aggregation, and reporting
to help the orchestrator make informed decisions about retries and failures.

Error categories:
- Recoverable: timeout, network_error, test_flaky, rate_limit, sandbox_busy
- Unrecoverable: invalid_repo, parse_error, auth_failed, disk_full, syntax_error
"""

import time
from typing import Any, Dict, List

from swe_agent.logging import get_logger

logger = get_logger(__name__)

# Recoverable error types (can retry)
RECOVERABLE_ERROR_TYPES = [
    "timeout",
    "network_error",
    "test_flaky",
    "rate_limit",
    "sandbox_busy",
]

# Unrecoverable error types (should abort)
UNRECOVERABLE_ERROR_TYPES = [
    "invalid_repo",
    "parse_error",
    "auth_failed",
    "disk_full",
    "syntax_error",
]


class ErrorHandler:
    """Manages error classification, aggregation, and reporting.

    Example:
        >>> handler = ErrorHandler()
        >>> error = {"type": "timeout", "message": "Operation timed out"}
        >>> handler.add_error(error, {"stage": "LOCALIZING", "attempt": 1})
        >>> report = handler.generate_report()
        >>> print(report["recommendation"])  # "retry"
    """

    def __init__(self):
        """Initialize error handler with empty error list."""
        self.errors: List[Dict[str, Any]] = []
        logger.debug("error_handler_initialized")

    def classify_error(self, error: Dict[str, Any]) -> Dict[str, Any]:
        """Classify error as recoverable or unrecoverable.

        Args:
            error: Error dictionary with "type" and "message" fields

        Returns:
            Classification dict with:
                - category: Error type/category
                - recoverable: True if error can be retried
        """
        error_type = error.get("type", "unknown")

        if error_type in RECOVERABLE_ERROR_TYPES:
            recoverable = True
        elif error_type in UNRECOVERABLE_ERROR_TYPES:
            recoverable = False
        else:
            # Unknown error types default to unrecoverable for safety
            recoverable = False
            logger.warning(
                "unknown_error_type",
                error_type=error_type,
                defaulting_to="unrecoverable",
            )

        classification = {
            "category": error_type,
            "recoverable": recoverable,
        }

        logger.debug(
            "error_classified",
            error_type=error_type,
            recoverable=recoverable,
        )

        return classification

    def is_recoverable(self, error: Dict[str, Any]) -> bool:
        """Check if an error is recoverable.

        Args:
            error: Error dictionary (can be raw or already processed)

        Returns:
            True if error is recoverable, False otherwise
        """
        # If error already has recoverable field, use it
        if "recoverable" in error:
            return error["recoverable"]

        # Otherwise classify it
        classification = self.classify_error(error)
        return classification["recoverable"]

    def add_error(self, error: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Add an error to the aggregator.

        Args:
            error: Error dictionary with "type" and "message"
            context: Context dictionary with stage, attempt, etc.
        """
        # Classify the error
        classification = self.classify_error(error)

        # Build complete error record
        error_record = {
            "type": error.get("type", "unknown"),
            "message": error.get("message", ""),
            "stage": context.get("stage", "unknown"),
            "timestamp": time.time(),
            "context": context,
            "recoverable": classification["recoverable"],
        }

        self.errors.append(error_record)

        logger.info(
            "error_added",
            error_type=error_record["type"],
            stage=error_record["stage"],
            recoverable=error_record["recoverable"],
        )

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get all recorded errors.

        Returns:
            List of error records
        """
        return self.errors

    def clear_errors(self) -> None:
        """Clear all recorded errors."""
        count = len(self.errors)
        self.errors = []
        logger.debug("errors_cleared", count=count)

    def aggregate_errors(self) -> Dict[str, Any]:
        """Aggregate multiple errors into a summary.

        Returns:
            Summary dictionary with:
                - total_count: Total number of errors
                - recoverable_count: Number of recoverable errors
                - unrecoverable_count: Number of unrecoverable errors
                - by_type: Count by error type
                - by_stage: Count by stage
                - summary_text: Human-readable summary
        """
        if not self.errors:
            return {
                "total_count": 0,
                "recoverable_count": 0,
                "unrecoverable_count": 0,
                "by_type": {},
                "by_stage": {},
                "summary_text": "No errors recorded",
            }

        # Count by type
        by_type: Dict[str, int] = {}
        for error in self.errors:
            error_type = error["type"]
            by_type[error_type] = by_type.get(error_type, 0) + 1

        # Count by stage
        by_stage: Dict[str, int] = {}
        for error in self.errors:
            stage = error["stage"]
            by_stage[stage] = by_stage.get(stage, 0) + 1

        # Count recoverable vs unrecoverable
        recoverable_count = sum(1 for e in self.errors if e["recoverable"])
        unrecoverable_count = len(self.errors) - recoverable_count

        # Generate summary text
        summary_parts = []
        summary_parts.append(f"Total errors: {len(self.errors)}")

        if by_type:
            type_summary = ", ".join(f"{t}: {c}" for t, c in by_type.items())
            summary_parts.append(f"By type: {type_summary}")

        if by_stage:
            stage_summary = ", ".join(f"{s}: {c}" for s, c in by_stage.items())
            summary_parts.append(f"By stage: {stage_summary}")

        summary_parts.append(
            f"Recoverable: {recoverable_count}, Unrecoverable: {unrecoverable_count}"
        )

        summary = {
            "total_count": len(self.errors),
            "recoverable_count": recoverable_count,
            "unrecoverable_count": unrecoverable_count,
            "by_type": by_type,
            "by_stage": by_stage,
            "summary_text": "; ".join(summary_parts),
        }

        logger.debug("errors_aggregated", summary=summary)

        return summary

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive error report.

        Returns:
            Report dictionary with:
                - total_errors: Total error count
                - recoverable_count: Number of recoverable errors
                - unrecoverable_count: Number of unrecoverable errors
                - summary: Aggregated summary text
                - errors: List of all error records
                - recommendation: Suggested action (continue/retry/abort)
        """
        aggregation = self.aggregate_errors()

        # Determine recommendation
        if aggregation["total_count"] == 0:
            recommendation = "continue"
        elif aggregation["unrecoverable_count"] > 0:
            recommendation = "abort"
        else:
            # All errors are recoverable
            recommendation = "retry"

        report = {
            "total_errors": aggregation["total_count"],
            "recoverable_count": aggregation["recoverable_count"],
            "unrecoverable_count": aggregation["unrecoverable_count"],
            "summary": aggregation["summary_text"],
            "errors": self.errors.copy(),
            "recommendation": recommendation,
        }

        logger.info(
            "error_report_generated",
            total_errors=report["total_errors"],
            recommendation=recommendation,
        )

        return report
