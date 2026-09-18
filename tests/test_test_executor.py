"""
Tests for TestExecutor
Task 6.1: Test Executor Implementation
Following TDD: Write tests first, then implement.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.swe_agent.agents.verification.test_executor import TestExecutor


class TestTestExecutorInit:
    """Test TestExecutor initialization"""

    def test_init_with_sandbox(self):
        """Test: Initialize with sandbox"""
        sandbox = Mock()
        executor = TestExecutor(sandbox)

        assert executor.sandbox == sandbox

    def test_init_stores_default_timeout(self):
        """Test: Default timeout is set"""
        sandbox = Mock()
        executor = TestExecutor(sandbox)

        assert executor.default_timeout == 300


class TestExecuteTests:
    """Test execute_tests method"""

    def test_execute_tests_success(self):
        """Test: Execute tests successfully"""
        sandbox = Mock()
        sandbox.execute.return_value = {
            "status": "success",
            "stdout": "===== 5 passed in 1.23s =====",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 1.23,
        }

        executor = TestExecutor(sandbox)
        result = executor.execute_tests("pytest", "/workspace")

        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert "5 passed" in result["output"]
        sandbox.execute.assert_called_once_with("pytest", timeout=300)

    def test_execute_tests_with_custom_timeout(self):
        """Test: Execute tests with custom timeout"""
        sandbox = Mock()
        sandbox.execute.return_value = {
            "status": "success",
            "stdout": "Tests passed",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 0.5,
        }

        executor = TestExecutor(sandbox)
        result = executor.execute_tests("npm test", "/workspace", timeout=600)

        sandbox.execute.assert_called_once_with("npm test", timeout=600)

    def test_execute_tests_failure(self):
        """Test: Execute tests with failures"""
        sandbox = Mock()
        sandbox.execute.return_value = {
            "status": "error",
            "stdout": "===== 3 passed, 2 failed in 2.45s =====",
            "stderr": "FAILED test_foo.py::test_bar",
            "exit_code": 1,
            "execution_time": 2.45,
        }

        executor = TestExecutor(sandbox)
        result = executor.execute_tests("pytest", "/workspace")

        assert result["status"] == "error"
        assert result["exit_code"] == 1
        assert "2 failed" in result["output"]

    def test_execute_tests_timeout(self):
        """Test: Execute tests with timeout"""
        sandbox = Mock()
        sandbox.execute.return_value = {
            "status": "timeout",
            "stdout": "Running tests...",
            "stderr": "",
            "exit_code": -1,
            "execution_time": 300.0,
        }

        executor = TestExecutor(sandbox)
        result = executor.execute_tests("pytest", "/workspace")

        assert result["status"] == "timeout"
        assert result["exit_code"] == -1

    def test_execute_tests_combines_stdout_stderr(self):
        """Test: Combines stdout and stderr in output"""
        sandbox = Mock()
        sandbox.execute.return_value = {
            "status": "success",
            "stdout": "Test output",
            "stderr": "Warning: deprecated",
            "exit_code": 0,
            "execution_time": 1.0,
        }

        executor = TestExecutor(sandbox)
        result = executor.execute_tests("pytest", "/workspace")

        assert "Test output" in result["output"]
        assert "Warning: deprecated" in result["output"]


class TestParseTestResults:
    """Test parse_test_results method"""

    def test_parse_pytest_output_all_passed(self):
        """Test: Parse pytest output with all tests passed"""
        output = """
collected 10 items

test_foo.py::test_bar PASSED
test_foo.py::test_baz PASSED
===== 10 passed in 1.23s =====
"""
        executor = TestExecutor(Mock())
        result = executor.parse_test_results(output)

        assert result["framework"] == "pytest"
        assert len(result["passed"]) == 2
        assert "test_foo.py::test_bar" in result["passed"]
        assert "test_foo.py::test_baz" in result["passed"]
        assert len(result["failed"]) == 0

    def test_parse_pytest_output_with_failures(self):
        """Test: Parse pytest output with failures"""
        output = """
collected 5 items

test_foo.py::test_bar PASSED
test_foo.py::test_baz FAILED
test_foo.py::test_qux PASSED
===== 2 passed, 1 failed in 2.45s =====
"""
        executor = TestExecutor(Mock())
        result = executor.parse_test_results(output)

        assert result["framework"] == "pytest"
        assert len(result["passed"]) == 2
        assert len(result["failed"]) == 1
        assert "test_foo.py::test_baz" in result["failed"]

    def test_parse_pytest_output_with_skipped(self):
        """Test: Parse pytest output with skipped tests"""
        output = """
test_foo.py::test_bar PASSED
test_foo.py::test_baz SKIPPED
===== 1 passed, 1 skipped in 0.50s =====
"""
        executor = TestExecutor(Mock())
        result = executor.parse_test_results(output)

        assert len(result["skipped"]) == 1
        assert "test_foo.py::test_baz" in result["skipped"]

    def test_parse_jest_output_all_passed(self):
        """Test: Parse jest output with all tests passed"""
        output = """
PASS  src/__tests__/foo.test.js
  ✓ test bar (5 ms)
  ✓ test baz (3 ms)

Tests: 2 passed, 2 total
"""
        executor = TestExecutor(Mock())
        result = executor.parse_test_results(output)

        assert result["framework"] == "jest"
        # Should capture both the file and individual tests
        assert len(result["passed"]) == 3
        assert "src/__tests__/foo.test.js" in result["passed"]
        assert "test bar" in result["passed"]
        assert "test baz" in result["passed"]

    def test_parse_jest_output_with_failures(self):
        """Test: Parse jest output with failures"""
        output = """
PASS  src/__tests__/foo.test.js
  ✓ test bar (5 ms)
FAIL  src/__tests__/baz.test.js
  ✕ test qux (10 ms)

Tests: 1 failed, 1 passed, 2 total
"""
        executor = TestExecutor(Mock())
        result = executor.parse_test_results(output)

        assert result["framework"] == "jest"
        assert len(result["failed"]) == 2
        assert "src/__tests__/baz.test.js" in result["failed"]
        assert "test qux" in result["failed"]
        assert len(result["passed"]) == 2
        assert "src/__tests__/foo.test.js" in result["passed"]
        assert "test bar" in result["passed"]

    def test_parse_junit_xml_output(self):
        """Test: Parse JUnit XML output"""
        output = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="FooTest" tests="3" failures="1" skipped="0">
    <testcase name="testBar" classname="FooTest" time="0.05"/>
    <testcase name="testBaz" classname="FooTest" time="0.03">
      <failure message="AssertionError">Expected true but was false</failure>
    </testcase>
    <testcase name="testQux" classname="FooTest" time="0.02"/>
  </testsuite>
</testsuites>
"""
        executor = TestExecutor(Mock())
        result = executor.parse_test_results(output)

        assert result["framework"] == "junit"
        assert len(result["passed"]) == 2
        assert len(result["failed"]) == 1

    def test_parse_unknown_format(self):
        """Test: Parse unknown output format"""
        output = "Some random output"
        executor = TestExecutor(Mock())
        result = executor.parse_test_results(output)

        assert result["framework"] == "unknown"
        assert len(result["passed"]) == 0
        assert len(result["failed"]) == 0


class TestExtractTestStats:
    """Test extract_test_stats method"""

    def test_extract_stats_pytest_success(self):
        """Test: Extract stats from pytest success output"""
        output = "===== 10 passed in 1.23s ====="
        executor = TestExecutor(Mock())
        stats = executor.extract_test_stats(output)

        assert stats["passed"] == 10
        assert stats["failed"] == 0
        assert stats["skipped"] == 0
        assert stats["total"] == 10
        assert stats["duration"] == 1.23

    def test_extract_stats_pytest_mixed(self):
        """Test: Extract stats from pytest mixed results"""
        output = "===== 5 passed, 2 failed, 1 skipped in 3.45s ====="
        executor = TestExecutor(Mock())
        stats = executor.extract_test_stats(output)

        assert stats["passed"] == 5
        assert stats["failed"] == 2
        assert stats["skipped"] == 1
        assert stats["total"] == 8
        assert stats["duration"] == 3.45

    def test_extract_stats_jest_success(self):
        """Test: Extract stats from jest success output"""
        output = "Tests: 8 passed, 8 total\nTime: 2.5s"
        executor = TestExecutor(Mock())
        stats = executor.extract_test_stats(output)

        assert stats["passed"] == 8
        assert stats["failed"] == 0
        assert stats["total"] == 8

    def test_extract_stats_jest_mixed(self):
        """Test: Extract stats from jest mixed results"""
        output = "Tests: 2 failed, 1 skipped, 5 passed, 8 total"
        executor = TestExecutor(Mock())
        stats = executor.extract_test_stats(output)

        assert stats["passed"] == 5
        assert stats["failed"] == 2
        assert stats["skipped"] == 1
        assert stats["total"] == 8

    def test_extract_stats_no_match(self):
        """Test: Extract stats from output with no recognizable format"""
        output = "Some random output"
        executor = TestExecutor(Mock())
        stats = executor.extract_test_stats(output)

        assert stats["passed"] == 0
        assert stats["failed"] == 0
        assert stats["skipped"] == 0
        assert stats["total"] == 0
        assert stats["duration"] == 0.0


class TestCompareResults:
    """Test compare_results method"""

    def test_compare_results_all_improved(self):
        """Test: All tests improved from failing to passing"""
        before = {
            "passed": ["test_a.py::test_1"],
            "failed": ["test_b.py::test_2", "test_c.py::test_3"],
            "skipped": [],
        }
        after = {
            "passed": ["test_a.py::test_1", "test_b.py::test_2", "test_c.py::test_3"],
            "failed": [],
            "skipped": [],
        }

        executor = TestExecutor(Mock())
        comparison = executor.compare_results(before, after)

        assert len(comparison["improved"]) == 2
        assert "test_b.py::test_2" in comparison["improved"]
        assert "test_c.py::test_3" in comparison["improved"]
        assert len(comparison["regressed"]) == 0
        assert len(comparison["still_failing"]) == 0
        assert comparison["net_improvement"] == 2

    def test_compare_results_all_regressed(self):
        """Test: All tests regressed from passing to failing"""
        before = {"passed": ["test_a.py::test_1", "test_b.py::test_2"], "failed": [], "skipped": []}
        after = {"passed": [], "failed": ["test_a.py::test_1", "test_b.py::test_2"], "skipped": []}

        executor = TestExecutor(Mock())
        comparison = executor.compare_results(before, after)

        assert len(comparison["improved"]) == 0
        assert len(comparison["regressed"]) == 2
        assert "test_a.py::test_1" in comparison["regressed"]
        assert "test_b.py::test_2" in comparison["regressed"]
        assert comparison["net_improvement"] == -2

    def test_compare_results_mixed_changes(self):
        """Test: Mixed improvements and regressions"""
        before = {
            "passed": ["test_a.py::test_1"],
            "failed": ["test_b.py::test_2", "test_c.py::test_3"],
            "skipped": [],
        }
        after = {
            "passed": ["test_b.py::test_2"],
            "failed": ["test_a.py::test_1", "test_c.py::test_3"],
            "skipped": [],
        }

        executor = TestExecutor(Mock())
        comparison = executor.compare_results(before, after)

        assert len(comparison["improved"]) == 1
        assert "test_b.py::test_2" in comparison["improved"]
        assert len(comparison["regressed"]) == 1
        assert "test_a.py::test_1" in comparison["regressed"]
        assert len(comparison["still_failing"]) == 1
        assert "test_c.py::test_3" in comparison["still_failing"]
        assert comparison["net_improvement"] == 0

    def test_compare_results_still_failing(self):
        """Test: Tests still failing after changes"""
        before = {"passed": [], "failed": ["test_a.py::test_1", "test_b.py::test_2"], "skipped": []}
        after = {"passed": [], "failed": ["test_a.py::test_1", "test_b.py::test_2"], "skipped": []}

        executor = TestExecutor(Mock())
        comparison = executor.compare_results(before, after)

        assert len(comparison["improved"]) == 0
        assert len(comparison["regressed"]) == 0
        assert len(comparison["still_failing"]) == 2
        assert comparison["net_improvement"] == 0

    def test_compare_results_empty_before(self):
        """Test: Compare with empty before results"""
        before = {"passed": [], "failed": [], "skipped": []}
        after = {"passed": ["test_a.py::test_1"], "failed": ["test_b.py::test_2"], "skipped": []}

        executor = TestExecutor(Mock())
        comparison = executor.compare_results(before, after)

        # New tests don't count as improved/regressed
        assert comparison["net_improvement"] == 0

    def test_compare_results_handles_skipped(self):
        """Test: Compare handles skipped tests correctly"""
        before = {
            "passed": ["test_a.py::test_1"],
            "failed": ["test_b.py::test_2"],
            "skipped": ["test_c.py::test_3"],
        }
        after = {
            "passed": ["test_a.py::test_1", "test_c.py::test_3"],
            "failed": ["test_b.py::test_2"],
            "skipped": [],
        }

        executor = TestExecutor(Mock())
        comparison = executor.compare_results(before, after)

        # Skipped -> Passed doesn't count as improvement in our logic
        # Only failed -> passed counts
        assert comparison["net_improvement"] == 0
