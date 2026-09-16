"""Sandbox execution tools for running commands, tests, and installing dependencies.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Implements Task 2.3: Sandbox Execution Tools
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from swe_agent.logging import get_logger
from swe_agent.tools.base import Tool, ToolResult

logger = get_logger(__name__)


class RunCommandTool(Tool):
    """Execute commands in the sandbox environment.

    This tool runs arbitrary shell commands within the isolated Docker sandbox,
    with configurable timeout and automatic output truncation.
    """

    def __init__(self, sandbox):
        """Initialize RunCommandTool.

        Args:
            sandbox: DockerSandbox instance for command execution
        """
        self.sandbox = sandbox
        self.name = "run_command"
        self.description = "Execute a shell command in the sandbox environment"
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 300)",
                    "default": 300
                }
            },
            "required": ["command"]
        }
        # 5KB limit for sandbox tool output (as per Task 2.3 requirements)
        self.max_output_size = 5 * 1024

    def execute(self, command: str, timeout: int = 300, **kwargs: Any) -> ToolResult:
        """Execute a shell command in the sandbox.

        Args:
            command: Shell command to execute
            timeout: Timeout in seconds (default: 300)
            **kwargs: Additional parameters (ignored)

        Returns:
            ToolResult with command output or error
        """
        logger.info("run_command_execute", command=command[:100], timeout=timeout)

        try:
            # Execute command in sandbox
            result = self.sandbox.execute(command, timeout=timeout)

            status = result["status"]
            stdout = result["stdout"]
            stderr = result["stderr"]
            exit_code = result["exit_code"]
            execution_time = result["execution_time"]

            # Handle timeout
            if status == "timeout":
                return ToolResult(
                    output="",
                    truncated=False,
                    error=f"Command timed out after {timeout}s",
                    metadata={
                        "exit_code": exit_code,
                        "execution_time": execution_time
                    }
                )

            # Handle execution error
            if status == "error":
                error_msg = stderr if stderr else "Command execution failed"
                return ToolResult(
                    output=stdout,
                    truncated=False,
                    error=error_msg,
                    metadata={
                        "exit_code": exit_code,
                        "execution_time": execution_time
                    }
                )

            # Success - combine stdout and stderr
            output = stdout
            if stderr:
                output += f"\n[stderr]\n{stderr}"

            # Apply truncation
            truncated_result = self.truncate_output(output)
            truncated_result.metadata.update({
                "exit_code": exit_code,
                "execution_time": execution_time
            })

            return truncated_result

        except Exception as e:
            logger.error("run_command_failed", command=command[:100], error=str(e))
            return ToolResult(
                output="",
                truncated=False,
                error=f"Command execution failed: {str(e)}"
            )


class RunTestTool(Tool):
    """Run tests with automatic framework detection.

    This tool automatically detects the test framework (pytest, jest, junit)
    and runs tests with appropriate commands.
    """

    def __init__(self, sandbox, work_dir: str):
        """Initialize RunTestTool.

        Args:
            sandbox: DockerSandbox instance for command execution
            work_dir: Working directory path for framework detection
        """
        self.sandbox = sandbox
        self.work_dir = Path(work_dir)
        self.name = "run_test"
        self.description = "Run tests with automatic framework detection (pytest/jest/junit)"
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "test_path": {
                    "type": "string",
                    "description": "Path to test file or directory",
                    "default": ""
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 600)",
                    "default": 600
                }
            },
            "required": []
        }
        # 5KB limit for test output
        self.max_output_size = 5 * 1024

    def _detect_test_framework(self) -> Optional[str]:
        """Detect test framework from project files.

        Returns:
            "pytest", "jest", "junit", or None if not detected
        """
        # Check for pytest (pytest.ini, setup.cfg with pytest, etc.)
        if (self.work_dir / "pytest.ini").exists():
            return "pytest"
        if (self.work_dir / "setup.cfg").exists():
            # Could check for [tool:pytest] section, but pytest.ini is more reliable
            pass

        # Check for jest (package.json with jest in test script)
        package_json = self.work_dir / "package.json"
        if package_json.exists():
            try:
                with open(package_json) as f:
                    data = json.load(f)
                    if "scripts" in data and "test" in data["scripts"]:
                        test_script = data["scripts"]["test"]
                        if "jest" in test_script:
                            return "jest"
                        # Generic npm test
                        return "jest"
            except Exception as e:
                logger.warning("package_json_parse_failed", error=str(e))

        # Check for junit (pom.xml for Maven)
        if (self.work_dir / "pom.xml").exists():
            return "junit"

        return None

    def execute(self, test_path: str = "", timeout: int = 600, **kwargs: Any) -> ToolResult:
        """Run tests with automatic framework detection.

        Args:
            test_path: Path to test file or directory (relative to workspace)
            timeout: Timeout in seconds (default: 600)
            **kwargs: Additional parameters (ignored)

        Returns:
            ToolResult with test output or error
        """
        logger.info("run_test_execute", test_path=test_path, timeout=timeout)

        # Detect framework
        framework = self._detect_test_framework()

        if not framework:
            return ToolResult(
                output="",
                truncated=False,
                error="No test framework detected. Supported: pytest, jest, junit"
            )

        # Build test command based on framework
        if framework == "pytest":
            command = f"pytest {test_path}" if test_path else "pytest"
        elif framework == "jest":
            command = f"npm test -- {test_path}" if test_path else "npm test"
        elif framework == "junit":
            command = "mvn test"
            if test_path:
                # Maven test filtering
                command += f" -Dtest={test_path}"
        else:
            return ToolResult(
                output="",
                truncated=False,
                error=f"Unsupported test framework: {framework}"
            )

        logger.info("run_test_command", framework=framework, command=command)

        try:
            # Execute test command
            result = self.sandbox.execute(command, timeout=timeout)

            status = result["status"]
            stdout = result["stdout"]
            stderr = result["stderr"]
            exit_code = result["exit_code"]
            execution_time = result["execution_time"]

            # Handle timeout
            if status == "timeout":
                return ToolResult(
                    output="",
                    truncated=False,
                    error=f"Tests timed out after {timeout}s",
                    metadata={
                        "framework": framework,
                        "exit_code": exit_code,
                        "execution_time": execution_time
                    }
                )

            # Combine output
            output = stdout
            if stderr:
                output += f"\n[stderr]\n{stderr}"

            # Handle test failures (non-zero exit code)
            error_msg = None
            if status == "error":
                error_msg = f"Tests failed (exit code: {exit_code})"

            # Apply truncation
            truncated_result = self.truncate_output(output)
            truncated_result.error = error_msg
            truncated_result.metadata.update({
                "framework": framework,
                "exit_code": exit_code,
                "execution_time": execution_time
            })

            return truncated_result

        except Exception as e:
            logger.error("run_test_failed", framework=framework, error=str(e))
            return ToolResult(
                output="",
                truncated=False,
                error=f"Test execution failed: {str(e)}",
                metadata={"framework": framework}
            )


class InstallDepsTool(Tool):
    """Install project dependencies with automatic package manager detection.

    This tool detects the project type (Python, Node.js, Java) and runs
    the appropriate dependency installation command.
    """

    def __init__(self, sandbox, work_dir: str):
        """Initialize InstallDepsTool.

        Args:
            sandbox: DockerSandbox instance for command execution
            work_dir: Working directory path for project type detection
        """
        self.sandbox = sandbox
        self.work_dir = Path(work_dir)
        self.name = "install_deps"
        self.description = "Install project dependencies (pip/npm/maven) with automatic detection"
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 600)",
                    "default": 600
                }
            },
            "required": []
        }
        # 5KB limit for installation output
        self.max_output_size = 5 * 1024

    def _detect_project_type(self) -> Optional[str]:
        """Detect project type from dependency files.

        Returns:
            "python", "nodejs", "java", or None if not detected
        """
        # Check for Python (requirements.txt, setup.py, pyproject.toml)
        if (self.work_dir / "requirements.txt").exists():
            return "python"
        if (self.work_dir / "setup.py").exists():
            return "python"
        if (self.work_dir / "pyproject.toml").exists():
            return "python"

        # Check for Node.js (package.json)
        if (self.work_dir / "package.json").exists():
            return "nodejs"

        # Check for Java (pom.xml for Maven)
        if (self.work_dir / "pom.xml").exists():
            return "java"

        return None

    def execute(self, timeout: int = 600, **kwargs: Any) -> ToolResult:
        """Install dependencies based on detected project type.

        Args:
            timeout: Timeout in seconds (default: 600)
            **kwargs: Additional parameters (ignored)

        Returns:
            ToolResult with installation output or error
        """
        logger.info("install_deps_execute", timeout=timeout)

        # Detect project type
        project_type = self._detect_project_type()

        if not project_type:
            return ToolResult(
                output="",
                truncated=False,
                error="No dependency file detected. Supported: requirements.txt, package.json, pom.xml"
            )

        # Build installation command based on project type
        if project_type == "python":
            # Check which file exists
            if (self.work_dir / "requirements.txt").exists():
                command = "pip install -r requirements.txt"
            else:
                command = "pip install -e ."
        elif project_type == "nodejs":
            command = "npm install"
        elif project_type == "java":
            command = "mvn dependency:resolve"
        else:
            return ToolResult(
                output="",
                truncated=False,
                error=f"Unsupported project type: {project_type}"
            )

        logger.info("install_deps_command", project_type=project_type, command=command)

        try:
            # Execute installation command
            result = self.sandbox.execute(command, timeout=timeout)

            status = result["status"]
            stdout = result["stdout"]
            stderr = result["stderr"]
            exit_code = result["exit_code"]
            execution_time = result["execution_time"]

            # Handle timeout
            if status == "timeout":
                return ToolResult(
                    output="",
                    truncated=False,
                    error=f"Installation timed out after {timeout}s",
                    metadata={
                        "project_type": project_type,
                        "exit_code": exit_code,
                        "execution_time": execution_time
                    }
                )

            # Combine output
            output = stdout
            if stderr:
                output += f"\n[stderr]\n{stderr}"

            # Handle installation errors
            error_msg = None
            if status == "error":
                error_msg = stderr if stderr else f"Installation failed (exit code: {exit_code})"

            # Apply truncation
            truncated_result = self.truncate_output(output)
            truncated_result.error = error_msg
            truncated_result.metadata.update({
                "project_type": project_type,
                "exit_code": exit_code,
                "execution_time": execution_time
            })

            return truncated_result

        except Exception as e:
            logger.error("install_deps_failed", project_type=project_type, error=str(e))
            return ToolResult(
                output="",
                truncated=False,
                error=f"Dependency installation failed: {str(e)}",
                metadata={"project_type": project_type}
            )
