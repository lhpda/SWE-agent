"""
Unit tests for RegressionDetector.

Task 6.3: Regression Detector
Tests verify regression detection, new failure identification, fixed test detection, and edge cases.
"""

import pytest
from src.swe_agent.agents.validation.regression import RegressionDetector


class TestRegressionDetectorBasics:
    """Test basic RegressionDetector functionality."""

    def test_initialization(self):
        """Test RegressionDetector initialization."""
        detector = RegressionDetector()
        assert detector is not None

    def test_empty_results_input(self):
        """Test handling of empty test results."""
        detector = RegressionDetector()
        before = {"passed": 0, "failed": 0, "skipped": 0, "total": 0, "failed_tests": []}
        after = {"passed": 0, "failed": 0, "skipped": 0, "total": 0, "failed_tests": []}

        result = detector.compare_results(before, after)

        assert result["is_regression"] is False
        assert result["new_failures"] == []
        assert result["fixed_tests"] == []
        assert result["still_failing"] == []
        assert result["net_change"] == 0


class TestDetectNewFailures:
    """Test detect_new_failures method."""

    def test_detect_single_new_failure(self):
        """Test detecting a single new failure."""
        detector = RegressionDetector()
        before = {"passed": 3, "failed": 0, "skipped": 0, "total": 3, "failed_tests": []}
        after = {"passed": 2, "failed": 1, "skipped": 0, "total": 3, "failed_tests": ["test_example.py::test_one"]}

        new_failures = detector.detect_new_failures(before, after)

        assert len(new_failures) == 1
        assert "test_example.py::test_one" in new_failures

    def test_detect_multiple_new_failures(self):
        """Test detecting multiple new failures."""
        detector = RegressionDetector()
        before = {"passed": 5, "failed": 0, "skipped": 0, "total": 5, "failed_tests": []}
        after = {
            "passed": 2,
            "failed": 3,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two", "test_c.py::test_three"]
        }

        new_failures = detector.detect_new_failures(before, after)

        assert len(new_failures) == 3
        assert "test_a.py::test_one" in new_failures
        assert "test_b.py::test_two" in new_failures
        assert "test_c.py::test_three" in new_failures

    def test_no_new_failures_all_same(self):
        """Test no new failures when failures remain the same."""
        detector = RegressionDetector()
        before = {
            "passed": 2,
            "failed": 1,
            "skipped": 0,
            "total": 3,
            "failed_tests": ["test_example.py::test_broken"]
        }
        after = {
            "passed": 2,
            "failed": 1,
            "skipped": 0,
            "total": 3,
            "failed_tests": ["test_example.py::test_broken"]
        }

        new_failures = detector.detect_new_failures(before, after)

        assert len(new_failures) == 0

    def test_new_failures_with_existing_failures(self):
        """Test detecting new failures when some tests were already failing."""
        detector = RegressionDetector()
        before = {
            "passed": 3,
            "failed": 1,
            "skipped": 0,
            "total": 4,
            "failed_tests": ["test_old.py::test_broken"]
        }
        after = {
            "passed": 2,
            "failed": 2,
            "skipped": 0,
            "total": 4,
            "failed_tests": ["test_old.py::test_broken", "test_new.py::test_regression"]
        }

        new_failures = detector.detect_new_failures(before, after)

        assert len(new_failures) == 1
        assert "test_new.py::test_regression" in new_failures
        assert "test_old.py::test_broken" not in new_failures


class TestDetectFixedTests:
    """Test detect_fixed_tests method."""

    def test_detect_single_fixed_test(self):
        """Test detecting a single fixed test."""
        detector = RegressionDetector()
        before = {
            "passed": 2,
            "failed": 1,
            "skipped": 0,
            "total": 3,
            "failed_tests": ["test_example.py::test_was_broken"]
        }
        after = {"passed": 3, "failed": 0, "skipped": 0, "total": 3, "failed_tests": []}

        fixed_tests = detector.detect_fixed_tests(before, after)

        assert len(fixed_tests) == 1
        assert "test_example.py::test_was_broken" in fixed_tests

    def test_detect_multiple_fixed_tests(self):
        """Test detecting multiple fixed tests."""
        detector = RegressionDetector()
        before = {
            "passed": 2,
            "failed": 3,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two", "test_c.py::test_three"]
        }
        after = {"passed": 5, "failed": 0, "skipped": 0, "total": 5, "failed_tests": []}

        fixed_tests = detector.detect_fixed_tests(before, after)

        assert len(fixed_tests) == 3
        assert "test_a.py::test_one" in fixed_tests
        assert "test_b.py::test_two" in fixed_tests
        assert "test_c.py::test_three" in fixed_tests

    def test_no_fixed_tests(self):
        """Test no fixed tests when failures remain."""
        detector = RegressionDetector()
        before = {
            "passed": 2,
            "failed": 1,
            "skipped": 0,
            "total": 3,
            "failed_tests": ["test_example.py::test_broken"]
        }
        after = {
            "passed": 2,
            "failed": 1,
            "skipped": 0,
            "total": 3,
            "failed_tests": ["test_example.py::test_broken"]
        }

        fixed_tests = detector.detect_fixed_tests(before, after)

        assert len(fixed_tests) == 0

    def test_partial_fixes(self):
        """Test detecting partial fixes when some tests are fixed but not all."""
        detector = RegressionDetector()
        before = {
            "passed": 2,
            "failed": 3,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two", "test_c.py::test_three"]
        }
        after = {
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_b.py::test_two"]
        }

        fixed_tests = detector.detect_fixed_tests(before, after)

        assert len(fixed_tests) == 2
        assert "test_a.py::test_one" in fixed_tests
        assert "test_c.py::test_three" in fixed_tests
        assert "test_b.py::test_two" not in fixed_tests


class TestIsRegression:
    """Test is_regression method."""

    def test_is_regression_with_new_failures(self):
        """Test regression detection when new failures occur."""
        detector = RegressionDetector()
        before = {"passed": 5, "failed": 0, "skipped": 0, "total": 5, "failed_tests": []}
        after = {
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_example.py::test_new_failure"]
        }

        is_regression = detector.is_regression(before, after)

        assert is_regression is True

    def test_not_regression_when_fixing_tests(self):
        """Test no regression when only fixes occur."""
        detector = RegressionDetector()
        before = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two"]
        }
        after = {"passed": 5, "failed": 0, "skipped": 0, "total": 5, "failed_tests": []}

        is_regression = detector.is_regression(before, after)

        assert is_regression is False

    def test_not_regression_when_no_changes(self):
        """Test no regression when test results remain the same."""
        detector = RegressionDetector()
        before = {
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_example.py::test_broken"]
        }
        after = {
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_example.py::test_broken"]
        }

        is_regression = detector.is_regression(before, after)

        assert is_regression is False

    def test_regression_even_with_some_fixes(self):
        """Test regression is detected even when some tests are fixed."""
        detector = RegressionDetector()
        before = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_old1.py::test_broken", "test_old2.py::test_broken"]
        }
        after = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_old1.py::test_broken", "test_new.py::test_regression"]
        }

        is_regression = detector.is_regression(before, after)

        assert is_regression is True


class TestCompareResults:
    """Test compare_results method with complete output."""

    def test_compare_with_new_failures_only(self):
        """Test comparison with only new failures."""
        detector = RegressionDetector()
        before = {"passed": 5, "failed": 0, "skipped": 0, "total": 5, "failed_tests": []}
        after = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two"]
        }

        result = detector.compare_results(before, after)

        assert result["is_regression"] is True
        assert len(result["new_failures"]) == 2
        assert "test_a.py::test_one" in result["new_failures"]
        assert "test_b.py::test_two" in result["new_failures"]
        assert len(result["fixed_tests"]) == 0
        assert len(result["still_failing"]) == 0
        assert result["net_change"] == -2

    def test_compare_with_fixes_only(self):
        """Test comparison with only fixed tests."""
        detector = RegressionDetector()
        before = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two"]
        }
        after = {"passed": 5, "failed": 0, "skipped": 0, "total": 5, "failed_tests": []}

        result = detector.compare_results(before, after)

        assert result["is_regression"] is False
        assert len(result["new_failures"]) == 0
        assert len(result["fixed_tests"]) == 2
        assert "test_a.py::test_one" in result["fixed_tests"]
        assert "test_b.py::test_two" in result["fixed_tests"]
        assert len(result["still_failing"]) == 0
        assert result["net_change"] == 2

    def test_compare_with_still_failing_tests(self):
        """Test comparison with tests that were and still are failing."""
        detector = RegressionDetector()
        before = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two"]
        }
        after = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_a.py::test_one", "test_b.py::test_two"]
        }

        result = detector.compare_results(before, after)

        assert result["is_regression"] is False
        assert len(result["new_failures"]) == 0
        assert len(result["fixed_tests"]) == 0
        assert len(result["still_failing"]) == 2
        assert "test_a.py::test_one" in result["still_failing"]
        assert "test_b.py::test_two" in result["still_failing"]
        assert result["net_change"] == 0

    def test_compare_with_mixed_changes(self):
        """Test comparison with both new failures and fixes."""
        detector = RegressionDetector()
        before = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_old1.py::test_broken", "test_old2.py::test_broken"]
        }
        after = {
            "passed": 3,
            "failed": 2,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_old1.py::test_broken", "test_new.py::test_regression"]
        }

        result = detector.compare_results(before, after)

        assert result["is_regression"] is True
        assert len(result["new_failures"]) == 1
        assert "test_new.py::test_regression" in result["new_failures"]
        assert len(result["fixed_tests"]) == 1
        assert "test_old2.py::test_broken" in result["fixed_tests"]
        assert len(result["still_failing"]) == 1
        assert "test_old1.py::test_broken" in result["still_failing"]
        assert result["net_change"] == 0

    def test_compare_all_tests_pass_before_and_after(self):
        """Test comparison when all tests pass in both runs."""
        detector = RegressionDetector()
        before = {"passed": 10, "failed": 0, "skipped": 0, "total": 10, "failed_tests": []}
        after = {"passed": 10, "failed": 0, "skipped": 0, "total": 10, "failed_tests": []}

        result = detector.compare_results(before, after)

        assert result["is_regression"] is False
        assert len(result["new_failures"]) == 0
        assert len(result["fixed_tests"]) == 0
        assert len(result["still_failing"]) == 0
        assert result["net_change"] == 0

    def test_compare_all_tests_fail_before_and_after(self):
        """Test comparison when all tests fail in both runs."""
        detector = RegressionDetector()
        before = {
            "passed": 0,
            "failed": 5,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_1", "test_2", "test_3", "test_4", "test_5"]
        }
        after = {
            "passed": 0,
            "failed": 5,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_1", "test_2", "test_3", "test_4", "test_5"]
        }

        result = detector.compare_results(before, after)

        assert result["is_regression"] is False
        assert len(result["new_failures"]) == 0
        assert len(result["fixed_tests"]) == 0
        assert len(result["still_failing"]) == 5
        assert result["net_change"] == 0

    def test_compare_with_positive_net_change(self):
        """Test net change calculation when more tests are fixed than broken."""
        detector = RegressionDetector()
        before = {
            "passed": 2,
            "failed": 3,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_1", "test_2", "test_3"]
        }
        after = {
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_4"]
        }

        result = detector.compare_results(before, after)

        # 3 fixed (test_1, test_2, test_3), 1 new (test_4)
        assert result["is_regression"] is True  # Because there's a new failure
        assert len(result["new_failures"]) == 1
        assert len(result["fixed_tests"]) == 3
        assert result["net_change"] == 2  # 3 fixed - 1 new = +2

    def test_compare_with_negative_net_change(self):
        """Test net change calculation when more tests break than are fixed."""
        detector = RegressionDetector()
        before = {
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_1"]
        }
        after = {
            "passed": 2,
            "failed": 3,
            "skipped": 0,
            "total": 5,
            "failed_tests": ["test_2", "test_3", "test_4"]
        }

        result = detector.compare_results(before, after)

        # 1 fixed (test_1), 3 new (test_2, test_3, test_4)
        assert result["is_regression"] is True
        assert len(result["new_failures"]) == 3
        assert len(result["fixed_tests"]) == 1
        assert result["net_change"] == -2  # 1 fixed - 3 new = -2
