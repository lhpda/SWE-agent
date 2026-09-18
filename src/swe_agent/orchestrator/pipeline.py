"""Pipeline orchestrator for coordinating all agents.

Task 7.4: PipelineOrchestrator implementation
Coordinates LocalizationAgent, ReproductionAgent, PatchGeneratorAgent, and ValidationAgent
to execute the full bug-fixing pipeline with state management, retries, and error handling.
"""

import time
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from swe_agent.agents.localization.agent import LocalizationAgent
from swe_agent.agents.reproduction.agent import ReproductionAgent
from swe_agent.agents.patch.agent import PatchGeneratorAgent
from swe_agent.agents.validation.agent import ValidationAgent
from swe_agent.logging import get_logger
from swe_agent.orchestrator.error_handler import ErrorHandler
from swe_agent.orchestrator.retry import RetryStrategy
from swe_agent.orchestrator.state_machine import State, StateMachine
from swe_agent.sandbox.docker import DockerSandbox
from swe_agent.storage import StateStore
from swe_agent.config import Config, load_config
from swe_agent.types import (
    ErrorInfo,
    IssueContext,
    LocalizationResult,
    PatchResult,
    PipelineResult,
    PipelineState,
    ReproductionResult,
    RepositoryContext,
    StageStatus,
    ValidationResult,
)

logger = get_logger(__name__)

# Global timeout: 30 minutes (1800 seconds)
DEFAULT_GLOBAL_TIMEOUT = 1800


class PipelineOrchestrator:
    """Orchestrates the full bug-fixing pipeline.

    Coordinates all agents through the pipeline stages:
    1. Localization: Find bug location
    2. Reproduction: Reproduce the bug
    3. Patch Generation: Generate fix candidates
    4. Validation: Validate the fix

    Features:
    - State management with StateMachine
    - Retry logic with RetryStrategy
    - Error handling with ErrorHandler
    - State persistence for resume capability
    - Global timeout enforcement
    """

    def __init__(
        self,
        issue: IssueContext,
        repository: RepositoryContext,
        state_store: StateStore,
        session_id: Optional[str] = None,
        global_timeout: int = DEFAULT_GLOBAL_TIMEOUT,
        sandbox: Optional[DockerSandbox] = None,
        config: Optional[Config] = None,
    ):
        """Initialize pipeline orchestrator.

        Args:
            issue: Issue context information
            repository: Repository context information
            state_store: State store for persistence
            session_id: Optional session ID (generates new if not provided)
            global_timeout: Global timeout in seconds (default: 1800)
            sandbox: Optional sandbox instance (creates new if not provided)
        """
        self.issue = issue
        self.repository = repository
        self.state_store = state_store
        self.session_id = session_id or str(uuid.uuid4())
        self.global_timeout = global_timeout
        self.sandbox = sandbox
        self.config = config or load_config()
        self._owns_sandbox = sandbox is None
        self._workspace = None

        # Create session in state store
        self.state_store.create_session(self.session_id)

        # Initialize state machine
        self.state_machine = StateMachine(
            session_id=self.session_id,
            metadata={
                "issue_id": issue.issue_id,
                "repo_path": repository.path,
                "issue": issue.model_dump(mode="json"),
                "repository": repository.model_dump(mode="json"),
                "config": self.config.model_dump(mode="json"),
                "global_timeout": global_timeout,
            },
        )

        # Initialize retry strategy
        self.retry_strategy = RetryStrategy()

        # Initialize error handler
        self.error_handler = ErrorHandler()

        # Track stage results
        self.stage_results: Dict[str, Any] = {}

        # Track stage attempts
        self.stage_attempts: Dict[str, int] = {
            "LOCALIZING": 0,
            "REPRODUCING": 0,
            "PATCHING": 0,
            "VALIDATING": 0,
        }

        # Track start time for global timeout
        self.start_time: Optional[float] = None
        self.state_machine.save_state(self.state_store)

        logger.info(
            "pipeline_orchestrator_initialized",
            session_id=self.session_id,
            issue_id=issue.issue_id,
            global_timeout=global_timeout,
        )

    def run(self) -> PipelineResult:
        """Execute the full pipeline.

        Returns:
            PipelineResult with final status and results
        """
        self.start_time = time.time()

        logger.info("pipeline_starting", session_id=self.session_id)

        try:
            if self.state_machine.get_current_state() == State.DONE:
                return self._build_success_result()
            if self.state_machine.get_current_state() != State.IDLE:
                # Containers are ephemeral: restart the execution stages from a clean copy.
                # Keep the last localization result and rebuild execution evidence.
                self.state_machine = StateMachine(self.session_id, self.state_machine.metadata)
                self.stage_results.pop("reproduction", None)
                self.stage_results.pop("patch_generation", None)
                self.stage_results.pop("validation", None)
            # Execute pipeline stages
            localization = self.stage_results.get("localization")
            if localization and localization.status in {"success", "partial"}:
                self.state_machine.transition(State.LOCALIZING)
            else:
                self._run_localization()
            self._run_reproduction()
            self._run_patch_generation()
            self._run_validation()

            # Transition to DONE state
            self.state_machine.transition(State.DONE)
            self.state_machine.save_state(self.state_store)

            # Build successful result
            result = self._build_success_result()

            logger.info(
                "pipeline_completed_successfully",
                session_id=self.session_id,
                execution_time=time.time() - self.start_time,
            )

            return result

        except TimeoutError as e:
            logger.error(
                "pipeline_timeout",
                session_id=self.session_id,
                elapsed_time=time.time() - self.start_time,
            )
            return self._build_failure_result(
                error_type="timeout",
                error_message=str(e),
            )

        except Exception as e:
            logger.error(
                "pipeline_failed",
                session_id=self.session_id,
                error=str(e),
                execution_time=time.time() - self.start_time,
            )

            # Transition to FAILED state
            try:
                self.state_machine.transition(State.FAILED)
                self.state_machine.save_state(self.state_store)
            except ValueError:
                # Already in terminal state
                pass

            return self._build_failure_result(
                error_type="agent_error",
                error_message=str(e),
            )

        finally:
            if self._owns_sandbox and self.sandbox is not None:
                self.sandbox.destroy()
                self.sandbox = None

    def _ensure_sandbox(self) -> None:
        if self.sandbox is not None:
            return
        source = Path(self.repository.path).resolve()
        if not source.is_dir():
            raise ValueError(f"Repository directory does not exist: {source}")
        workspace = self.state_store.get_session_path(self.session_id).resolve() / "workspace"
        # Never bind-mount the user's original checkout for patch validation.
        shutil.copytree(
            source,
            workspace,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                ".git",
                ".swe-agent",
                ".venv",
                ".env",
                ".env.*",
                "agent.env",
                "__pycache__",
                ".pytest_cache",
            ),
        )
        self._workspace = workspace
        self.sandbox = DockerSandbox(session_id=self.session_id)
        self.sandbox.create(self.config.docker_image, str(workspace))

    def _check_timeout(self) -> None:
        """Check if global timeout has been exceeded.

        Raises:
            TimeoutError: If global timeout exceeded
        """
        if self.start_time is None:
            return

        elapsed = time.time() - self.start_time
        if elapsed > self.global_timeout:
            raise TimeoutError(
                f"Global timeout of {self.global_timeout}s exceeded (elapsed: {elapsed:.1f}s)"
            )

    def _run_localization(self) -> LocalizationResult:
        """Run localization stage with retry logic.

        Returns:
            LocalizationResult

        Raises:
            Exception: If localization fails after retries
        """
        stage_name = "LOCALIZING"
        logger.info("stage_starting", stage=stage_name, session_id=self.session_id)

        # Transition to LOCALIZING state
        self.state_machine.transition(State.LOCALIZING)
        self.state_machine.save_state(self.state_store)

        while True:
            self._check_timeout()

            attempt = self.stage_attempts[stage_name]

            try:
                # Create and run localization agent
                agent = LocalizationAgent(
                    issue_context=self.issue,
                    repo_context=self.repository,
                )

                result = agent.run()

                # Save result
                self.stage_results["localization"] = result
                self.state_store.save_stage_result(self.session_id, "localization", result)

                # Check if successful
                if result.status in {"success", "partial"} and result.candidates:
                    logger.info(
                        "stage_completed",
                        stage=stage_name,
                        attempt=attempt,
                        candidates=len(result.candidates),
                    )
                    return result

                # Failed but not an exception - check retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_retrying",
                        stage=stage_name,
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise Exception(f"Localization failed with status: {result.status}")

            except Exception as e:
                # Add error to handler
                self.error_handler.add_error(
                    {"type": "agent_error", "message": str(e)},
                    {"stage": stage_name, "attempt": attempt},
                )

                # Check if should retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_error_retrying",
                        stage=stage_name,
                        error=str(e),
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise

    def _run_reproduction(self) -> ReproductionResult:
        """Run reproduction stage with retry logic.

        Returns:
            ReproductionResult

        Raises:
            Exception: If reproduction fails after retries
        """
        stage_name = "REPRODUCING"
        logger.info("stage_starting", stage=stage_name, session_id=self.session_id)

        # Transition to REPRODUCING state
        self.state_machine.transition(State.REPRODUCING)
        self.state_machine.save_state(self.state_store)

        localization_result = self.stage_results.get("localization")
        if not localization_result:
            raise Exception("No localization result available")

        while True:
            self._check_timeout()

            attempt = self.stage_attempts[stage_name]

            try:
                # Create sandbox if needed
                self._ensure_sandbox()

                # Create and run reproduction agent
                agent = ReproductionAgent(
                    localization_result=localization_result,
                    repo_context=self.repository,
                    sandbox=self.sandbox,
                )

                result = agent.run()

                # Save result
                self.stage_results["reproduction"] = result
                self.state_store.save_stage_result(self.session_id, "reproduction", result)

                # Check if successful
                if result.status == "reproduced":
                    logger.info(
                        "stage_completed",
                        stage=stage_name,
                        attempt=attempt,
                    )
                    return result

                # Failed - check retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_retrying",
                        stage=stage_name,
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise Exception(f"Reproduction failed with status: {result.status}")

            except Exception as e:
                # Add error to handler
                self.error_handler.add_error(
                    {"type": "agent_error", "message": str(e)},
                    {"stage": stage_name, "attempt": attempt},
                )

                # Check if should retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_error_retrying",
                        stage=stage_name,
                        error=str(e),
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise

    def _run_patch_generation(self) -> PatchResult:
        """Run patch generation stage with retry logic.

        Returns:
            PatchResult

        Raises:
            Exception: If patch generation fails after retries
        """
        stage_name = "PATCHING"
        logger.info("stage_starting", stage=stage_name, session_id=self.session_id)

        # Transition to PATCHING state
        if self.state_machine.get_current_state() != State.PATCHING:
            self.state_machine.transition(State.PATCHING)
        self.state_machine.save_state(self.state_store)

        localization_result = self.stage_results.get("localization")
        reproduction_result = self.stage_results.get("reproduction")

        if not localization_result or not reproduction_result:
            raise Exception("Missing required stage results")

        while True:
            self._check_timeout()

            attempt = self.stage_attempts[stage_name]

            try:
                # Create and run patch generator agent
                agent = PatchGeneratorAgent(
                    localization_result=localization_result.model_dump(),
                    reproduction_result=reproduction_result.model_dump(),
                    repo_context={**self.repository.model_dump(), "issue_body": self.issue.body},
                    config=self.config,
                )

                result_dict = agent.run()

                # Convert to PatchResult
                result = PatchResult(
                    **{k: v for k, v in result_dict.items() if k in PatchResult.model_fields}
                )

                # Save result
                self.stage_results["patch_generation"] = result
                self.state_store.save_stage_result(self.session_id, "patch_generation", result)

                # Check if successful
                if result.status == "generated" and result.patches:
                    logger.info(
                        "stage_completed",
                        stage=stage_name,
                        attempt=attempt,
                        patches=len(result.patches),
                    )
                    return result

                # Failed - check retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_retrying",
                        stage=stage_name,
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise Exception(
                        f"Patch generation failed: {result_dict.get('error', result.status)}"
                    )

            except PermissionError:
                raise
            except Exception as e:
                # Add error to handler
                self.error_handler.add_error(
                    {"type": "agent_error", "message": str(e)},
                    {"stage": stage_name, "attempt": attempt},
                )

                # Check if should retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_error_retrying",
                        stage=stage_name,
                        error=str(e),
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise

    def _run_validation(self) -> ValidationResult:
        """Run validation stage with retry and rollback logic.

        Returns:
            ValidationResult

        Raises:
            Exception: If validation fails after retries
        """
        stage_name = "VALIDATING"
        logger.info("stage_starting", stage=stage_name, session_id=self.session_id)

        # Transition to VALIDATING state
        self.state_machine.transition(State.VALIDATING)
        self.state_machine.save_state(self.state_store)

        patch_result = self.stage_results.get("patch_generation")

        if not patch_result:
            raise Exception("No patch result available")

        while True:
            self._check_timeout()

            attempt = self.stage_attempts[stage_name]

            try:
                # Ensure sandbox exists
                self._ensure_sandbox()

                # Create and run validation agent
                agent = ValidationAgent(
                    patch_result=patch_result.model_dump(),
                    sandbox=self.sandbox,
                    repo_context={
                        **self.repository.model_dump(),
                        "path": str(self._workspace or self.repository.path),
                        "test_command": self.stage_results["reproduction"].test_command,
                    },
                )

                result_dict = agent.run()

                # Convert to ValidationResult
                result = ValidationResult(
                    **{k: v for k, v in result_dict.items() if k in ValidationResult.model_fields}
                )

                # Save result
                self.stage_results["validation"] = result
                self.state_store.save_stage_result(self.session_id, "validation", result)

                # Check if successful
                if result.status == "passed":
                    logger.info(
                        "stage_completed",
                        stage=stage_name,
                        attempt=attempt,
                    )
                    return result

                # Check if should rollback
                if self.retry_strategy.should_rollback(stage_name, result.model_dump()):
                    if not self.retry_strategy.should_retry(stage_name, attempt):
                        raise RuntimeError("Validation failed after bounded patch retries")
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "validation_regression_rollback",
                        stage=stage_name,
                        patch_id=result.patch_id,
                    )

                    # Rollback to PATCHING
                    self.state_machine.transition(State.PATCHING)
                    self.state_machine.save_state(self.state_store)

                    # Re-run patch generation
                    patch_result = self._run_patch_generation()

                    # Transition back to VALIDATING
                    self.state_machine.transition(State.VALIDATING)
                    self.state_machine.save_state(self.state_store)

                    continue

                # Failed - check retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_retrying",
                        stage=stage_name,
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise Exception(f"Validation failed with status: {result.status}")

            except Exception as e:
                # Add error to handler
                self.error_handler.add_error(
                    {"type": "agent_error", "message": str(e)},
                    {"stage": stage_name, "attempt": attempt},
                )

                # Check if should retry
                if self.retry_strategy.should_retry(stage_name, attempt):
                    self.stage_attempts[stage_name] += 1
                    logger.warning(
                        "stage_error_retrying",
                        stage=stage_name,
                        error=str(e),
                        attempt=self.stage_attempts[stage_name],
                    )
                    continue
                else:
                    raise

    def _build_success_result(self) -> PipelineResult:
        """Build successful pipeline result.

        Returns:
            PipelineResult with success status
        """
        # Get final patch from validation stage
        patch_result = self.stage_results.get("patch_generation")
        final_patch = None
        if patch_result and patch_result.patches:
            final_patch = patch_result.patches[0]

        # Build execution summary
        execution_summary = {
            "total_time": time.time() - self.start_time,
            "stages": {},
        }

        for stage_name, result in self.stage_results.items():
            if hasattr(result, "execution_time"):
                execution_summary["stages"][stage_name] = {
                    "execution_time": result.execution_time,
                    "status": result.status,
                }

        # Get audit log path
        audit_log = str(self.state_store.get_session_path(self.session_id) / "execution_log.jsonl")

        return PipelineResult(
            session_id=self.session_id,
            status="success",
            issue=self.issue,
            repository=self.repository,
            final_patch=final_patch,
            execution_summary=execution_summary,
            audit_log=audit_log,
            error=None,
        )

    def _build_failure_result(self, error_type: str, error_message: str) -> PipelineResult:
        """Build failed pipeline result.

        Args:
            error_type: Type of error
            error_message: Error message

        Returns:
            PipelineResult with failed status
        """
        # Build execution summary
        execution_summary = {
            "total_time": time.time() - self.start_time if self.start_time else 0,
            "stages": {},
        }

        for stage_name, result in self.stage_results.items():
            if hasattr(result, "execution_time"):
                execution_summary["stages"][stage_name] = {
                    "execution_time": result.execution_time,
                    "status": result.status,
                }

        # Get audit log path
        audit_log = str(self.state_store.get_session_path(self.session_id) / "execution_log.jsonl")

        # Build error info
        error_info = ErrorInfo(
            type=error_type,
            message=error_message,
            details=self.error_handler.aggregate_errors(),
            recoverable=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        return PipelineResult(
            session_id=self.session_id,
            status="failed",
            issue=self.issue,
            repository=self.repository,
            final_patch=None,
            execution_summary=execution_summary,
            audit_log=audit_log,
            error=error_info,
        )

    def get_state(self) -> PipelineState:
        """Get current pipeline state.

        Returns:
            PipelineState with current status
        """
        # Map state machine states to pipeline states
        state_map = {
            State.IDLE: "idle",
            State.LOCALIZING: "running",
            State.REPRODUCING: "running",
            State.PATCHING: "running",
            State.VALIDATING: "running",
            State.DONE: "success",
            State.FAILED: "failed",
        }

        current_sm_state = self.state_machine.get_current_state()
        pipeline_status = state_map.get(current_sm_state, "idle")

        # Map current stage
        stage_map = {
            State.LOCALIZING: "localization",
            State.REPRODUCING: "reproduction",
            State.PATCHING: "patch_generation",
            State.VALIDATING: "validation",
        }

        current_stage = stage_map.get(current_sm_state)

        # Build stage statuses
        stages = {}

        # Localization
        loc_result = self.stage_results.get("localization")
        stages["localization"] = self._build_stage_status(
            "localization", loc_result, self.stage_attempts.get("LOCALIZING", 0)
        )

        # Reproduction
        repro_result = self.stage_results.get("reproduction")
        stages["reproduction"] = self._build_stage_status(
            "reproduction", repro_result, self.stage_attempts.get("REPRODUCING", 0)
        )

        # Patch generation
        patch_result = self.stage_results.get("patch_generation")
        stages["patch_generation"] = self._build_stage_status(
            "patch_generation", patch_result, self.stage_attempts.get("PATCHING", 0)
        )

        # Validation
        val_result = self.stage_results.get("validation")
        stages["validation"] = self._build_stage_status(
            "validation", val_result, self.stage_attempts.get("VALIDATING", 0)
        )

        # Build error info if failed
        error_info = None
        if current_sm_state == State.FAILED:
            errors = self.error_handler.get_errors()
            if errors:
                last_error = errors[-1]
                error_info = ErrorInfo(
                    type="agent_error",
                    message=last_error.get("message", "Unknown error"),
                    details=last_error,
                    recoverable=last_error.get("recoverable", False),
                    timestamp=datetime.fromtimestamp(
                        last_error.get("timestamp", time.time()), tz=timezone.utc
                    ).isoformat(),
                )

        now = datetime.now(timezone.utc).isoformat()

        return PipelineState(
            session_id=self.session_id,
            status=pipeline_status,
            current_stage=current_stage,
            stages=stages,
            retry_count=sum(self.stage_attempts.values()),
            max_retries=sum(self.retry_strategy.retry_limits.values()),
            started_at=self.state_machine.get_history()[0]["timestamp"],
            updated_at=self.state_machine.get_history()[-1]["timestamp"],
            completed_at=(
                self.state_machine.get_history()[-1]["timestamp"]
                if current_sm_state in [State.DONE, State.FAILED]
                else None
            ),
            error=error_info,
        )

    def _build_stage_status(self, stage_name: str, result: Any, retries: int) -> StageStatus:
        """Build stage status from result.

        Args:
            stage_name: Stage name
            result: Stage result (if any)
            retries: Number of retries

        Returns:
            StageStatus
        """
        if result is None:
            return StageStatus(
                status="pending",
                started_at=None,
                completed_at=None,
                duration=None,
                result=None,
                error=None,
                retries=retries,
            )

        # Determine status from result
        status = "success"
        if hasattr(result, "status"):
            if result.status in ["success", "passed", "generated", "reproduced"]:
                status = "success"
            elif result.status in ["failed", "error", "not_reproduced"]:
                status = "failed"

        result_dict = result.model_dump() if hasattr(result, "model_dump") else result

        return StageStatus(
            status=status,
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration=getattr(result, "execution_time", None),
            result=result_dict,
            error=None,
            retries=retries,
        )

    @classmethod
    def resume(cls, run_id: str, state_store: StateStore) -> "PipelineOrchestrator":
        """Resume a pipeline from saved state.

        Args:
            run_id: Session ID to resume
            state_store: State store to load from

        Returns:
            PipelineOrchestrator instance restored from saved state

        Raises:
            ValueError: If session not found
        """
        logger.info("pipeline_resuming", run_id=run_id)

        # Check if session exists
        if not state_store.session_exists(run_id):
            raise ValueError(f"Session {run_id} not found")

        # Load state machine
        state_machine = StateMachine.load_state(state_store, run_id)

        if state_machine is None:
            raise ValueError(f"Could not load state for session {run_id}")

        metadata = state_machine.metadata
        if "issue" not in metadata or "repository" not in metadata:
            raise ValueError(
                "This legacy session has no saved issue/repository context; start a new run"
            )
        instance = cls.__new__(cls)
        instance.session_id = run_id
        instance.state_store = state_store
        instance.state_machine = state_machine
        instance.issue = IssueContext.model_validate(metadata["issue"])
        instance.repository = RepositoryContext.model_validate(metadata["repository"])
        instance.config = Config.model_validate(metadata.get("config", {}))
        instance.retry_strategy = RetryStrategy()
        instance.error_handler = ErrorHandler()
        instance.stage_results = {}
        for name, model in (
            ("localization", LocalizationResult),
            ("reproduction", ReproductionResult),
            ("patch_generation", PatchResult),
            ("validation", ValidationResult),
        ):
            data = state_store.load_stage_result(run_id, name)
            if data:
                instance.stage_results[name] = model.model_validate(data)
        instance.stage_attempts = {
            name: 0 for name in ("LOCALIZING", "REPRODUCING", "PATCHING", "VALIDATING")
        }
        instance.start_time = None
        instance.sandbox = None
        instance._owns_sandbox = True
        instance._workspace = None
        instance.global_timeout = metadata.get("global_timeout", DEFAULT_GLOBAL_TIMEOUT)
        return instance
