"""
ValidationAgent - Validates patches by applying them and running tests.

Task 6.4: ValidationAgent Implementation
Orchestrates the validation workflow:
1. Run tests before patch (baseline)
2. Apply patch to sandbox
3. Run tests after patch
4. Detect regressions
5. Generate validation report
"""

import time
from typing import Dict, Any, Optional

from .applicator import PatchApplicator
from .test_runner import TestRunner
from .regression import RegressionDetector


class ValidationAgent:
    """
    Validates patches by applying them and running test suites.

    Workflow:
    1. Establish baseline by running tests before patch
    2. Apply patch using PatchApplicator
    3. Run tests after patch application
    4. Compare results using RegressionDetector
    5. Generate comprehensive validation report
    """

    def __init__(self, patch_result: Dict[str, Any], sandbox: Any, repo_context: Dict[str, Any]):
        """
        Initialize ValidationAgent.

        Args:
            patch_result: Result from patch generation stage containing patches and metadata
            sandbox: Sandbox instance for test execution
            repo_context: Repository context with test commands and paths
        """
        self.patch_result = patch_result
        self.sandbox = sandbox
        self.repo_context = repo_context

        # Initialize components
        self.applicator = PatchApplicator()
        self.test_runner = TestRunner(sandbox)
        self.regression_detector = RegressionDetector()

    def run(self) -> Dict[str, Any]:
        """
        Execute complete validation workflow.

        Returns:
            ValidationResult dict with structure:
            {
                "status": "passed" | "failed" | "error",
                "patch_id": str,
                "patch_applied": bool,
                "test_results": dict,
                "target_test_status": "passed" | "failed" | "not_found",
                "regression_check": dict,
                "test_output": str,
                "execution_time": float
            }
        """
        start_time = time.time()

        # Get first patch from patches list
        patches = self.patch_result.get("patches", [])
        if not patches:
            return self._error_result("No patches provided", start_time)

        patch = patches[0]
        patch_id = patch.get("id", "unknown")

        result = {
            "status": "error",
            "patch_id": patch_id,
            "patch_applied": False,
            "test_results": {},
            "target_test_status": "not_found",
            "regression_check": {},
            "test_output": "",
            "execution_time": 0.0
        }

        try:
            # Step 1: Run tests before patch (baseline)
            tests_before = self._run_tests_before()

            # Step 2: Apply patch
            apply_result = self._apply_patch(patch)
            result["patch_applied"] = apply_result.get("applied", False)

            if not apply_result.get("success", False):
                result["status"] = "error"
                result["test_output"] = f"Patch application failed: {apply_result.get('error', 'Unknown error')}"
                result["execution_time"] = time.time() - start_time
                return result

            # Step 3: Run tests after patch
            tests_after = self._run_tests_after()

            # Step 4: Detect regression
            regression_info = self._detect_regression(tests_before, tests_after)

            # Step 5: Determine target test status
            target_test = self.patch_result.get("target_test")
            target_test_status = self._determine_target_test_status(
                tests_before, tests_after, target_test
            )

            # Step 6: Determine overall status
            if regression_info["is_regression"]:
                status = "failed"
            else:
                status = "passed"

            # Build result
            result.update({
                "status": status,
                "test_results": {
                    "passed": tests_after.get("passed", 0),
                    "failed": tests_after.get("failed", 0),
                    "skipped": tests_after.get("skipped", 0),
                    "total": tests_after.get("total", 0)
                },
                "target_test_status": target_test_status,
                "regression_check": regression_info,
                "test_output": tests_after.get("output", "")[:10240],  # Truncate to 10KB
                "execution_time": time.time() - start_time
            })

            return result

        except Exception as e:
            result["status"] = "error"
            result["test_output"] = f"Validation error: {str(e)}"
            result["execution_time"] = time.time() - start_time
            return result

    def _apply_patch(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply patch using PatchApplicator.

        Args:
            patch: Patch dictionary with file path and content

        Returns:
            Application result dict
        """
        file_path = patch.get("file", "")
        patch_content = patch.get("content", {})

        return self.applicator.apply_patch(
            patch_content=patch_content,
            file_path=file_path,
            sandbox=self.sandbox
        )

    def _run_tests_before(self) -> Dict[str, Any]:
        """
        Run test suite before patch application (baseline).

        Returns:
            Test results dict with statistics and failed test list
        """
        test_command = self.repo_context.get("test_command", "pytest tests/")
        working_dir = self.repo_context.get("path", ".")

        result = self.test_runner.run_test_suite(
            test_command=test_command,
            working_dir=working_dir
        )

        # Extract failed test names from output if not provided
        if "failed_tests" not in result:
            result["failed_tests"] = self._extract_failed_tests(result.get("output", ""))

        return result

    def _run_tests_after(self) -> Dict[str, Any]:
        """
        Run test suite after patch application.

        Returns:
            Test results dict with statistics and failed test list
        """
        test_command = self.repo_context.get("test_command", "pytest tests/")
        working_dir = self.repo_context.get("path", ".")

        result = self.test_runner.run_test_suite(
            test_command=test_command,
            working_dir=working_dir
        )

        # Extract failed test names from output if not provided
        if "failed_tests" not in result:
            result["failed_tests"] = self._extract_failed_tests(result.get("output", ""))

        return result

    def _detect_regression(
        self,
        tests_before: Dict[str, Any],
        tests_after: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Detect regression by comparing test results.

        Args:
            tests_before: Test results before patch
            tests_after: Test results after patch

        Returns:
            Regression comparison dict
        """
        return self.regression_detector.compare_results(tests_before, tests_after)

    def _determine_target_test_status(
        self,
        tests_before: Dict[str, Any],
        tests_after: Dict[str, Any],
        target_test: Optional[str]
    ) -> str:
        """
        Determine the status of the target test.

        Args:
            tests_before: Test results before patch
            tests_after: Test results after patch
            target_test: Name of the target test to check

        Returns:
            "passed" | "failed" | "not_found"
        """
        if not target_test:
            return "not_found"

        failed_before = tests_before.get("failed_tests", [])
        failed_after = tests_after.get("failed_tests", [])

        # Check if target test was in failed list before
        was_failing = target_test in failed_before

        # Check if target test is in failed list after
        is_failing = target_test in failed_after

        # If it was failing and now isn't, it passed
        if was_failing and not is_failing:
            return "passed"

        # If it's not in the failed list after, assume it passed
        if not is_failing:
            return "passed"

        # If it's still failing
        if is_failing:
            return "failed"

        return "not_found"

    def _generate_report(self, validation_data: Dict[str, Any]) -> str:
        """
        Generate human-readable validation report.

        Args:
            validation_data: Validation result data

        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=== Validation Report ===")
        lines.append("")

        # Status
        status = validation_data.get("status", "unknown")
        lines.append(f"Status: {status.upper()}")
        lines.append("")

        # Patch application
        patch_applied = validation_data.get("patch_applied", False)
        lines.append(f"Patch Applied: {'Yes' if patch_applied else 'No'}")
        lines.append("")

        # Test statistics before
        tests_before = validation_data.get("tests_before", {})
        lines.append("Tests Before Patch:")
        lines.append(f"  Passed: {tests_before.get('passed', 0)}")
        lines.append(f"  Failed: {tests_before.get('failed', 0)}")
        lines.append(f"  Total: {tests_before.get('total', 0)}")
        lines.append("")

        # Test statistics after
        tests_after = validation_data.get("tests_after", {})
        lines.append("Tests After Patch:")
        lines.append(f"  Passed: {tests_after.get('passed', 0)}")
        lines.append(f"  Failed: {tests_after.get('failed', 0)}")
        lines.append(f"  Total: {tests_after.get('total', 0)}")
        lines.append("")

        # Regression info
        regression_info = validation_data.get("regression_info", {})
        is_regression = regression_info.get("is_regression", False)
        lines.append(f"Regression Detected: {'Yes' if is_regression else 'No'}")

        if is_regression:
            new_failures = regression_info.get("new_failures", [])
            lines.append(f"New Failures ({len(new_failures)}):")
            for test in new_failures:
                lines.append(f"  - {test}")
        else:
            fixed_tests = regression_info.get("fixed_tests", [])
            if fixed_tests:
                lines.append(f"Fixed Tests ({len(fixed_tests)}):")
                for test in fixed_tests:
                    lines.append(f"  - {test}")

        return "\n".join(lines)

    def _extract_failed_tests(self, output: str) -> list:
        """
        Extract failed test names from test output.

        Args:
            output: Raw test output

        Returns:
            List of failed test names
        """
        # Simple extraction - look for FAILED test::name patterns
        import re
        pattern = r'FAILED\s+(\S+)'
        matches = re.findall(pattern, output)
        return matches

    def _error_result(self, error_msg: str, start_time: float) -> Dict[str, Any]:
        """
        Create an error result.

        Args:
            error_msg: Error message
            start_time: Start timestamp

        Returns:
            Error result dict
        """
        return {
            "status": "error",
            "patch_id": "unknown",
            "patch_applied": False,
            "test_results": {},
            "target_test_status": "not_found",
            "regression_check": {},
            "test_output": error_msg,
            "execution_time": time.time() - start_time
        }
