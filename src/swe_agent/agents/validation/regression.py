"""
Regression detector for comparing test results before and after patches.

Task 6.3: Regression Detector
Provides functionality to detect regressions, new failures, and fixed tests.
"""

from typing import Dict, List, Any


class RegressionDetector:
    """Detects regressions by comparing test results before and after patch application."""

    def __init__(self):
        """Initialize the RegressionDetector."""
        pass

    def detect_new_failures(self, before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
        """
        Detect tests that are failing after the patch but were passing before.

        Args:
            before: Test results before patch (with failed_tests list)
            after: Test results after patch (with failed_tests list)

        Returns:
            List of test names that are newly failing
        """
        before_failed = set(before.get("failed_tests", []))
        after_failed = set(after.get("failed_tests", []))

        # New failures are tests that failed after but not before
        new_failures = after_failed - before_failed

        return list(new_failures)

    def detect_fixed_tests(self, before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
        """
        Detect tests that were failing before but are now passing.

        Args:
            before: Test results before patch (with failed_tests list)
            after: Test results after patch (with failed_tests list)

        Returns:
            List of test names that have been fixed
        """
        before_failed = set(before.get("failed_tests", []))
        after_failed = set(after.get("failed_tests", []))

        # Fixed tests are tests that failed before but not after
        fixed_tests = before_failed - after_failed

        return list(fixed_tests)

    def is_regression(self, before: Dict[str, Any], after: Dict[str, Any]) -> bool:
        """
        Determine if a regression has occurred.

        A regression occurs when there are new test failures after the patch.

        Args:
            before: Test results before patch
            after: Test results after patch

        Returns:
            True if regression detected (new failures exist), False otherwise
        """
        new_failures = self.detect_new_failures(before, after)
        return len(new_failures) > 0

    def compare_results(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare test results before and after patch application.

        Args:
            before: Test results before patch with structure:
                {
                    "passed": int,
                    "failed": int,
                    "skipped": int,
                    "total": int,
                    "failed_tests": List[str]
                }
            after: Test results after patch with same structure

        Returns:
            Dictionary containing:
                {
                    "is_regression": bool,
                    "new_failures": List[str],
                    "fixed_tests": List[str],
                    "still_failing": List[str],
                    "net_change": int  # fixed - new_failures
                }
        """
        new_failures = self.detect_new_failures(before, after)
        fixed_tests = self.detect_fixed_tests(before, after)

        # Still failing tests are those that failed both before and after
        before_failed = set(before.get("failed_tests", []))
        after_failed = set(after.get("failed_tests", []))
        still_failing = list(before_failed & after_failed)

        # Net change: positive means improvement, negative means degradation
        net_change = len(fixed_tests) - len(new_failures)

        return {
            "is_regression": self.is_regression(before, after),
            "new_failures": new_failures,
            "fixed_tests": fixed_tests,
            "still_failing": still_failing,
            "net_change": net_change
        }
