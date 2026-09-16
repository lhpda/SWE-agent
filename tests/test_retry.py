"""Tests for retry and rollback strategy.

This module tests the RetryStrategy class which handles:
- Retry count limits per stage
- Rollback logic for validation failures
- Loop detection using sliding windows
- Circuit breaker for consecutive failures
"""

import pytest

from swe_agent.orchestrator.retry import RetryStrategy


class TestRetryCountLimits:
    """Test retry count limits for each stage."""

    def test_get_max_retries_localizing(self):
        """LOCALIZING stage allows 2 retries."""
        strategy = RetryStrategy()
        assert strategy.get_max_retries("LOCALIZING") == 2

    def test_get_max_retries_reproducing(self):
        """REPRODUCING stage allows 1 retry."""
        strategy = RetryStrategy()
        assert strategy.get_max_retries("REPRODUCING") == 1

    def test_get_max_retries_patching(self):
        """PATCHING stage allows 3 retries."""
        strategy = RetryStrategy()
        assert strategy.get_max_retries("PATCHING") == 3

    def test_get_max_retries_validating(self):
        """VALIDATING stage allows 1 retry."""
        strategy = RetryStrategy()
        assert strategy.get_max_retries("VALIDATING") == 1

    def test_get_max_retries_unknown_stage(self):
        """Unknown stages default to 0 retries."""
        strategy = RetryStrategy()
        assert strategy.get_max_retries("UNKNOWN") == 0

    def test_should_retry_within_limit(self):
        """Should retry when attempt is within limit."""
        strategy = RetryStrategy()
        # Attempt 0 (first try), 1 (first retry), 2 (second retry)
        assert strategy.should_retry("LOCALIZING", 0) is True
        assert strategy.should_retry("LOCALIZING", 1) is True

    def test_should_retry_at_limit(self):
        """Should not retry when at limit."""
        strategy = RetryStrategy()
        # LOCALIZING allows 2 retries, so attempt 2 is at limit
        assert strategy.should_retry("LOCALIZING", 2) is False

    def test_should_retry_over_limit(self):
        """Should not retry when over limit."""
        strategy = RetryStrategy()
        assert strategy.should_retry("LOCALIZING", 3) is False
        assert strategy.should_retry("LOCALIZING", 10) is False

    def test_should_retry_reproducing_limit(self):
        """REPRODUCING stage allows only 1 retry."""
        strategy = RetryStrategy()
        assert strategy.should_retry("REPRODUCING", 0) is True
        assert strategy.should_retry("REPRODUCING", 1) is False


class TestRollbackLogic:
    """Test rollback trigger conditions."""

    def test_should_rollback_validating_with_regression(self):
        """Should rollback when VALIDATING fails with regression."""
        strategy = RetryStrategy()
        result = {
            "success": False,
            "has_regression": True,
        }
        assert strategy.should_rollback("VALIDATING", result) is True

    def test_should_rollback_validating_without_regression(self):
        """Should not rollback when VALIDATING fails without regression."""
        strategy = RetryStrategy()
        result = {
            "success": False,
            "has_regression": False,
        }
        assert strategy.should_rollback("VALIDATING", result) is False

    def test_should_rollback_validating_success(self):
        """Should not rollback when VALIDATING succeeds."""
        strategy = RetryStrategy()
        result = {
            "success": True,
            "has_regression": False,
        }
        assert strategy.should_rollback("VALIDATING", result) is False

    def test_should_rollback_other_stages(self):
        """Other stages should not trigger rollback."""
        strategy = RetryStrategy()
        result = {
            "success": False,
            "has_regression": True,
        }
        assert strategy.should_rollback("LOCALIZING", result) is False
        assert strategy.should_rollback("REPRODUCING", result) is False
        assert strategy.should_rollback("PATCHING", result) is False

    def test_should_rollback_missing_regression_field(self):
        """Should not rollback if has_regression field is missing."""
        strategy = RetryStrategy()
        result = {
            "success": False,
        }
        assert strategy.should_rollback("VALIDATING", result) is False


class TestLoopDetection:
    """Test infinite loop detection using sliding windows."""

    def test_detect_loop_empty_history(self):
        """Empty history should not detect loop."""
        strategy = RetryStrategy()
        assert strategy.detect_loop([]) is False

    def test_detect_loop_short_history(self):
        """History shorter than window should not detect loop."""
        strategy = RetryStrategy()
        history = [
            {"state": "LOCALIZING"},
            {"state": "REPRODUCING"},
        ]
        assert strategy.detect_loop(history) is False

    def test_detect_loop_no_repetition(self):
        """No repetition should not detect loop."""
        strategy = RetryStrategy()
        history = [
            {"state": "LOCALIZING"},
            {"state": "REPRODUCING"},
            {"state": "PATCHING"},
            {"state": "VALIDATING"},
            {"state": "DONE"},
        ]
        assert strategy.detect_loop(history) is False

    def test_detect_loop_two_repetitions(self):
        """Two repetitions in window should not detect loop."""
        strategy = RetryStrategy()
        history = [
            {"state": "LOCALIZING"},
            {"state": "REPRODUCING"},
            {"state": "PATCHING"},
            {"state": "PATCHING"},  # 2nd occurrence
            {"state": "VALIDATING"},
        ]
        assert strategy.detect_loop(history) is False

    def test_detect_loop_three_repetitions(self):
        """Three repetitions of same state in window should detect loop."""
        strategy = RetryStrategy()
        history = [
            {"state": "PATCHING"},
            {"state": "VALIDATING"},
            {"state": "PATCHING"},  # 2nd occurrence
            {"state": "VALIDATING"},
            {"state": "PATCHING"},  # 3rd occurrence
        ]
        assert strategy.detect_loop(history) is True

    def test_detect_loop_outside_window(self):
        """Repetitions outside window should not count."""
        strategy = RetryStrategy()
        # Window size is 5, so first PATCHING is outside
        history = [
            {"state": "PATCHING"},  # Outside window
            {"state": "LOCALIZING"},
            {"state": "REPRODUCING"},
            {"state": "PATCHING"},  # In window (1st)
            {"state": "VALIDATING"},
            {"state": "PATCHING"},  # In window (2nd)
        ]
        # Only 2 PATCHING in last 5 entries
        assert strategy.detect_loop(history) is False

    def test_detect_loop_exactly_three_in_window(self):
        """Exactly 3 occurrences in window should detect loop."""
        strategy = RetryStrategy()
        history = [
            {"state": "VALIDATING"},
            {"state": "PATCHING"},  # 1st in window
            {"state": "VALIDATING"},
            {"state": "PATCHING"},  # 2nd in window
            {"state": "PATCHING"},  # 3rd in window
        ]
        assert strategy.detect_loop(history) is True

    def test_detect_loop_different_states(self):
        """Different states should not detect loop."""
        strategy = RetryStrategy()
        history = [
            {"state": "LOCALIZING"},
            {"state": "REPRODUCING"},
            {"state": "PATCHING"},
            {"state": "VALIDATING"},
            {"state": "DONE"},
        ]
        assert strategy.detect_loop(history) is False


class TestCircuitBreaker:
    """Test circuit breaker for consecutive failures."""

    def test_should_circuit_break_empty(self):
        """Empty failures should not trigger circuit breaker."""
        strategy = RetryStrategy()
        assert strategy.should_circuit_break([]) is False

    def test_should_circuit_break_single_failure(self):
        """Single failure should not trigger circuit breaker."""
        strategy = RetryStrategy()
        failures = [{"stage": "LOCALIZING", "error": "test"}]
        assert strategy.should_circuit_break(failures) is False

    def test_should_circuit_break_four_failures(self):
        """Four consecutive failures should not trigger circuit breaker."""
        strategy = RetryStrategy()
        failures = [
            {"stage": "LOCALIZING", "error": "test1"},
            {"stage": "LOCALIZING", "error": "test2"},
            {"stage": "LOCALIZING", "error": "test3"},
            {"stage": "LOCALIZING", "error": "test4"},
        ]
        assert strategy.should_circuit_break(failures) is False

    def test_should_circuit_break_five_failures(self):
        """Five consecutive failures should trigger circuit breaker."""
        strategy = RetryStrategy()
        failures = [
            {"stage": "LOCALIZING", "error": "test1"},
            {"stage": "REPRODUCING", "error": "test2"},
            {"stage": "PATCHING", "error": "test3"},
            {"stage": "VALIDATING", "error": "test4"},
            {"stage": "LOCALIZING", "error": "test5"},
        ]
        assert strategy.should_circuit_break(failures) is True

    def test_should_circuit_break_more_than_five(self):
        """More than five consecutive failures should trigger circuit breaker."""
        strategy = RetryStrategy()
        failures = [{"stage": f"STAGE_{i}", "error": f"error{i}"} for i in range(10)]
        assert strategy.should_circuit_break(failures) is True

    def test_should_circuit_break_exactly_five(self):
        """Exactly five consecutive failures should trigger circuit breaker."""
        strategy = RetryStrategy()
        failures = [{"stage": "TEST", "error": f"error{i}"} for i in range(5)]
        assert strategy.should_circuit_break(failures) is True


class TestRetryStrategyIntegration:
    """Integration tests combining multiple features."""

    def test_custom_retry_limits(self):
        """Test custom retry limits override defaults."""
        custom_limits = {
            "LOCALIZING": 5,
            "REPRODUCING": 3,
        }
        strategy = RetryStrategy(retry_limits=custom_limits)
        assert strategy.get_max_retries("LOCALIZING") == 5
        assert strategy.get_max_retries("REPRODUCING") == 3
        # Should still use default for PATCHING
        assert strategy.get_max_retries("PATCHING") == 3

    def test_custom_window_size(self):
        """Test custom window size for loop detection."""
        strategy = RetryStrategy(window_size=3)
        # Need 3 repetitions in window of 3
        history = [
            {"state": "PATCHING"},
            {"state": "PATCHING"},
            {"state": "PATCHING"},
        ]
        assert strategy.detect_loop(history) is True

    def test_custom_circuit_threshold(self):
        """Test custom circuit breaker threshold."""
        strategy = RetryStrategy(circuit_threshold=3)
        failures = [
            {"stage": "TEST1", "error": "e1"},
            {"stage": "TEST2", "error": "e2"},
            {"stage": "TEST3", "error": "e3"},
        ]
        assert strategy.should_circuit_break(failures) is True

    def test_realistic_scenario_success(self):
        """Test realistic successful scenario."""
        strategy = RetryStrategy()

        # First attempt at each stage succeeds
        assert strategy.should_retry("LOCALIZING", 0) is True
        assert strategy.should_retry("REPRODUCING", 0) is True
        assert strategy.should_retry("PATCHING", 0) is True

        # No rollback needed
        result = {"success": True, "has_regression": False}
        assert strategy.should_rollback("VALIDATING", result) is False

    def test_realistic_scenario_with_retry(self):
        """Test realistic scenario with retries."""
        strategy = RetryStrategy()

        # LOCALIZING fails once, retries
        assert strategy.should_retry("LOCALIZING", 0) is True
        assert strategy.should_retry("LOCALIZING", 1) is True

        # PATCHING needs multiple attempts
        assert strategy.should_retry("PATCHING", 0) is True
        assert strategy.should_retry("PATCHING", 1) is True
        assert strategy.should_retry("PATCHING", 2) is True
        assert strategy.should_retry("PATCHING", 3) is False

    def test_realistic_scenario_with_rollback(self):
        """Test realistic scenario with rollback."""
        strategy = RetryStrategy()

        history = [
            {"state": "LOCALIZING"},
            {"state": "REPRODUCING"},
            {"state": "PATCHING"},
            {"state": "VALIDATING"},
        ]

        # Validation fails with regression
        result = {"success": False, "has_regression": True}
        assert strategy.should_rollback("VALIDATING", result) is True

        # Not a loop yet
        assert strategy.detect_loop(history) is False
