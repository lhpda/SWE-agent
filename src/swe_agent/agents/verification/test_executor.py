"""
Test Executor for running and analyzing test results.

Task 6.1: Test Executor Implementation
Provides functionality to execute tests in sandbox, parse output, and compare results.
"""

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional


class TestExecutor:
    """
    Execute and analyze tests in sandbox environment.

    Features:
    - Execute tests with configurable timeout
    - Parse multiple test framework outputs (pytest, jest, junit)
    - Extract test statistics
    - Compare test results before/after changes
    """

    def __init__(self, sandbox):
        """
        Initialize TestExecutor.

        Args:
            sandbox: Sandbox instance for executing tests
        """
        self.sandbox = sandbox
        self.default_timeout = 300  # 5 minutes

    def execute_tests(
        self, test_command: str, working_dir: str, timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute tests in sandbox environment.

        Args:
            test_command: Command to run tests (e.g., "pytest", "npm test")
            working_dir: Working directory for test execution
            timeout: Timeout in seconds (default: 300)

        Returns:
            Dict containing:
                - status: "success", "error", or "timeout"
                - output: Combined stdout and stderr
                - exit_code: Process exit code
                - execution_time: Time taken in seconds
        """
        if timeout is None:
            timeout = self.default_timeout

        # Execute command in sandbox
        result = self.sandbox.execute(test_command, timeout=timeout)

        # Combine stdout and stderr
        output = result["stdout"]
        if result["stderr"]:
            output += "\n" + result["stderr"]

        return {
            "status": result["status"],
            "output": output,
            "exit_code": result["exit_code"],
            "execution_time": result["execution_time"],
        }

    def parse_test_results(self, output: str) -> Dict[str, Any]:
        """
        Parse test output to extract individual test results.

        Supports pytest, jest, and junit XML formats.

        Args:
            output: Raw test output string

        Returns:
            Dict containing:
                - framework: Detected framework ("pytest", "jest", "junit", "unknown")
                - passed: List of passed test names
                - failed: List of failed test names
                - skipped: List of skipped test names
        """
        # Try to detect framework and parse accordingly
        if self._is_pytest_output(output):
            return self._parse_pytest_output(output)
        elif self._is_jest_output(output):
            return self._parse_jest_output(output)
        elif self._is_junit_xml(output):
            return self._parse_junit_xml(output)
        else:
            return {"framework": "unknown", "passed": [], "failed": [], "skipped": []}

    def extract_test_stats(self, output: str) -> Dict[str, Any]:
        """
        Extract test statistics from output.

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

        # Try pytest format first - more flexible pattern
        # Pattern captures: "5 passed, 2 failed, 1 skipped in 3.45s"
        pytest_pattern = r"=+\s*(?:(\d+)\s+passed)?(?:,\s*(\d+)\s+failed)?(?:,\s*(\d+)\s+skipped)?.*?in\s+([\d.]+)s"
        pytest_match = re.search(pytest_pattern, output)

        if pytest_match:
            passed = pytest_match.group(1)
            failed = pytest_match.group(2)
            skipped = pytest_match.group(3)
            duration = pytest_match.group(4)

            stats["passed"] = int(passed) if passed else 0
            stats["failed"] = int(failed) if failed else 0
            stats["skipped"] = int(skipped) if skipped else 0
            stats["total"] = stats["passed"] + stats["failed"] + stats["skipped"]
            stats["duration"] = float(duration) if duration else 0.0
            return stats

        # Try jest format
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

    def compare_results(
        self, before: Dict[str, List[str]], after: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Compare test results before and after changes.

        Args:
            before: Test results before changes (with "passed", "failed", "skipped" keys)
            after: Test results after changes (with "passed", "failed", "skipped" keys)

        Returns:
            Dict containing:
                - improved: List of tests that went from failed to passed
                - regressed: List of tests that went from passed to failed
                - still_failing: List of tests that are still failing
                - net_improvement: improved count - regressed count
        """
        before_passed = set(before.get("passed", []))
        before_failed = set(before.get("failed", []))
        after_passed = set(after.get("passed", []))
        after_failed = set(after.get("failed", []))

        # Improved: was failing, now passing
        improved = list(before_failed & after_passed)

        # Regressed: was passing, now failing
        regressed = list(before_passed & after_failed)

        # Still failing: was failing, still failing
        still_failing = list(before_failed & after_failed)

        return {
            "improved": improved,
            "regressed": regressed,
            "still_failing": still_failing,
            "net_improvement": len(improved) - len(regressed),
        }

    # Private helper methods

    def _is_pytest_output(self, output: str) -> bool:
        """Check if output is from pytest."""
        # Check for pytest-specific patterns
        has_pytest_summary = bool(
            re.search(r"=+\s*\d+\s+(passed|failed|skipped).*in\s+[\d.]+s\s*=+", output)
        )
        has_pytest_test_format = bool(
            re.search(r"test_\w+\.py::\w+\s+(PASSED|FAILED|SKIPPED)", output)
        )
        return has_pytest_summary or has_pytest_test_format

    def _is_jest_output(self, output: str) -> bool:
        """Check if output is from jest."""
        return bool(
            re.search(r"Tests:\s*\d+\s+(passed|failed)", output)
            or re.search(r"(PASS|FAIL)\s+\S+\.test\.(js|ts)", output)
        )

    def _is_junit_xml(self, output: str) -> bool:
        """Check if output is JUnit XML format."""
        return output.strip().startswith("<?xml") and "<testsuite" in output

    def _parse_pytest_output(self, output: str) -> Dict[str, Any]:
        """Parse pytest output format."""
        result = {"framework": "pytest", "passed": [], "failed": [], "skipped": []}

        # Match individual test results
        for match in re.finditer(r"(\S+\.py::\S+)\s+(PASSED|FAILED|SKIPPED)", output):
            test_name = match.group(1)
            status = match.group(2)

            if status == "PASSED":
                result["passed"].append(test_name)
            elif status == "FAILED":
                result["failed"].append(test_name)
            elif status == "SKIPPED":
                result["skipped"].append(test_name)

        return result

    def _parse_jest_output(self, output: str) -> Dict[str, Any]:
        """Parse jest output format."""
        result = {"framework": "jest", "passed": [], "failed": [], "skipped": []}

        # Match test file results
        for match in re.finditer(r"(PASS|FAIL)\s+(\S+\.test\.(js|ts))", output):
            status = match.group(1)
            test_file = match.group(2)

            if status == "PASS":
                result["passed"].append(test_file)
            elif status == "FAIL":
                result["failed"].append(test_file)

        # Match individual test results within files (with unicode checkmark/cross)
        # ✓ (U+2713) for passed, ✕ (U+2715) for failed
        for match in re.finditer(r"✓\s+(.+?)\s+\((\d+)\s*ms\)", output):
            test_name = match.group(1).strip()
            result["passed"].append(test_name)

        for match in re.finditer(r"✕\s+(.+?)\s+\((\d+)\s*ms\)", output):
            test_name = match.group(1).strip()
            result["failed"].append(test_name)

        return result

    def _parse_junit_xml(self, output: str) -> Dict[str, Any]:
        """Parse JUnit XML format."""
        result = {"framework": "junit", "passed": [], "failed": [], "skipped": []}

        try:
            root = ET.fromstring(output)

            # Handle both <testsuites> and direct <testsuite>
            testsuites = root.findall(".//testsuite")
            if not testsuites:
                testsuites = [root] if root.tag == "testsuite" else []

            for testsuite in testsuites:
                for testcase in testsuite.findall("testcase"):
                    test_name = testcase.get("name", "")
                    classname = testcase.get("classname", "")
                    full_name = f"{classname}.{test_name}" if classname else test_name

                    # Check for failure or skip
                    if testcase.find("failure") is not None:
                        result["failed"].append(full_name)
                    elif testcase.find("skipped") is not None:
                        result["skipped"].append(full_name)
                    else:
                        result["passed"].append(full_name)

        except ET.ParseError:
            # Invalid XML, return empty result
            pass

        return result
