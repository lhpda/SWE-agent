"""
Tests for ValidationAgent implementation.

Task 6.4: ValidationAgent - Tests written first following TDD.
Tests cover:
- Valid patch validation
- Regression detection
- Target test status identification
- Patch application failures
- Test execution scenarios
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.swe_agent.agents.validation.agent import ValidationAgent


class TestValidationAgentInit:
    """Test ValidationAgent initialization."""

    def test_init_with_all_parameters(self):
        """Test agent initializes with patch_result, sandbox, and repo_context."""
        patch_result = {"patches": [{"id": "p1", "file": "test.py"}]}
        sandbox = Mock()
        repo_context = {"path": "/repo", "test_command": "pytest"}

        agent = ValidationAgent(patch_result, sandbox, repo_context)

        assert agent.patch_result == patch_result
        assert agent.sandbox == sandbox
        assert agent.repo_context == repo_context
        assert agent.applicator is not None
        assert agent.test_runner is not None
        assert agent.regression_detector is not None

    def test_init_creates_required_components(self):
        """Test agent creates PatchApplicator, TestRunner, and RegressionDetector."""
        agent = ValidationAgent({}, Mock(), {})

        assert hasattr(agent, 'applicator')
        assert hasattr(agent, 'test_runner')
        assert hasattr(agent, 'regression_detector')


class TestApplyPatch:
    """Test _apply_patch method."""

    @patch('src.swe_agent.agents.validation.agent.PatchApplicator')
    def test_apply_patch_success(self, mock_applicator_class):
        """Test successful patch application."""
        mock_applicator = Mock()
        mock_applicator.apply_patch.return_value = {
            "success": True,
            "applied": True,
            "file_path": "/repo/test.py",
            "snapshot_id": "snap_123"
        }
        mock_applicator_class.return_value = mock_applicator

        patch_result = {"patches": [{"id": "p1", "file": "/repo/test.py", "content": {}}]}
        agent = ValidationAgent(patch_result, Mock(), {})

        result = agent._apply_patch(patch_result["patches"][0])

        assert result["success"] is True
        assert result["applied"] is True

    @patch('src.swe_agent.agents.validation.agent.PatchApplicator')
    def test_apply_patch_failure(self, mock_applicator_class):
        """Test patch application failure."""
        mock_applicator = Mock()
        mock_applicator.apply_patch.return_value = {
            "success": False,
            "applied": False,
            "error": "Syntax error in patch"
        }
        mock_applicator_class.return_value = mock_applicator

        patch_result = {"patches": [{"id": "p1", "file": "/repo/test.py", "content": {}}]}
        agent = ValidationAgent(patch_result, Mock(), {})

        result = agent._apply_patch(patch_result["patches"][0])

        assert result["success"] is False
        assert result["applied"] is False
        assert "error" in result


class TestRunTestsBefore:
    """Test _run_tests_before method."""

    @patch('src.swe_agent.agents.validation.agent.TestRunner')
    def test_run_tests_before_success(self, mock_runner_class):
        """Test running tests before patch application."""
        mock_runner = Mock()
        mock_runner.run_test_suite.return_value = {
            "passed": 10,
            "failed": 2,
            "skipped": 1,
            "total": 13,
            "duration": 5.5,
            "failed_tests": ["test_a", "test_b"],
            "output": "test output"
        }
        mock_runner_class.return_value = mock_runner

        repo_context = {"test_command": "pytest tests/", "path": "/repo"}
        agent = ValidationAgent({}, Mock(), repo_context)

        result = agent._run_tests_before()

        assert result["passed"] == 10
        assert result["failed"] == 2
        assert len(result["failed_tests"]) == 2


class TestRunTestsAfter:
    """Test _run_tests_after method."""

    @patch('src.swe_agent.agents.validation.agent.TestRunner')
    def test_run_tests_after_success(self, mock_runner_class):
        """Test running tests after patch application."""
        mock_runner = Mock()
        mock_runner.run_test_suite.return_value = {
            "passed": 12,
            "failed": 0,
            "skipped": 1,
            "total": 13,
            "duration": 5.2,
            "failed_tests": [],
            "output": "all tests passed"
        }
        mock_runner_class.return_value = mock_runner

        repo_context = {"test_command": "pytest tests/", "path": "/repo"}
        agent = ValidationAgent({}, Mock(), repo_context)

        result = agent._run_tests_after()

        assert result["passed"] == 12
        assert result["failed"] == 0
        assert len(result["failed_tests"]) == 0


class TestDetectRegression:
    """Test _detect_regression method."""

    @patch('src.swe_agent.agents.validation.agent.RegressionDetector')
    def test_detect_no_regression(self, mock_detector_class):
        """Test regression detection when no regression exists."""
        mock_detector = Mock()
        mock_detector.compare_results.return_value = {
            "is_regression": False,
            "new_failures": [],
            "fixed_tests": ["test_a", "test_b"],
            "still_failing": [],
            "net_change": 2
        }
        mock_detector_class.return_value = mock_detector

        agent = ValidationAgent({}, Mock(), {})

        before = {"failed_tests": ["test_a", "test_b"]}
        after = {"failed_tests": []}

        result = agent._detect_regression(before, after)

        assert result["is_regression"] is False
        assert len(result["fixed_tests"]) == 2

    @patch('src.swe_agent.agents.validation.agent.RegressionDetector')
    def test_detect_regression_exists(self, mock_detector_class):
        """Test regression detection when regression exists."""
        mock_detector = Mock()
        mock_detector.compare_results.return_value = {
            "is_regression": True,
            "new_failures": ["test_c", "test_d"],
            "fixed_tests": ["test_a"],
            "still_failing": [],
            "net_change": -1
        }
        mock_detector_class.return_value = mock_detector

        agent = ValidationAgent({}, Mock(), {})

        before = {"failed_tests": ["test_a"]}
        after = {"failed_tests": ["test_c", "test_d"]}

        result = agent._detect_regression(before, after)

        assert result["is_regression"] is True
        assert len(result["new_failures"]) == 2


class TestGenerateReport:
    """Test _generate_report method."""

    def test_generate_report_success(self):
        """Test report generation for successful validation."""
        agent = ValidationAgent({}, Mock(), {})

        validation_data = {
            "status": "passed",
            "patch_applied": True,
            "tests_before": {"passed": 10, "failed": 2, "total": 12},
            "tests_after": {"passed": 12, "failed": 0, "total": 12},
            "regression_info": {
                "is_regression": False,
                "fixed_tests": ["test_a", "test_b"],
                "new_failures": []
            }
        }

        report = agent._generate_report(validation_data)

        assert "passed" in report.lower() or "success" in report.lower()
        assert "test_a" in report
        assert "test_b" in report

    def test_generate_report_regression(self):
        """Test report generation for regression."""
        agent = ValidationAgent({}, Mock(), {})

        validation_data = {
            "status": "failed",
            "patch_applied": True,
            "tests_before": {"passed": 10, "failed": 2, "total": 12},
            "tests_after": {"passed": 8, "failed": 4, "total": 12},
            "regression_info": {
                "is_regression": True,
                "fixed_tests": [],
                "new_failures": ["test_c", "test_d"]
            }
        }

        report = agent._generate_report(validation_data)

        assert "regression" in report.lower() or "failed" in report.lower()
        assert "test_c" in report
        assert "test_d" in report


class TestValidationAgentRun:
    """Test complete run method - main integration."""

    @patch('src.swe_agent.agents.validation.agent.PatchApplicator')
    @patch('src.swe_agent.agents.validation.agent.TestRunner')
    @patch('src.swe_agent.agents.validation.agent.RegressionDetector')
    def test_run_valid_patch_success(self, mock_detector_class, mock_runner_class, mock_applicator_class):
        """Test full validation run with valid patch that fixes tests."""
        # Setup mocks
        mock_applicator = Mock()
        mock_applicator.apply_patch.return_value = {
            "success": True,
            "applied": True,
            "file_path": "/repo/test.py"
        }
        mock_applicator_class.return_value = mock_applicator

        mock_runner = Mock()
        mock_runner.run_test_suite.side_effect = [
            {  # Before patch
                "passed": 10,
                "failed": 2,
                "skipped": 1,
                "total": 13,
                "duration": 5.0,
                "failed_tests": ["test_target", "test_other"],
                "output": "before output"
            },
            {  # After patch
                "passed": 12,
                "failed": 0,
                "skipped": 1,
                "total": 13,
                "duration": 5.2,
                "failed_tests": [],
                "output": "after output"
            }
        ]
        mock_runner_class.return_value = mock_runner

        mock_detector = Mock()
        mock_detector.compare_results.return_value = {
            "is_regression": False,
            "new_failures": [],
            "fixed_tests": ["test_target", "test_other"],
            "still_failing": [],
            "net_change": 2
        }
        mock_detector_class.return_value = mock_detector

        patch_result = {
            "patches": [{"id": "p1", "file": "/repo/test.py", "content": {}}],
            "target_test": "test_target"
        }
        repo_context = {"test_command": "pytest tests/", "path": "/repo"}

        agent = ValidationAgent(patch_result, Mock(), repo_context)
        result = agent.run()

        assert result["status"] == "passed"
        assert result["patch_applied"] is True
        assert result["test_results"]["passed"] == 12
        assert result["regression_check"]["is_regression"] is False
        assert result["execution_time"] >= 0

    @patch('src.swe_agent.agents.validation.agent.PatchApplicator')
    @patch('src.swe_agent.agents.validation.agent.TestRunner')
    @patch('src.swe_agent.agents.validation.agent.RegressionDetector')
    def test_run_regression_detected(self, mock_detector_class, mock_runner_class, mock_applicator_class):
        """Test validation run detects regression."""
        # Setup mocks
        mock_applicator = Mock()
        mock_applicator.apply_patch.return_value = {
            "success": True,
            "applied": True,
            "file_path": "/repo/test.py"
        }
        mock_applicator_class.return_value = mock_applicator

        mock_runner = Mock()
        mock_runner.run_test_suite.side_effect = [
            {  # Before patch
                "passed": 10,
                "failed": 2,
                "skipped": 1,
                "total": 13,
                "duration": 5.0,
                "failed_tests": ["test_a", "test_b"],
                "output": "before output"
            },
            {  # After patch - introduces new failures
                "passed": 8,
                "failed": 5,
                "skipped": 0,
                "total": 13,
                "duration": 5.5,
                "failed_tests": ["test_a", "test_b", "test_c", "test_d", "test_e"],
                "output": "after output with failures"
            }
        ]
        mock_runner_class.return_value = mock_runner

        mock_detector = Mock()
        mock_detector.compare_results.return_value = {
            "is_regression": True,
            "new_failures": ["test_c", "test_d", "test_e"],
            "fixed_tests": [],
            "still_failing": ["test_a", "test_b"],
            "net_change": -3
        }
        mock_detector_class.return_value = mock_detector

        patch_result = {"patches": [{"id": "p1", "file": "/repo/test.py", "content": {}}]}
        repo_context = {"test_command": "pytest tests/", "path": "/repo"}

        agent = ValidationAgent(patch_result, Mock(), repo_context)
        result = agent.run()

        assert result["status"] == "failed"
        assert result["regression_check"]["is_regression"] is True
        assert len(result["regression_check"]["new_failures"]) == 3

    @patch('src.swe_agent.agents.validation.agent.PatchApplicator')
    def test_run_patch_application_fails(self, mock_applicator_class):
        """Test validation when patch application fails."""
        mock_applicator = Mock()
        mock_applicator.apply_patch.return_value = {
            "success": False,
            "applied": False,
            "error": "File not found"
        }
        mock_applicator_class.return_value = mock_applicator

        patch_result = {"patches": [{"id": "p1", "file": "/repo/test.py", "content": {}}]}
        repo_context = {"test_command": "pytest tests/", "path": "/repo"}

        agent = ValidationAgent(patch_result, Mock(), repo_context)
        result = agent.run()

        assert result["status"] == "error"
        assert result["patch_applied"] is False

    @patch('src.swe_agent.agents.validation.agent.PatchApplicator')
    @patch('src.swe_agent.agents.validation.agent.TestRunner')
    @patch('src.swe_agent.agents.validation.agent.RegressionDetector')
    def test_run_target_test_identified(self, mock_detector_class, mock_runner_class, mock_applicator_class):
        """Test that target test status is correctly identified."""
        # Setup mocks
        mock_applicator = Mock()
        mock_applicator.apply_patch.return_value = {"success": True, "applied": True}
        mock_applicator_class.return_value = mock_applicator

        mock_runner = Mock()
        mock_runner.run_test_suite.side_effect = [
            {
                "passed": 10,
                "failed": 1,
                "skipped": 0,
                "total": 11,
                "duration": 5.0,
                "failed_tests": ["test_target"],
                "output": "before"
            },
            {
                "passed": 11,
                "failed": 0,
                "skipped": 0,
                "total": 11,
                "duration": 5.0,
                "failed_tests": [],
                "output": "after"
            }
        ]
        mock_runner_class.return_value = mock_runner

        mock_detector = Mock()
        mock_detector.compare_results.return_value = {
            "is_regression": False,
            "new_failures": [],
            "fixed_tests": ["test_target"],
            "still_failing": [],
            "net_change": 1
        }
        mock_detector_class.return_value = mock_detector

        patch_result = {
            "patches": [{"id": "p1", "file": "/repo/test.py", "content": {}}],
            "target_test": "test_target"
        }
        repo_context = {"test_command": "pytest tests/", "path": "/repo"}

        agent = ValidationAgent(patch_result, Mock(), repo_context)
        result = agent.run()

        assert result["target_test_status"] == "passed"
        assert "test_target" in result["regression_check"]["fixed_tests"]

    @patch('src.swe_agent.agents.validation.agent.PatchApplicator')
    @patch('src.swe_agent.agents.validation.agent.TestRunner')
    @patch('src.swe_agent.agents.validation.agent.RegressionDetector')
    def test_run_measures_execution_time(self, mock_detector_class, mock_runner_class, mock_applicator_class):
        """Test that execution time is measured."""
        # Setup mocks
        mock_applicator = Mock()
        mock_applicator.apply_patch.return_value = {"success": True, "applied": True}
        mock_applicator_class.return_value = mock_applicator

        mock_runner = Mock()
        mock_runner.run_test_suite.return_value = {
            "passed": 10,
            "failed": 0,
            "skipped": 0,
            "total": 10,
            "duration": 5.0,
            "failed_tests": [],
            "output": "output"
        }
        mock_runner_class.return_value = mock_runner

        mock_detector = Mock()
        mock_detector.compare_results.return_value = {
            "is_regression": False,
            "new_failures": [],
            "fixed_tests": [],
            "still_failing": [],
            "net_change": 0
        }
        mock_detector_class.return_value = mock_detector

        patch_result = {"patches": [{"id": "p1", "file": "/repo/test.py", "content": {}}]}
        repo_context = {"test_command": "pytest tests/", "path": "/repo"}

        agent = ValidationAgent(patch_result, Mock(), repo_context)
        result = agent.run()

        assert "execution_time" in result
        assert result["execution_time"] >= 0
        assert isinstance(result["execution_time"], (int, float))
