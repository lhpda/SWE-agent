"""Retry and rollback strategy for pipeline execution.

This module implements retry logic, rollback triggers, loop detection,
and circuit breaker mechanisms for the SWE Agent pipeline.

Retry limits per stage (from SYSTEM_DESIGN.md Section 2.2):
- LOCALIZING: 2 retries
- REPRODUCING: 1 retry
- PATCHING: 3 retries
- VALIDATING: 1 retry

Rollback conditions:
- VALIDATING fails with regression → rollback to PATCHING

Loop detection:
- Sliding window of 5 states
- If same state appears 3+ times in window → loop detected

Circuit breaker:
- 5+ consecutive failures → trigger circuit breaker
"""

from collections import Counter
from typing import Any, Dict, List, Optional

from swe_agent.logging import get_logger

logger = get_logger(__name__)

# Default retry limits per stage (from fault tolerance matrix)
DEFAULT_RETRY_LIMITS = {
    "LOCALIZING": 2,
    "REPRODUCING": 1,
    "PATCHING": 3,
    "VALIDATING": 1,
}

# Loop detection parameters
DEFAULT_WINDOW_SIZE = 5
DEFAULT_LOOP_THRESHOLD = 3

# Circuit breaker threshold
DEFAULT_CIRCUIT_THRESHOLD = 5


class RetryStrategy:
    """Manages retry, rollback, loop detection, and circuit breaker logic.

    Example:
        >>> strategy = RetryStrategy()
        >>> if strategy.should_retry("LOCALIZING", attempt=1):
        ...     # Retry localization
        ...     pass
        >>> if strategy.should_rollback("VALIDATING", result):
        ...     # Rollback to PATCHING
        ...     pass
    """

    def __init__(
        self,
        retry_limits: Optional[Dict[str, int]] = None,
        window_size: int = DEFAULT_WINDOW_SIZE,
        loop_threshold: int = DEFAULT_LOOP_THRESHOLD,
        circuit_threshold: int = DEFAULT_CIRCUIT_THRESHOLD,
    ):
        """Initialize retry strategy.

        Args:
            retry_limits: Custom retry limits per stage (overrides defaults)
            window_size: Size of sliding window for loop detection
            loop_threshold: Number of repetitions to trigger loop detection
            circuit_threshold: Number of consecutive failures to trigger circuit breaker
        """
        self.retry_limits = {**DEFAULT_RETRY_LIMITS}
        if retry_limits:
            self.retry_limits.update(retry_limits)

        self.window_size = window_size
        self.loop_threshold = loop_threshold
        self.circuit_threshold = circuit_threshold

        logger.debug(
            "retry_strategy_initialized",
            retry_limits=self.retry_limits,
            window_size=window_size,
            loop_threshold=loop_threshold,
            circuit_threshold=circuit_threshold,
        )

    def get_max_retries(self, stage: str) -> int:
        """Get maximum retry count for a stage.

        Args:
            stage: Stage name (LOCALIZING, REPRODUCING, PATCHING, VALIDATING)

        Returns:
            Maximum number of retries allowed for this stage (0 if unknown)
        """
        return self.retry_limits.get(stage, 0)

    def should_retry(self, stage: str, attempt: int) -> bool:
        """Check if stage should be retried.

        Args:
            stage: Stage name
            attempt: Current attempt number (0-indexed, so 0 = first try)

        Returns:
            True if should retry, False if at or over limit
        """
        max_retries = self.get_max_retries(stage)
        should_retry = attempt < max_retries

        logger.debug(
            "retry_check",
            stage=stage,
            attempt=attempt,
            max_retries=max_retries,
            should_retry=should_retry,
        )

        return should_retry

    def should_rollback(self, stage: str, result: Dict[str, Any]) -> bool:
        """Check if stage result should trigger rollback.

        Rollback conditions:
        - Stage is VALIDATING
        - Result indicates failure (success=False)
        - Result has regression (has_regression=True)

        Args:
            stage: Stage name
            result: Stage result dictionary

        Returns:
            True if should rollback to previous stage, False otherwise
        """
        # Only VALIDATING stage can trigger rollback
        if stage != "VALIDATING":
            return False

        # Must have failed
        if result.get("success", True):
            return False

        # Must have regression
        has_regression = result.get("has_regression", False)

        if has_regression:
            logger.info(
                "rollback_triggered",
                stage=stage,
                reason="validation_regression",
            )

        return has_regression

    def detect_loop(self, history: List[Dict[str, Any]]) -> bool:
        """Detect infinite loops using sliding window approach.

        Checks if any state appears 3+ times in the last 5 history entries.

        Args:
            history: List of state history entries, each with a "state" field

        Returns:
            True if loop detected, False otherwise
        """
        if not history:
            return False

        # Get last N entries (sliding window)
        window = history[-self.window_size :]

        # Extract state names
        states = [entry.get("state") for entry in window if "state" in entry]

        if not states:
            return False

        # Count occurrences of each state
        state_counts = Counter(states)

        # Check if any state appears >= threshold times
        max_count = max(state_counts.values())
        loop_detected = max_count >= self.loop_threshold

        if loop_detected:
            # Find which state(s) caused the loop
            looping_states = [
                state
                for state, count in state_counts.items()
                if count >= self.loop_threshold
            ]
            logger.warning(
                "loop_detected",
                window_size=len(window),
                looping_states=looping_states,
                max_count=max_count,
            )

        return loop_detected

    def should_circuit_break(self, failures: List[Dict[str, Any]]) -> bool:
        """Check if circuit breaker should trigger.

        Circuit breaker triggers when consecutive failures >= threshold.

        Args:
            failures: List of consecutive failure records

        Returns:
            True if circuit breaker should trigger, False otherwise
        """
        failure_count = len(failures)
        should_break = failure_count >= self.circuit_threshold

        if should_break:
            logger.error(
                "circuit_breaker_triggered",
                failure_count=failure_count,
                threshold=self.circuit_threshold,
            )

        return should_break
