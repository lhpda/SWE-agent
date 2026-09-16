"""Tests for ReproductionAgent.

Task 4.3: ReproductionAgent implementation tests
Following TDD: Write tests first, then implementation.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from swe_agent.agents.reproduction.agent import ReproductionAgent
from swe_agent.types import LocalizationResult, RepositoryContext, ReproductionResult


@pytest.fixture
def localization_result():
    """Sample localization result."""
    return LocalizationResult(
        status="success",
        candidates=[
            {"file": "src/calculator.py", "confidence": 0.9, "line": 42},
            {"file": "src/utils.py", "confidence": 0.7, "line": 10},
        ],
        search_strategy="bm25",
        execution_time=1.5,
        tool_calls=3,
    )


@pytest.fixture
def repo_context():
    """Sample repository context."""
    return RepositoryContext(
        path="/workspace/test-repo",
        git={"branch": "main", "commit": "abc123"},
        project_type="python",
        test_framework="pytest",
        dependencies={"requirements.txt": True},
    )


@pytest.fixture
def mock_sandbox():
    """Mock DockerSandbox instance."""
    sandbox = Mock()
    sandbox.session_id = "test-session-123"
    sandbox.execute = Mock()
    return sandbox


class TestReproductionAgentInit:
    """Test ReproductionAgent initialization."""

    def test_init_with_valid_inputs(self, localization_result, repo_context, mock_sandbox):
        """Test initialization with valid inputs."""
        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)

        assert agent.localization_result == localization_result
        assert agent.repo_context == repo_context
        assert agent.sandbox == mock_sandbox
        assert agent.max_attempts == 5

    def test_init_with_custom_max_attempts(self, localization_result, repo_context, mock_sandbox):
        """Test initialization with custom max attempts."""
        agent = ReproductionAgent(
            localization_result, repo_context, mock_sandbox, max_attempts=3
        )

        assert agent.max_attempts == 3


class TestProjectDetection:
    """Test project type and framework detection."""

    @patch('swe_agent.agents.reproduction.agent.ProjectTypeDetector')
    @patch('swe_agent.agents.reproduction.agent.TestFrameworkDetector')
    def test_detect_project_python_pytest(
        self, mock_framework_detector, mock_type_detector,
        localization_result, repo_context, mock_sandbox
    ):
        """Test detection of Python project with pytest."""
        # Setup mocks
        mock_type_detector.return_value.detect.return_value = {
            "project_type": "python",
            "indicators": ["requirements.txt"],
        }
        mock_framework_detector.return_value.detect.return_value = {
            "framework": "pytest",
            "indicators": ["pytest.ini"],
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent._detect_project()

        assert result["project_type"] == "python"
        assert result["framework"] == "pytest"
        mock_type_detector.assert_called_once_with(repo_context.path)
        mock_framework_detector.assert_called_once()

    @patch('swe_agent.agents.reproduction.agent.ProjectTypeDetector')
    @patch('swe_agent.agents.reproduction.agent.TestFrameworkDetector')
    def test_detect_project_nodejs_jest(
        self, mock_framework_detector, mock_type_detector,
        localization_result, repo_context, mock_sandbox
    ):
        """Test detection of Node.js project with jest."""
        mock_type_detector.return_value.detect.return_value = {
            "project_type": "nodejs",
            "indicators": ["package.json"],
        }
        mock_framework_detector.return_value.detect.return_value = {
            "framework": "jest",
            "indicators": ["package.json"],
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent._detect_project()

        assert result["project_type"] == "nodejs"
        assert result["framework"] == "jest"


class TestDependencyInstallation:
    """Test dependency installation."""

    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    def test_install_dependencies_not_needed(
        self, mock_dep_detector, localization_result, repo_context, mock_sandbox
    ):
        """Test when dependencies don't need installation."""
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": False,
            "reason": "node_modules_exists",
            "install_command": None,
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        agent.project_info = {"project_type": "nodejs", "framework": "jest"}
        result = agent._install_dependencies()

        assert result["installed"] is False
        assert result["reason"] == "node_modules_exists"
        mock_sandbox.execute.assert_not_called()

    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    def test_install_dependencies_success(
        self, mock_dep_detector, localization_result, repo_context, mock_sandbox
    ):
        """Test successful dependency installation."""
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": True,
            "reason": "dependencies_file_exists",
            "install_command": "pip install -r requirements.txt",
        }
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "Successfully installed packages",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 10.5,
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        agent.project_info = {"project_type": "python", "framework": "pytest"}
        result = agent._install_dependencies()

        assert result["installed"] is True
        assert result["execution_time"] == 10.5
        mock_sandbox.execute.assert_called_once()

    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    def test_install_dependencies_failure(
        self, mock_dep_detector, localization_result, repo_context, mock_sandbox
    ):
        """Test failed dependency installation."""
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": True,
            "reason": "dependencies_file_exists",
            "install_command": "pip install -r requirements.txt",
        }
        mock_sandbox.execute.return_value = {
            "status": "error",
            "stdout": "",
            "stderr": "Package not found",
            "exit_code": 1,
            "execution_time": 2.0,
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        agent.project_info = {"project_type": "python", "framework": "pytest"}
        result = agent._install_dependencies()

        assert result["installed"] is False
        assert "error" in result


class TestRunTests:
    """Test test execution in sandbox."""

    @patch('swe_agent.agents.reproduction.agent.TestCommandInferrer')
    def test_run_tests_success(
        self, mock_cmd_inferrer, localization_result, repo_context, mock_sandbox
    ):
        """Test successful test execution."""
        mock_cmd_inferrer.return_value.infer.return_value = {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": [],
        }
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "test_example.py::test_function FAILED\nAssertionError: 1 != 2",
            "stderr": "",
            "exit_code": 1,
            "execution_time": 3.5,
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent._run_tests("pytest")

        assert result["status"] == "success"
        assert result["exit_code"] == 1
        assert result["execution_time"] == 3.5
        assert "test_function FAILED" in result["stdout"]

    @patch('swe_agent.agents.reproduction.agent.TestCommandInferrer')
    def test_run_tests_with_fallback_commands(
        self, mock_cmd_inferrer, localization_result, repo_context, mock_sandbox
    ):
        """Test test execution with fallback to alternative commands."""
        mock_cmd_inferrer.return_value.infer.return_value = {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": [],
        }
        # First command fails, second succeeds
        mock_sandbox.execute.side_effect = [
            {
                "status": "error",
                "stdout": "",
                "stderr": "pytest: command not found",
                "exit_code": 127,
                "execution_time": 0.1,
            },
            {
                "status": "success",
                "stdout": "test passed",
                "stderr": "",
                "exit_code": 1,
                "execution_time": 2.0,
            },
        ]

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        agent.project_info = {"project_type": "python", "framework": "pytest"}
        result = agent._run_tests_with_retry()

        # Should have tried fallback command
        assert mock_sandbox.execute.call_count >= 1
        assert result["status"] == "success"


class TestAnalyzeResults:
    """Test result analysis."""

    @patch('swe_agent.agents.reproduction.agent.LogAnalyzer')
    def test_analyze_results_reproduced(
        self, mock_log_analyzer, localization_result, repo_context, mock_sandbox
    ):
        """Test analysis when error is successfully reproduced."""
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.identify_error_type.return_value = "AssertionError"
        mock_analyzer_instance.extract_root_cause.return_value = {
            "file": "src/calculator.py",
            "line": 42,
        }
        mock_analyzer_instance.extract_stack_traces.return_value = [
            "Traceback...\nFile src/calculator.py, line 42\nAssertionError"
        ]
        mock_analyzer_instance.truncate_log.return_value = "Truncated log..."
        mock_log_analyzer.return_value = mock_analyzer_instance

        test_output = "test_example.py FAILED\nAssertionError: Expected 4 but got 5"

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent._analyze_results(test_output, exit_code=1)

        assert result["status"] == "reproduced"
        assert result["error_details"]["error_type"] == "AssertionError"
        assert result["root_cause"]["file"] == "src/calculator.py"
        assert result["root_cause"]["line"] == 42

    @patch('swe_agent.agents.reproduction.agent.LogAnalyzer')
    def test_analyze_results_not_reproduced(
        self, mock_log_analyzer, localization_result, repo_context, mock_sandbox
    ):
        """Test analysis when error is not reproduced (tests pass)."""
        test_output = "====== 5 passed in 2.3s ======"

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent._analyze_results(test_output, exit_code=0)

        assert result["status"] == "not_reproduced"

    @patch('swe_agent.agents.reproduction.agent.LogAnalyzer')
    def test_analyze_results_with_stack_trace(
        self, mock_log_analyzer, localization_result, repo_context, mock_sandbox
    ):
        """Test analysis extracts stack trace information."""
        mock_analyzer_instance = Mock()
        mock_analyzer_instance.identify_error_type.return_value = "ValueError"
        mock_analyzer_instance.extract_root_cause.return_value = {
            "file": "src/utils.py",
            "line": 15,
        }
        mock_analyzer_instance.extract_stack_traces.return_value = [
            'File "src/utils.py", line 15\nValueError: invalid literal'
        ]
        mock_analyzer_instance.truncate_log.return_value = "Log content..."
        mock_log_analyzer.return_value = mock_analyzer_instance

        test_output = 'File "src/utils.py", line 15\nValueError: invalid literal'

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent._analyze_results(test_output, exit_code=1)

        assert result["status"] == "reproduced"
        assert result["error_details"]["error_type"] == "ValueError"
        assert len(result["error_details"]["stack_trace"]) == 1


class TestReproductionAgentRun:
    """Test main run() method."""

    @patch('swe_agent.agents.reproduction.agent.ProjectTypeDetector')
    @patch('swe_agent.agents.reproduction.agent.TestFrameworkDetector')
    @patch('swe_agent.agents.reproduction.agent.TestCommandInferrer')
    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    @patch('swe_agent.agents.reproduction.agent.LogAnalyzer')
    def test_run_successful_reproduction(
        self, mock_log_analyzer, mock_dep_detector, mock_cmd_inferrer,
        mock_framework_detector, mock_type_detector,
        localization_result, repo_context, mock_sandbox
    ):
        """Test successful error reproduction flow."""
        # Setup all mocks
        mock_type_detector.return_value.detect.return_value = {
            "project_type": "python",
            "indicators": ["requirements.txt"],
        }
        mock_framework_detector.return_value.detect.return_value = {
            "framework": "pytest",
            "indicators": ["pytest.ini"],
        }
        mock_cmd_inferrer.return_value.infer.return_value = {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": [],
        }
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": False,
            "reason": "no_dependency_file",
            "install_command": None,
        }

        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "test_example.py::test_add FAILED\nAssertionError",
            "stderr": "",
            "exit_code": 1,
            "execution_time": 2.0,
        }

        mock_analyzer_instance = Mock()
        mock_analyzer_instance.identify_error_type.return_value = "AssertionError"
        mock_analyzer_instance.extract_root_cause.return_value = {
            "file": "src/calculator.py",
            "line": 42,
        }
        mock_analyzer_instance.extract_stack_traces.return_value = ["trace"]
        mock_analyzer_instance.truncate_log.return_value = "log"
        mock_log_analyzer.return_value = mock_analyzer_instance

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent.run()

        assert isinstance(result, ReproductionResult)
        assert result.status == "reproduced"
        assert result.test_command == "pytest"
        assert result.execution_time > 0
        assert result.attempts == 1

    @patch('swe_agent.agents.reproduction.agent.ProjectTypeDetector')
    @patch('swe_agent.agents.reproduction.agent.TestFrameworkDetector')
    @patch('swe_agent.agents.reproduction.agent.TestCommandInferrer')
    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    def test_run_not_reproduced(
        self, mock_dep_detector, mock_cmd_inferrer,
        mock_framework_detector, mock_type_detector,
        localization_result, repo_context, mock_sandbox
    ):
        """Test when error cannot be reproduced."""
        mock_type_detector.return_value.detect.return_value = {
            "project_type": "python",
            "indicators": ["requirements.txt"],
        }
        mock_framework_detector.return_value.detect.return_value = {
            "framework": "pytest",
            "indicators": ["pytest.ini"],
        }
        mock_cmd_inferrer.return_value.infer.return_value = {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": [],
        }
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": False,
            "reason": "no_dependency_file",
            "install_command": None,
        }

        # Tests pass (exit code 0)
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "====== 5 passed in 1.2s ======",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 1.2,
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent.run()

        assert isinstance(result, ReproductionResult)
        assert result.status == "not_reproduced"
        assert result.root_cause is None

    @patch('swe_agent.agents.reproduction.agent.ProjectTypeDetector')
    @patch('swe_agent.agents.reproduction.agent.TestFrameworkDetector')
    @patch('swe_agent.agents.reproduction.agent.TestCommandInferrer')
    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    def test_run_with_retry_strategy(
        self, mock_dep_detector, mock_cmd_inferrer,
        mock_framework_detector, mock_type_detector,
        localization_result, repo_context, mock_sandbox
    ):
        """Test retry strategy with multiple attempts."""
        mock_type_detector.return_value.detect.return_value = {
            "project_type": "python",
            "indicators": ["requirements.txt"],
        }
        mock_framework_detector.return_value.detect.return_value = {
            "framework": "pytest",
            "indicators": ["pytest.ini"],
        }
        mock_cmd_inferrer.return_value.infer.return_value = {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": [],
        }
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": False,
            "reason": "no_dependency_file",
            "install_command": None,
        }

        # First attempt fails with command not found, second succeeds
        mock_sandbox.execute.side_effect = [
            {
                "status": "error",
                "stdout": "",
                "stderr": "pytest: command not found",
                "exit_code": 127,
                "execution_time": 0.1,
            },
            {
                "status": "success",
                "stdout": "test FAILED\nAssertionError",
                "stderr": "",
                "exit_code": 1,
                "execution_time": 2.0,
            },
        ]

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent.run()

        assert result.attempts >= 1
        assert mock_sandbox.execute.call_count >= 1

    @patch('swe_agent.agents.reproduction.agent.ProjectTypeDetector')
    @patch('swe_agent.agents.reproduction.agent.TestFrameworkDetector')
    @patch('swe_agent.agents.reproduction.agent.TestCommandInferrer')
    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    def test_run_execution_time_constraint(
        self, mock_dep_detector, mock_cmd_inferrer,
        mock_framework_detector, mock_type_detector,
        localization_result, repo_context, mock_sandbox
    ):
        """Test that execution completes within time constraint (< 8 minutes simulated)."""
        mock_type_detector.return_value.detect.return_value = {
            "project_type": "python",
            "indicators": ["requirements.txt"],
        }
        mock_framework_detector.return_value.detect.return_value = {
            "framework": "pytest",
            "indicators": ["pytest.ini"],
        }
        mock_cmd_inferrer.return_value.infer.return_value = {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": [],
        }
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": False,
            "reason": "no_dependency_file",
            "install_command": None,
        }

        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "test FAILED",
            "stderr": "",
            "exit_code": 1,
            "execution_time": 2.0,
        }

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent.run()

        # Simulated execution should be fast (< 8 minutes = 480 seconds)
        assert result.execution_time < 480

    @patch('swe_agent.agents.reproduction.agent.ProjectTypeDetector')
    @patch('swe_agent.agents.reproduction.agent.TestFrameworkDetector')
    @patch('swe_agent.agents.reproduction.agent.TestCommandInferrer')
    @patch('swe_agent.agents.reproduction.agent.DependencyInstallDetector')
    def test_run_with_dependency_installation(
        self, mock_dep_detector, mock_cmd_inferrer,
        mock_framework_detector, mock_type_detector,
        localization_result, repo_context, mock_sandbox
    ):
        """Test flow with dependency installation."""
        mock_type_detector.return_value.detect.return_value = {
            "project_type": "python",
            "indicators": ["requirements.txt"],
        }
        mock_framework_detector.return_value.detect.return_value = {
            "framework": "pytest",
            "indicators": ["pytest.ini"],
        }
        mock_cmd_inferrer.return_value.infer.return_value = {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": [],
        }
        mock_dep_detector.return_value.needs_install.return_value = {
            "needs_install": True,
            "reason": "dependencies_file_exists",
            "install_command": "pip install -r requirements.txt",
        }

        # First call: install dependencies, second call: run tests
        mock_sandbox.execute.side_effect = [
            {
                "status": "success",
                "stdout": "Successfully installed",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 10.0,
            },
            {
                "status": "success",
                "stdout": "test FAILED",
                "stderr": "",
                "exit_code": 1,
                "execution_time": 2.0,
            },
        ]

        agent = ReproductionAgent(localization_result, repo_context, mock_sandbox)
        result = agent.run()

        assert mock_sandbox.execute.call_count >= 2
        assert result.status == "reproduced"
