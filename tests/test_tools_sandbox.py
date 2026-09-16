"""Tests for sandbox execution tools.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Tests for Task 2.3: Sandbox Execution Tools
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from swe_agent.tools.base import ToolResult
from swe_agent.tools.sandbox_exec import (
    InstallDepsTool,
    RunCommandTool,
    RunTestTool,
)


class TestRunCommandTool:
    """Tests for RunCommandTool."""

    def test_tool_metadata(self):
        """Test tool has correct name and description."""
        mock_sandbox = Mock()
        tool = RunCommandTool(sandbox=mock_sandbox)

        assert tool.name == "run_command"
        assert "execute" in tool.description.lower()
        assert "command" in tool.parameters_schema["properties"]
        assert "timeout" in tool.parameters_schema["properties"]

    def test_simple_echo_command(self):
        """Test simple echo command execution."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "hello world\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 0.1,
        }

        tool = RunCommandTool(sandbox=mock_sandbox)
        result = tool.execute(command="echo 'hello world'")

        assert result.error is None
        assert "hello world" in result.output
        assert result.truncated is False
        mock_sandbox.execute.assert_called_once_with("echo 'hello world'", timeout=300)

    def test_ls_command(self):
        """Test ls command execution."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "file1.txt\nfile2.py\ndir1/\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 0.05,
        }

        tool = RunCommandTool(sandbox=mock_sandbox)
        result = tool.execute(command="ls -la")

        assert result.error is None
        assert "file1.txt" in result.output
        assert "file2.py" in result.output
        assert result.truncated is False

    def test_command_with_error(self):
        """Test command that returns error."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "error",
            "stdout": "",
            "stderr": "command not found: invalid_cmd",
            "exit_code": 127,
            "execution_time": 0.02,
        }

        tool = RunCommandTool(sandbox=mock_sandbox)
        result = tool.execute(command="invalid_cmd")

        assert result.error is not None
        assert "command not found" in result.error.lower()
        assert result.metadata["exit_code"] == 127

    def test_timeout_mechanism(self):
        """Test command timeout handling."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "timeout",
            "stdout": "",
            "stderr": "Command exceeded timeout of 5s",
            "exit_code": -1,
            "execution_time": 5.1,
        }

        tool = RunCommandTool(sandbox=mock_sandbox)
        result = tool.execute(command="sleep 10", timeout=5)

        assert result.error is not None
        assert "timed out" in result.error.lower()
        mock_sandbox.execute.assert_called_once_with("sleep 10", timeout=5)

    def test_custom_timeout(self):
        """Test command with custom timeout."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "done\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 2.0,
        }

        tool = RunCommandTool(sandbox=mock_sandbox)
        result = tool.execute(command="some_command", timeout=10)

        mock_sandbox.execute.assert_called_once_with("some_command", timeout=10)

    def test_output_truncation(self):
        """Test output truncation for large output (5KB limit for sandbox tools)."""
        mock_sandbox = Mock()
        large_output = "x" * 10000  # 10KB output
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": large_output,
            "stderr": "",
            "exit_code": 0,
            "execution_time": 0.5,
        }

        tool = RunCommandTool(sandbox=mock_sandbox)
        tool.max_output_size = 5 * 1024  # 5KB limit
        result = tool.execute(command="cat large_file.txt")

        assert result.truncated is True
        assert len(result.output) < len(large_output)


class TestRunTestTool:
    """Tests for RunTestTool."""

    def test_tool_metadata(self):
        """Test tool has correct name and description."""
        mock_sandbox = Mock()
        tool = RunTestTool(sandbox=mock_sandbox, work_dir="/workspace")

        assert tool.name == "run_test"
        assert "test" in tool.description.lower()
        assert "test_path" in tool.parameters_schema["properties"]

    def test_detect_pytest_framework(self):
        """Test pytest framework detection."""
        mock_sandbox = Mock()

        # Create temp dir with pytest.ini
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pytest.ini").touch()

            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            framework = tool._detect_test_framework()

            assert framework == "pytest"

    def test_detect_jest_framework(self):
        """Test jest framework detection (Node.js)."""
        mock_sandbox = Mock()

        # Create temp dir with package.json
        with tempfile.TemporaryDirectory() as tmpdir:
            package_json = Path(tmpdir) / "package.json"
            package_json.write_text(json.dumps({
                "scripts": {"test": "jest"}
            }))

            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            framework = tool._detect_test_framework()

            assert framework == "jest"

    def test_detect_junit_framework(self):
        """Test junit framework detection (Java/Maven)."""
        mock_sandbox = Mock()

        # Create temp dir with pom.xml
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pom.xml").touch()

            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            framework = tool._detect_test_framework()

            assert framework == "junit"

    def test_run_pytest_tests(self):
        """Test running pytest tests."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "===== 5 passed in 2.3s =====\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 2.5,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pytest.ini").touch()

            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute(test_path="tests/")

            assert result.error is None
            assert "5 passed" in result.output
            mock_sandbox.execute.assert_called_once()
            call_args = mock_sandbox.execute.call_args[0]
            assert "pytest" in call_args[0]

    def test_run_jest_tests(self):
        """Test running jest tests."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "Test Suites: 3 passed, 3 total\nTests: 12 passed, 12 total\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 5.2,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            package_json = Path(tmpdir) / "package.json"
            package_json.write_text(json.dumps({"scripts": {"test": "jest"}}))

            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute(test_path="src/")

            assert result.error is None
            assert "12 passed" in result.output
            call_args = mock_sandbox.execute.call_args[0]
            assert "npm test" in call_args[0]

    def test_run_junit_tests(self):
        """Test running junit tests."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "[INFO] Tests run: 8, Failures: 0, Errors: 0, Skipped: 0\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 10.5,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pom.xml").touch()

            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute(test_path="src/test/")

            assert result.error is None
            assert "Tests run: 8" in result.output
            call_args = mock_sandbox.execute.call_args[0]
            assert "mvn test" in call_args[0]

    def test_test_failure(self):
        """Test handling of test failures."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "error",
            "stdout": "===== 3 passed, 2 failed in 1.5s =====\n",
            "stderr": "FAILED tests/test_module.py::test_function - AssertionError",
            "exit_code": 1,
            "execution_time": 1.8,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pytest.ini").touch()

            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute(test_path="tests/test_module.py")

            assert result.error is not None
            assert "failed" in result.error.lower() or "failed" in result.output.lower()

    def test_no_framework_detected(self):
        """Test behavior when no test framework is detected."""
        mock_sandbox = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = RunTestTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute(test_path="tests/")

            assert result.error is not None
            assert "no test framework" in result.error.lower()


class TestInstallDepsTool:
    """Tests for InstallDepsTool."""

    def test_tool_metadata(self):
        """Test tool has correct name and description."""
        mock_sandbox = Mock()
        tool = InstallDepsTool(sandbox=mock_sandbox, work_dir="/workspace")

        assert tool.name == "install_deps"
        assert "install" in tool.description.lower()
        assert "dependencies" in tool.description.lower()

    def test_detect_python_project(self):
        """Test Python project detection (requirements.txt)."""
        mock_sandbox = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").touch()

            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            project_type = tool._detect_project_type()

            assert project_type == "python"

    def test_detect_nodejs_project(self):
        """Test Node.js project detection (package.json)."""
        mock_sandbox = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "package.json").touch()

            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            project_type = tool._detect_project_type()

            assert project_type == "nodejs"

    def test_detect_java_project(self):
        """Test Java project detection (pom.xml)."""
        mock_sandbox = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pom.xml").touch()

            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            project_type = tool._detect_project_type()

            assert project_type == "java"

    def test_install_python_dependencies(self):
        """Test installing Python dependencies."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "Successfully installed package1-1.0.0 package2-2.1.0\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 15.3,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").touch()

            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute()

            assert result.error is None
            assert "Successfully installed" in result.output
            call_args = mock_sandbox.execute.call_args[0]
            assert "pip install" in call_args[0]
            assert "requirements.txt" in call_args[0]

    def test_install_nodejs_dependencies(self):
        """Test installing Node.js dependencies."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "added 245 packages in 8s\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 8.5,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "package.json").touch()

            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute()

            assert result.error is None
            assert "added" in result.output and "packages" in result.output
            call_args = mock_sandbox.execute.call_args[0]
            assert "npm install" in call_args[0]

    def test_install_java_dependencies(self):
        """Test installing Java dependencies."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "success",
            "stdout": "[INFO] BUILD SUCCESS\n[INFO] Total time: 45.2 s\n",
            "stderr": "",
            "exit_code": 0,
            "execution_time": 45.5,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "pom.xml").touch()

            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute()

            assert result.error is None
            assert "BUILD SUCCESS" in result.output
            call_args = mock_sandbox.execute.call_args[0]
            assert "mvn" in call_args[0]

    def test_install_failure(self):
        """Test handling of installation failure."""
        mock_sandbox = Mock()
        mock_sandbox.execute.return_value = {
            "status": "error",
            "stdout": "",
            "stderr": "ERROR: Could not find a version that satisfies the requirement invalid-package",
            "exit_code": 1,
            "execution_time": 2.1,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "requirements.txt").touch()

            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute()

            assert result.error is not None
            assert "could not find" in result.error.lower()

    def test_no_project_type_detected(self):
        """Test behavior when no project type is detected."""
        mock_sandbox = Mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = InstallDepsTool(sandbox=mock_sandbox, work_dir=tmpdir)
            result = tool.execute()

            assert result.error is not None
            assert "no dependency" in result.error.lower() or "not detected" in result.error.lower()
