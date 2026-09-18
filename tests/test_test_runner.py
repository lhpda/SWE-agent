"""
Unit tests for TestRunner.

Task 6.2: Test Suite Runner
Tests verify test suite execution, result parsing, output truncation, and timeout handling.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.swe_agent.agents.validation.test_runner import TestRunner


class TestTestRunnerBasics:
    """Test basic TestRunner functionality."""

    def test_initialization(self):
        """Test TestRunner initialization."""
        sandbox = Mock()
        runner = TestRunner(sandbox)

        assert runner.sandbox == sandbox
        assert runner.default_timeout == 600
        assert runner.max_output_size == 10240

    def test_initialization_custom_timeout(self):
        """Test TestRunner with custom timeout."""
        sandbox = Mock()
        runner = TestRunner(sandbox, default_timeout=300)

        assert runner.default_timeout == 300


class TestRunTestSuite:
    """Test run_test_suite method."""

    def test_run_pytest_suite_success(self):
        """Test running pytest suite successfully."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "success",
                "stdout": "test_example.py::test_one PASSED\ntest_example.py::test_two PASSED\n===== 2 passed in 1.23s =====",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 1.23,
            }
        )

        runner = TestRunner(sandbox)
        result = runner.run_test_suite("pytest tests/", "/path/to/project")

        assert result["passed"] == 2
        assert result["failed"] == 0
        assert result["skipped"] == 0
        assert result["total"] == 2
        assert result["duration"] == 1.23
        assert result["timed_out"] is False
        assert result["exit_code"] == 0
        assert "2 passed" in result["output"]

    def test_run_pytest_suite_with_failures(self):
        """Test running pytest suite with failures."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "success",
                "stdout": "test_example.py::test_one PASSED\ntest_example.py::test_two FAILED\n===== 1 passed, 1 failed in 2.34s =====",
                "stderr": "",
                "exit_code": 1,
                "execution_time": 2.34,
            }
        )

        runner = TestRunner(sandbox)
        result = runner.run_test_suite("pytest tests/", "/path/to/project")

        assert result["passed"] == 1
        assert result["failed"] == 1
        assert result["total"] == 2
        assert result["exit_code"] == 1

    def test_run_jest_suite_success(self):
        """Test running jest suite successfully."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "success",
                "stdout": "PASS tests/example.test.js\n✓ test one (10 ms)\n✓ test two (15 ms)\nTests: 2 passed, 2 total\nTime: 1.5s",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 1.5,
            }
        )

        runner = TestRunner(sandbox)
        result = runner.run_test_suite("npm test", "/path/to/project")

        assert result["passed"] == 2
        assert result["failed"] == 0
        assert result["total"] == 2
        assert result["exit_code"] == 0

    def test_run_suite_with_timeout(self):
        """Test running suite with timeout."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "timeout",
                "stdout": "test_example.py::test_one PASSED\ntest_example.py::test_slow",
                "stderr": "Timeout exceeded",
                "exit_code": -1,
                "execution_time": 600,
            }
        )

        runner = TestRunner(sandbox)
        result = runner.run_test_suite("pytest tests/", "/path/to/project", timeout=600)

        assert result["timed_out"] is True
        assert result["exit_code"] == -1
        assert "Timeout exceeded" in result["output"]

    def test_run_suite_custom_timeout(self):
        """Test running suite with custom timeout."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "success",
                "stdout": "===== 5 passed in 10.0s =====",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 10.0,
            }
        )

        runner = TestRunner(sandbox)
        result = runner.run_test_suite("pytest tests/", "/path/to/project", timeout=300)

        # Verify sandbox was called with correct timeout
        sandbox.execute.assert_called_once_with("pytest tests/", timeout=300)
        assert result["passed"] == 5

    def test_run_suite_with_stderr(self):
        """Test running suite with stderr output."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "success",
                "stdout": "===== 3 passed in 1.0s =====",
                "stderr": "Warning: deprecated feature used",
                "exit_code": 0,
                "execution_time": 1.0,
            }
        )

        runner = TestRunner(sandbox)
        result = runner.run_test_suite("pytest tests/", "/path/to/project")

        assert "Warning: deprecated feature used" in result["output"]
        assert result["passed"] == 3


class TestParseResults:
    """Test parse_results method."""

    def test_parse_pytest_results(self):
        """Test parsing pytest results."""
        output = """
test_example.py::test_one PASSED
test_example.py::test_two FAILED
test_example.py::test_three SKIPPED
===== 1 passed, 1 failed, 1 skipped in 2.45s =====
"""
        runner = TestRunner(Mock())
        stats = runner.parse_results(output)

        assert stats["passed"] == 1
        assert stats["failed"] == 1
        assert stats["skipped"] == 1
        assert stats["total"] == 3
        assert stats["duration"] == 2.45

    def test_parse_jest_results(self):
        """Test parsing jest results."""
        output = """
PASS tests/example.test.js
✓ test one (10 ms)
✓ test two (15 ms)
FAIL tests/broken.test.js
✕ test three (5 ms)
Tests: 1 failed, 2 passed, 3 total
Time: 3.5s
"""
        runner = TestRunner(Mock())
        stats = runner.parse_results(output)

        assert stats["passed"] == 2
        assert stats["failed"] == 1
        assert stats["total"] == 3
        assert stats["duration"] == 3.5

    def test_parse_results_no_match(self):
        """Test parsing results with no recognizable format."""
        output = "Some random output"
        runner = TestRunner(Mock())
        stats = runner.parse_results(output)

        assert stats["passed"] == 0
        assert stats["failed"] == 0
        assert stats["skipped"] == 0
        assert stats["total"] == 0
        assert stats["duration"] == 0.0

    def test_parse_pytest_only_passed(self):
        """Test parsing pytest with only passed tests."""
        output = "===== 5 passed in 1.5s ====="
        runner = TestRunner(Mock())
        stats = runner.parse_results(output)

        assert stats["passed"] == 5
        assert stats["failed"] == 0
        assert stats["skipped"] == 0
        assert stats["total"] == 5

    def test_parse_pytest_only_failed(self):
        """Test parsing pytest with only failed tests."""
        output = "===== 3 failed in 2.0s ====="
        runner = TestRunner(Mock())
        stats = runner.parse_results(output)

        assert stats["passed"] == 0
        assert stats["failed"] == 3
        assert stats["total"] == 3


class TestTruncateOutput:
    """Test truncate_output method."""

    def test_truncate_short_output(self):
        """Test truncate with output shorter than max size."""
        runner = TestRunner(Mock())
        output = "Short output"
        result = runner.truncate_output(output, max_size=1024)

        assert result == output
        assert len(result) <= 1024

    def test_truncate_long_output(self):
        """Test truncate with output longer than max size."""
        runner = TestRunner(Mock())
        output = "x" * 20000
        result = runner.truncate_output(output, max_size=10240)

        assert len(result) == 10240
        assert result.startswith("... (output truncated) ...")
        # Should keep last part of output
        assert result.endswith("x" * 100)

    def test_truncate_default_max_size(self):
        """Test truncate with default max size."""
        runner = TestRunner(Mock())
        output = "y" * 15000
        result = runner.truncate_output(output)

        assert len(result) == 10240  # Default max size
        assert "truncated" in result

    def test_truncate_preserves_tail(self):
        """Test that truncation preserves the tail (last 10KB)."""
        runner = TestRunner(Mock())
        output = "START" + ("x" * 20000) + "END"
        result = runner.truncate_output(output, max_size=10240)

        assert "END" in result
        assert "START" not in result
        assert len(result) == 10240


class TestGetSummary:
    """Test get_summary method."""

    def test_get_summary_after_successful_run(self):
        """Test getting summary after successful test run."""
        sandbox = Mock()
        sandbox.execute = Mock(
            return_value={
                "status": "success",
                "stdout": "===== 5 passed in 2.5s =====",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 2.5,
            }
        )

        runner = TestRunner(sandbox)
        runner.run_test_suite("pytest tests/", "/path")
        summary = runner.get_summary()

        assert summary["passed"] == 5
        assert summary["failed"] == 0
        assert summary["skipped"] == 0
        assert summary["total"] == 5
        assert summary["duration"] == 2.5
        assert summary["timed_out"] is False

    def test_get_summary_before_run(self):
        """Test getting summary before any test run."""
        runner = TestRunner(Mock())
        summary = runner.get_summary()

        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["skipped"] == 0
        assert summary["total"] == 0
        assert summary["duration"] == 0.0
        assert summary["timed_out"] is False

    def test_get_summary_after_multiple_runs(self):
        """Test getting summary after multiple test runs."""
        sandbox = Mock()
        sandbox.execute = Mock(
            side_effect=[
                {
                    "status": "success",
                    "stdout": "===== 3 passed in 1.0s =====",
                    "stderr": "",
                    "exit_code": 0,
                    "execution_time": 1.0,
                },
                {
                    "status": "success",
                    "stdout": "===== 5 passed, 1 failed in 2.0s =====",
                    "stderr": "",
                    "exit_code": 1,
                    "execution_time": 2.0,
                },
            ]
        )

        runner = TestRunner(sandbox)
        runner.run_test_suite("pytest tests/", "/path")
        runner.run_test_suite("pytest tests/", "/path")

        # Should return most recent run
        summary = runner.get_summary()
        assert summary["passed"] == 5
        assert summary["failed"] == 1
        assert summary["total"] == 6
