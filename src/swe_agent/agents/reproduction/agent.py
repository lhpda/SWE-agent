"""ReproductionAgent for reproducing errors in isolated sandbox environment.

Task 4.3: ReproductionAgent implementation
Orchestrates error reproduction by detecting project type, installing dependencies,
running tests, and analyzing results.
"""

import time
from typing import Dict, List, Any, Optional

from swe_agent.types import LocalizationResult, RepositoryContext, ReproductionResult
from swe_agent.sandbox import DockerSandbox
from swe_agent.agents.reproduction.detector import (
    ProjectTypeDetector,
    TestFrameworkDetector,
    TestCommandInferrer,
    DependencyInstallDetector,
)
from swe_agent.agents.reproduction.log_analyzer import LogAnalyzer
from swe_agent.logging import get_logger

logger = get_logger(__name__)


class ReproductionAgent:
    """Agent responsible for reproducing errors in a sandboxed environment.

    Workflow:
    1. Detect project type and test framework
    2. Install dependencies if needed
    3. Run tests with retry strategy
    4. Analyze results to extract root cause
    """

    # Fallback test commands to try if primary command fails
    FALLBACK_COMMANDS = {
        "pytest": ["python -m pytest", "python -m unittest discover"],
        "unittest": ["python -m unittest discover"],
        "jest": ["npm test", "npx jest"],
        "mocha": ["npm test", "npx mocha"],
    }

    def __init__(
        self,
        localization_result: LocalizationResult,
        repo_context: RepositoryContext,
        sandbox: DockerSandbox,
        max_attempts: int = 5,
    ):
        """Initialize ReproductionAgent.

        Args:
            localization_result: Result from localization stage
            repo_context: Repository context information
            sandbox: DockerSandbox instance for isolated execution
            max_attempts: Maximum number of retry attempts (default: 5)
        """
        self.localization_result = localization_result
        self.repo_context = repo_context
        self.sandbox = sandbox
        self.max_attempts = max_attempts

        self.project_info: Optional[Dict[str, Any]] = None
        self.attempts_made = 0

        logger.info(
            "reproduction_agent_initialized",
            session_id=sandbox.session_id,
            max_attempts=max_attempts,
        )

    def run(self) -> ReproductionResult:
        """Execute the reproduction workflow.

        Returns:
            ReproductionResult with reproduction status and details
        """
        start_time = time.time()

        logger.info("reproduction_agent_starting", session_id=self.sandbox.session_id)

        try:
            # Step 1: Detect project type and test framework
            self.project_info = self._detect_project()
            logger.info(
                "project_detected",
                project_type=self.project_info["project_type"],
                framework=self.project_info["framework"],
            )

            # Step 2: Install dependencies if needed
            install_result = self._install_dependencies()
            if install_result.get("error"):
                logger.warning(
                    "dependency_installation_failed",
                    error=install_result["error"],
                )
                # Continue anyway - tests might still work

            # Step 3: Run tests with retry strategy
            test_result = self._run_tests_with_retry()

            if test_result["status"] == "error" and self.attempts_made >= self.max_attempts:
                # Failed after all retries
                execution_time = time.time() - start_time
                return ReproductionResult(
                    status="error",
                    root_cause=None,
                    error_details={
                        "error_type": "ExecutionError",
                        "message": "Failed to execute tests after maximum retries",
                        "stack_trace": [],
                        "log": test_result.get("stderr", ""),
                    },
                    test_command=test_result.get("command", "unknown"),
                    test_output=test_result.get("stderr", "")[:5120],
                    execution_time=execution_time,
                    attempts=self.attempts_made,
                )

            # Step 4: Analyze results
            analysis = self._analyze_results(
                test_result["output"],
                test_result["exit_code"],
            )

            execution_time = time.time() - start_time

            # Truncate output to 5KB
            truncated_output = test_result["output"][:5120]

            # Build ReproductionResult
            result = ReproductionResult(
                status=analysis["status"],
                root_cause=analysis.get("root_cause"),
                error_details=analysis.get("error_details"),
                test_command=test_result["command"],
                test_output=truncated_output,
                execution_time=execution_time,
                attempts=self.attempts_made,
            )

            logger.info(
                "reproduction_agent_completed",
                status=result.status,
                execution_time=execution_time,
                attempts=self.attempts_made,
            )

            return result

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "reproduction_agent_error",
                error=str(e),
                execution_time=execution_time,
            )

            return ReproductionResult(
                status="error",
                root_cause=None,
                error_details={
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "stack_trace": [],
                    "log": "",
                },
                test_command="unknown",
                test_output=str(e)[:5120],
                execution_time=execution_time,
                attempts=self.attempts_made,
            )

    def _detect_project(self) -> Dict[str, Any]:
        """Detect project type and test framework.

        Returns:
            Dict with project_type and framework information
        """
        # Detect project type
        type_detector = ProjectTypeDetector(self.repo_context.path)
        type_result = type_detector.detect()

        project_type = type_result["project_type"]

        # Detect test framework
        framework_detector = TestFrameworkDetector(
            self.repo_context.path,
            project_type,
        )
        framework_result = framework_detector.detect()

        return {
            "project_type": project_type,
            "framework": framework_result["framework"],
            "type_indicators": type_result["indicators"],
            "framework_indicators": framework_result["indicators"],
        }

    def _install_dependencies(self) -> Dict[str, Any]:
        """Install dependencies if needed.

        Returns:
            Dict with installation status and details
        """
        if not self.project_info:
            return {"installed": False, "reason": "project_not_detected"}

        # Check if installation is needed
        dep_detector = DependencyInstallDetector(
            self.repo_context.path,
            self.project_info["project_type"],
        )
        install_info = dep_detector.needs_install()

        if not install_info["needs_install"]:
            logger.debug(
                "dependencies_not_needed",
                reason=install_info["reason"],
            )
            return {
                "installed": False,
                "reason": install_info["reason"],
            }

        # Install dependencies
        install_cmd = install_info["install_command"]
        logger.info("installing_dependencies", command=install_cmd)

        try:
            result = self.sandbox.execute(
                install_cmd,
                timeout=300,  # 5 minutes for installation
            )

            if result["status"] == "success" and result["exit_code"] == 0:
                logger.info(
                    "dependencies_installed",
                    execution_time=result["execution_time"],
                )
                return {
                    "installed": True,
                    "execution_time": result["execution_time"],
                    "output": result["stdout"],
                }
            else:
                logger.warning(
                    "dependency_installation_failed",
                    exit_code=result["exit_code"],
                    stderr=result["stderr"][:500],
                )
                return {
                    "installed": False,
                    "error": result["stderr"],
                    "exit_code": result["exit_code"],
                }

        except Exception as e:
            logger.error("dependency_installation_error", error=str(e))
            return {
                "installed": False,
                "error": str(e),
            }

    def _run_tests_with_retry(self) -> Dict[str, Any]:
        """Run tests with retry strategy using fallback commands.

        Returns:
            Dict with test execution results
        """
        if not self.project_info:
            return {
                "status": "error",
                "output": "Project type not detected",
                "exit_code": -1,
                "command": "unknown",
            }

        framework = self.project_info["framework"]

        # Get primary test command
        cmd_inferrer = TestCommandInferrer(
            self.repo_context.path,
            self.project_info["project_type"],
            framework,
        )
        cmd_info = cmd_inferrer.infer()
        primary_command = cmd_info["command"]

        # Build list of commands to try
        commands_to_try = [primary_command]

        # Add fallback commands
        if framework in self.FALLBACK_COMMANDS:
            for fallback in self.FALLBACK_COMMANDS[framework]:
                if fallback not in commands_to_try:
                    commands_to_try.append(fallback)

        # Try each command
        for attempt, command in enumerate(commands_to_try, 1):
            if attempt > self.max_attempts:
                break

            self.attempts_made = attempt

            logger.debug(
                "running_test_command",
                attempt=attempt,
                command=command,
            )

            result = self._run_tests(command)

            # Check if command executed successfully (not command not found)
            if result["status"] != "error" or result["exit_code"] != 127:
                # Command executed (even if tests failed)
                return {
                    "status": "success",
                    "output": result["stdout"] + result["stderr"],
                    "exit_code": result["exit_code"],
                    "command": command,
                    "execution_time": result["execution_time"],
                }

            logger.debug(
                "test_command_failed",
                command=command,
                exit_code=result["exit_code"],
            )

        # All commands failed
        return {
            "status": "error",
            "output": "All test commands failed",
            "exit_code": -1,
            "command": primary_command,
        }

    def _run_tests(self, command: str) -> Dict[str, Any]:
        """Run tests using the specified command.

        Args:
            command: Test command to execute

        Returns:
            Dict with execution results
        """
        try:
            result = self.sandbox.execute(
                command,
                timeout=420,  # 7 minutes for test execution
            )

            logger.debug(
                "test_execution_completed",
                exit_code=result["exit_code"],
                execution_time=result["execution_time"],
            )

            return result

        except Exception as e:
            logger.error("test_execution_error", error=str(e))
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": 0,
            }

    def _analyze_results(self, test_output: str, exit_code: int) -> Dict[str, Any]:
        """Analyze test results to extract error information.

        Args:
            test_output: Raw test output
            exit_code: Test command exit code

        Returns:
            Dict with analysis results including status and error details
        """
        # If exit code is 0, tests passed (not reproduced)
        if exit_code == 0:
            logger.info("error_not_reproduced", reason="tests_passed")
            return {
                "status": "not_reproduced",
                "root_cause": None,
                "error_details": None,
            }

        # Parse log to extract error information
        analyzer = LogAnalyzer(test_output)

        error_type = analyzer.identify_error_type()
        root_cause_info = analyzer.extract_root_cause()
        stack_traces = analyzer.extract_stack_traces()
        truncated_log = analyzer.truncate_log(max_lines=200)

        # Extract error message from output
        error_message = self._extract_error_message(test_output, error_type)

        # Build root cause dict
        root_cause = None
        if root_cause_info["file"]:
            root_cause = {
                "file": root_cause_info["file"],
                "line": root_cause_info["line"],
                "function": None,  # Not extracted by current analyzer
                "explanation": f"{error_type} occurred at {root_cause_info['file']}:{root_cause_info['line']}",
            }

        # Build error details
        error_details = {
            "error_type": error_type,
            "message": error_message,
            "stack_trace": stack_traces,
            "log": truncated_log,
        }

        logger.info(
            "error_reproduced",
            error_type=error_type,
            root_cause_file=root_cause_info["file"],
            root_cause_line=root_cause_info["line"],
        )

        return {
            "status": "reproduced",
            "root_cause": root_cause,
            "error_details": error_details,
        }

    def _extract_error_message(self, output: str, error_type: str) -> str:
        """Extract error message from test output.

        Args:
            output: Test output
            error_type: Identified error type

        Returns:
            Error message string
        """
        lines = output.split("\n")

        # Look for lines containing the error type
        for i, line in enumerate(lines):
            if error_type in line and ":" in line:
                # Extract message after error type
                parts = line.split(":", 1)
                if len(parts) > 1:
                    return parts[1].strip()

        # Fallback: return first non-empty line with error type
        for line in lines:
            if error_type in line and line.strip():
                return line.strip()

        return "Error details not available"
