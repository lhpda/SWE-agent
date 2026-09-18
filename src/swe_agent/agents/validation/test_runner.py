"""
Test Suite Runner for executing and analyzing test suites.

Task 6.2: Test Suite Runner Implementation
Provides functionality to run test suites, parse results, and truncate output.
"""

import re
from typing import Dict, Any, Optional


class TestRunner:
    """
    Run test suites and analyze results.

    Features:
    - Execute complete test suites with configurable timeout
    - Parse test results from pytest and jest
    - Truncate large outputs to manageable size
    - Track test statistics across runs
    """

    def __init__(self, sandbox, default_timeout: int = 600):
        """
        Initialize TestRunner.

        Args:
            sandbox: Sandbox instance for executing tests
            default_timeout: Default timeout in seconds (default: 600 = 10 minutes)
        """
        self.sandbox = sandbox
        self.default_timeout = default_timeout
        self.max_output_size = 10240  # 10KB
        self._last_result = None

    def run_test_suite(
        self, test_command: str, working_dir: str, timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run complete test suite.

        Args:
            test_command: Command to run tests (e.g., "pytest tests/", "npm test")
            working_dir: Working directory for test execution
            timeout: Timeout in seconds (default: self.default_timeout)

        Returns:
            Dict containing:
                - passed: Number of passed tests
                - failed: Number of failed tests
                - skipped: Number of skipped tests
                - total: Total number of tests
                - duration: Execution time in seconds
                - output: Test output (truncated to max_output_size)
                - timed_out: Whether execution timed out
                - exit_code: Process exit code
        """
        if timeout is None:
            timeout = self.default_timeout

        # Execute test command in sandbox
        result = self.sandbox.execute(test_command, timeout=timeout)

        # Combine stdout and stderr
        output = result["stdout"]
        if result["stderr"]:
            output += "\n" + result["stderr"]

        # Parse test statistics
        stats = self.parse_results(output)

        # Truncate output if needed
        truncated_output = self.truncate_output(output, self.max_output_size)

        # Build result dict
        test_result = {
            "passed": stats["passed"],
            "failed": stats["failed"],
            "skipped": stats["skipped"],
            "total": stats["total"],
            "duration": stats["duration"],
            "output": truncated_output,
            "timed_out": result["status"] == "timeout",
            "exit_code": result["exit_code"],
        }

        # Store for get_summary()
        self._last_result = test_result

        return test_result

    def parse_results(self, output: str) -> Dict[str, Any]:
        """
        Parse test output to extract statistics.

        Supports pytest and jest output formats.

        Args:
            output: Raw test output string

        Returns:
            Dict containing:
                - passed: Number of passed tests
                - failed: Number of failed tests
                - skipped: Number of skipped tests
                - total: Total number of tests
                - duration: Execution time in seconds
        """
        stats = {"passed": 0, "failed": 0, "skipped": 0, "total": 0, "duration": 0.0}

        # Try pytest format first
        # Pattern: "=== 5 passed, 2 failed, 1 skipped in 3.45s ==="
        # Match summary line with duration
        duration_match = re.search(r"in\s+([\d.]+)s(?:\s*=+|\s*$)", output, re.MULTILINE)
        if duration_match:
            stats["duration"] = float(duration_match.group(1))

            # Extract individual counts
            passed_match = re.search(r"(\d+)\s+passed", output)
            if passed_match:
                stats["passed"] = int(passed_match.group(1))

            failed_match = re.search(r"(\d+)\s+failed", output)
            if failed_match:
                stats["failed"] = int(failed_match.group(1))

            skipped_match = re.search(r"(\d+)\s+skipped", output)
            if skipped_match:
                stats["skipped"] = int(skipped_match.group(1))

            stats["total"] = stats["passed"] + stats["failed"] + stats["skipped"]
            return stats

        # Try jest format
        # Pattern: "Tests: 1 failed, 2 passed, 3 total"
        jest_match = re.search(
            r"Tests:\s*(?:(\d+)\s+failed,?\s*)?(?:(\d+)\s+skipped,?\s*)?(?:(\d+)\s+passed,?\s*)?(\d+)\s+total",
            output,
        )
        if jest_match:
            failed = jest_match.group(1)
            skipped = jest_match.group(2)
            passed = jest_match.group(3)
            total = jest_match.group(4)

            stats["failed"] = int(failed) if failed else 0
            stats["skipped"] = int(skipped) if skipped else 0
            stats["passed"] = int(passed) if passed else 0
            stats["total"] = int(total) if total else 0

            # Try to find duration
            time_match = re.search(r"Time:\s*([\d.]+)s", output)
            if time_match:
                stats["duration"] = float(time_match.group(1))

            return stats

        return stats

    def truncate_output(self, output: str, max_size: Optional[int] = None) -> str:
        """
        Truncate output to maximum size, keeping the tail.

        When output exceeds max_size, keeps the last max_size bytes
        with a truncation notice prepended.

        Args:
            output: Raw output string
            max_size: Maximum size in bytes (default: self.max_output_size)

        Returns:
            Truncated output string
        """
        if max_size is None:
            max_size = self.max_output_size

        if len(output) <= max_size:
            return output

        # Truncation notice
        truncation_notice = "... (output truncated) ..."
        notice_len = len(truncation_notice)

        # Keep the last (max_size - notice_len) bytes
        tail_size = max_size - notice_len
        tail = output[-tail_size:]

        return truncation_notice + tail

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of the most recent test run.

        Returns:
            Dict containing:
                - passed: Number of passed tests
                - failed: Number of failed tests
                - skipped: Number of skipped tests
                - total: Total number of tests
                - duration: Execution time in seconds
                - timed_out: Whether execution timed out
        """
        if self._last_result is None:
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "duration": 0.0,
                "timed_out": False,
            }

        return {
            "passed": self._last_result["passed"],
            "failed": self._last_result["failed"],
            "skipped": self._last_result["skipped"],
            "total": self._last_result["total"],
            "duration": self._last_result["duration"],
            "timed_out": self._last_result["timed_out"],
        }
