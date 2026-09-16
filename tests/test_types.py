"""Tests for core data structures (Task 0.2)."""

import json
from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from swe_agent.types import (
    IssueContext,
    RepositoryContext,
    LocalizationResult,
    ReproductionResult,
    PatchResult,
    ValidationResult,
    PipelineState,
    StageStatus,
    ErrorInfo,
    ToolCall,
    ToolResult,
    PipelineResult,
)


class TestIssueContext:
    """Test IssueContext model."""

    def test_valid_issue_context(self):
        """Test creating valid IssueContext."""
        issue = IssueContext(
            issue_id="123",
            title="Test bug",
            body="Bug description",
            parsed={
                "error_message": "ValueError: invalid input",
                "stack_trace": ["line 1", "line 2"],
                "reproduction_steps": ["step 1"],
                "expected_behavior": "should work",
                "actual_behavior": "crashes",
                "affected_versions": ["1.0.0"],
            },
            metadata={
                "created_at": "2026-09-16T10:00:00Z",
                "labels": ["bug"],
                "author": "user1",
            },
        )
        assert issue.issue_id == "123"
        assert issue.title == "Test bug"
        assert issue.parsed["error_message"] == "ValueError: invalid input"

    def test_issue_context_serialization(self):
        """Test IssueContext JSON serialization."""
        issue = IssueContext(
            issue_id="456",
            title="Another bug",
            body="Description",
            parsed={},
            metadata={
                "created_at": "2026-09-16T10:00:00Z",
                "labels": [],
                "author": "user2",
            },
        )
        json_str = issue.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["issue_id"] == "456"

    def test_issue_context_with_none_parsed_fields(self):
        """Test IssueContext with null parsed fields."""
        issue = IssueContext(
            issue_id="789",
            title="Bug",
            body="Body",
            parsed={
                "error_message": None,
                "stack_trace": None,
                "reproduction_steps": None,
                "expected_behavior": None,
                "actual_behavior": None,
                "affected_versions": None,
            },
            metadata={
                "created_at": "2026-09-16T10:00:00Z",
                "labels": [],
                "author": "user",
            },
        )
        assert issue.parsed["error_message"] is None


class TestRepositoryContext:
    """Test RepositoryContext model."""

    def test_valid_repository_context(self):
        """Test creating valid RepositoryContext."""
        repo = RepositoryContext(
            path="/path/to/repo",
            git={
                "remote_url": "https://github.com/user/repo.git",
                "current_branch": "main",
                "commit_sha": "abc123",
                "is_dirty": False,
            },
            project_type="python",
            test_framework="pytest",
            dependencies={
                "files": ["requirements.txt"],
                "installed": True,
            },
        )
        assert repo.path == "/path/to/repo"
        assert repo.project_type == "python"
        assert repo.test_framework == "pytest"

    def test_repository_context_with_none_fields(self):
        """Test RepositoryContext with optional null fields."""
        repo = RepositoryContext(
            path="/path/to/repo",
            git={
                "remote_url": None,
                "current_branch": "main",
                "commit_sha": "abc123",
                "is_dirty": False,
            },
            project_type="unknown",
            test_framework=None,
            dependencies={
                "files": [],
                "installed": False,
            },
        )
        assert repo.git["remote_url"] is None
        assert repo.test_framework is None


class TestLocalizationResult:
    """Test LocalizationResult model."""

    def test_valid_localization_result(self):
        """Test creating valid LocalizationResult."""
        result = LocalizationResult(
            status="success",
            candidates=[
                {
                    "file_path": "src/main.py",
                    "confidence": 0.95,
                    "reason": "Error trace points here",
                    "relevant_symbols": [
                        {
                            "name": "process_data",
                            "type": "function",
                            "line_start": 10,
                            "line_end": 20,
                        }
                    ],
                    "code_snippet": "def process_data():\n    pass",
                }
            ],
            search_strategy="stack_trace_based",
            execution_time=2.5,
            tool_calls=5,
        )
        assert result.status == "success"
        assert len(result.candidates) == 1
        assert result.candidates[0]["confidence"] == 0.95

    def test_localization_result_status_validation(self):
        """Test LocalizationResult status must be valid."""
        with pytest.raises(ValidationError):
            LocalizationResult(
                status="invalid_status",
                candidates=[],
                search_strategy="test",
                execution_time=1.0,
                tool_calls=1,
            )


class TestReproductionResult:
    """Test ReproductionResult model."""

    def test_reproduced_result(self):
        """Test ReproductionResult with reproduced status."""
        result = ReproductionResult(
            status="reproduced",
            root_cause={
                "file_path": "src/main.py",
                "line_number": 42,
                "function_name": "process_data",
                "explanation": "Division by zero",
            },
            error_details={
                "error_type": "ZeroDivisionError",
                "error_message": "division by zero",
                "stack_trace": ["line1", "line2"],
                "relevant_logs": "Last 200 lines...",
            },
            test_command="pytest tests/test_main.py",
            test_output="FAILED...",
            execution_time=5.2,
            attempts=2,
        )
        assert result.status == "reproduced"
        assert result.root_cause["line_number"] == 42

    def test_not_reproduced_result(self):
        """Test ReproductionResult with not_reproduced status."""
        result = ReproductionResult(
            status="not_reproduced",
            root_cause=None,
            error_details=None,
            test_command="pytest tests/",
            test_output="All passed",
            execution_time=3.0,
            attempts=5,
        )
        assert result.status == "not_reproduced"
        assert result.root_cause is None


class TestPatchResult:
    """Test PatchResult model."""

    def test_valid_patch_result(self):
        """Test creating valid PatchResult."""
        result = PatchResult(
            status="generated",
            patches=[
                {
                    "id": "patch-uuid-123",
                    "diff": "--- a/file.py\n+++ b/file.py\n...",
                    "description": "Fix division by zero",
                    "files_changed": ["src/main.py"],
                    "lines_added": 2,
                    "lines_removed": 1,
                    "confidence": 0.85,
                    "syntax_valid": True,
                }
            ],
            generation_strategy="single_fix",
            execution_time=4.5,
        )
        assert result.status == "generated"
        assert len(result.patches) == 1
        assert result.patches[0]["syntax_valid"] is True

    def test_multiple_patches(self):
        """Test PatchResult with multiple candidates."""
        result = PatchResult(
            status="generated",
            patches=[
                {
                    "id": "p1",
                    "diff": "diff1",
                    "description": "Fix 1",
                    "files_changed": ["file1.py"],
                    "lines_added": 1,
                    "lines_removed": 1,
                    "confidence": 0.9,
                    "syntax_valid": True,
                },
                {
                    "id": "p2",
                    "diff": "diff2",
                    "description": "Fix 2",
                    "files_changed": ["file2.py"],
                    "lines_added": 2,
                    "lines_removed": 0,
                    "confidence": 0.7,
                    "syntax_valid": True,
                },
            ],
            generation_strategy="beam_search",
            execution_time=6.0,
        )
        assert len(result.patches) == 2


class TestValidationResult:
    """Test ValidationResult model."""

    def test_passed_validation(self):
        """Test ValidationResult with passed status."""
        result = ValidationResult(
            status="passed",
            patch_id="patch-123",
            test_results={
                "total": 100,
                "passed": 100,
                "failed": 0,
                "skipped": 0,
                "error": 0,
            },
            target_test_status="passed",
            regression_check={
                "new_failures": [],
                "fixed_tests": ["test_main"],
                "is_regression": False,
            },
            test_output="All tests passed",
            execution_time=8.5,
        )
        assert result.status == "passed"
        assert result.test_results["passed"] == 100
        assert result.regression_check["is_regression"] is False

    def test_failed_validation_with_regression(self):
        """Test ValidationResult with regression."""
        result = ValidationResult(
            status="failed",
            patch_id="patch-456",
            test_results={
                "total": 100,
                "passed": 98,
                "failed": 2,
                "skipped": 0,
                "error": 0,
            },
            target_test_status="passed",
            regression_check={
                "new_failures": ["test_feature_x", "test_feature_y"],
                "fixed_tests": ["test_main"],
                "is_regression": True,
            },
            test_output="2 tests failed",
            execution_time=10.0,
        )
        assert result.status == "failed"
        assert result.regression_check["is_regression"] is True
        assert len(result.regression_check["new_failures"]) == 2


class TestStageStatus:
    """Test StageStatus model."""

    def test_pending_stage(self):
        """Test StageStatus in pending state."""
        stage = StageStatus(
            status="pending",
            started_at=None,
            completed_at=None,
            duration=None,
            result=None,
            error=None,
            retries=0,
        )
        assert stage.status == "pending"
        assert stage.retries == 0

    def test_completed_stage(self):
        """Test StageStatus in success state."""
        stage = StageStatus(
            status="success",
            started_at="2026-09-16T10:00:00Z",
            completed_at="2026-09-16T10:05:00Z",
            duration=300.0,
            result={"some": "data"},
            error=None,
            retries=1,
        )
        assert stage.status == "success"
        assert stage.duration == 300.0


class TestErrorInfo:
    """Test ErrorInfo model."""

    def test_recoverable_error(self):
        """Test ErrorInfo for recoverable error."""
        error = ErrorInfo(
            type="timeout",
            message="Command timed out",
            details={"command": "pytest", "timeout": 60},
            recoverable=True,
            timestamp="2026-09-16T10:00:00Z",
        )
        assert error.type == "timeout"
        assert error.recoverable is True

    def test_non_recoverable_error(self):
        """Test ErrorInfo for non-recoverable error."""
        error = ErrorInfo(
            type="validation_error",
            message="Invalid input",
            details={"field": "issue_id"},
            recoverable=False,
            timestamp="2026-09-16T10:00:00Z",
        )
        assert error.recoverable is False


class TestPipelineState:
    """Test PipelineState model."""

    def test_initial_pipeline_state(self):
        """Test PipelineState in initial state."""
        state = PipelineState(
            session_id="session-123",
            status="idle",
            current_stage=None,
            stages={
                "localization": StageStatus(
                    status="pending",
                    started_at=None,
                    completed_at=None,
                    duration=None,
                    result=None,
                    error=None,
                    retries=0,
                ),
                "reproduction": StageStatus(
                    status="pending",
                    started_at=None,
                    completed_at=None,
                    duration=None,
                    result=None,
                    error=None,
                    retries=0,
                ),
                "patch_generation": StageStatus(
                    status="pending",
                    started_at=None,
                    completed_at=None,
                    duration=None,
                    result=None,
                    error=None,
                    retries=0,
                ),
                "validation": StageStatus(
                    status="pending",
                    started_at=None,
                    completed_at=None,
                    duration=None,
                    result=None,
                    error=None,
                    retries=0,
                ),
            },
            retry_count=0,
            max_retries=3,
            started_at="2026-09-16T10:00:00Z",
            updated_at="2026-09-16T10:00:00Z",
            completed_at=None,
            error=None,
        )
        assert state.status == "idle"
        assert state.retry_count == 0


class TestToolCall:
    """Test ToolCall model."""

    def test_valid_tool_call(self):
        """Test creating valid ToolCall."""
        call = ToolCall(
            id="call-123",
            tool_name="ripgrep_search",
            parameters={"pattern": "def main", "file_types": ["py"]},
            timestamp="2026-09-16T10:00:00Z",
            caller="localization_agent",
        )
        assert call.tool_name == "ripgrep_search"
        assert call.parameters["pattern"] == "def main"


class TestToolResult:
    """Test ToolResult model."""

    def test_successful_tool_result(self):
        """Test ToolResult for successful execution."""
        result = ToolResult(
            call_id="call-123",
            status="success",
            output={"matches": ["file1.py", "file2.py"]},
            error=None,
            execution_time=150.5,
            truncated=False,
            metadata={"sandbox_used": False, "cache_hit": False},
        )
        assert result.status == "success"
        assert result.truncated is False

    def test_failed_tool_result(self):
        """Test ToolResult for failed execution."""
        result = ToolResult(
            call_id="call-456",
            status="error",
            output=None,
            error="Command not found",
            execution_time=10.0,
            truncated=False,
            metadata={"sandbox_used": True, "cache_hit": False},
        )
        assert result.status == "error"
        assert result.error == "Command not found"


class TestPipelineResult:
    """Test PipelineResult model."""

    def test_successful_pipeline_result(self):
        """Test PipelineResult for successful execution."""
        result = PipelineResult(
            session_id="session-123",
            status="success",
            issue=IssueContext(
                issue_id="1",
                title="Bug",
                body="Description",
                parsed={},
                metadata={
                    "created_at": "2026-09-16T10:00:00Z",
                    "labels": [],
                    "author": "user",
                },
            ),
            repository=RepositoryContext(
                path="/repo",
                git={
                    "remote_url": None,
                    "current_branch": "main",
                    "commit_sha": "abc",
                    "is_dirty": False,
                },
                project_type="python",
                test_framework=None,
                dependencies={"files": [], "installed": False},
            ),
            final_patch={
                "diff": "--- a/file\n+++ b/file",
                "description": "Fix bug",
                "files_changed": ["file.py"],
                "validation_passed": True,
            },
            execution_summary={
                "total_time": 600.0,
                "stages_completed": ["localization", "reproduction", "patch_generation", "validation"],
                "tool_calls_total": 25,
                "llm_calls_total": 8,
                "tokens_used": 50000,
            },
            audit_log="/path/to/log",
            error=None,
        )
        assert result.status == "success"
        assert result.final_patch["validation_passed"] is True

    def test_failed_pipeline_result(self):
        """Test PipelineResult for failed execution."""
        result = PipelineResult(
            session_id="session-456",
            status="failed",
            issue=IssueContext(
                issue_id="2",
                title="Bug",
                body="Description",
                parsed={},
                metadata={
                    "created_at": "2026-09-16T10:00:00Z",
                    "labels": [],
                    "author": "user",
                },
            ),
            repository=RepositoryContext(
                path="/repo",
                git={
                    "remote_url": None,
                    "current_branch": "main",
                    "commit_sha": "abc",
                    "is_dirty": False,
                },
                project_type="python",
                test_framework=None,
                dependencies={"files": [], "installed": False},
            ),
            final_patch=None,
            execution_summary={
                "total_time": 300.0,
                "stages_completed": ["localization"],
                "tool_calls_total": 10,
                "llm_calls_total": 3,
                "tokens_used": 15000,
            },
            audit_log="/path/to/log",
            error=ErrorInfo(
                type="agent_error",
                message="Failed to localize",
                details={},
                recoverable=False,
                timestamp="2026-09-16T10:00:00Z",
            ),
        )
        assert result.status == "failed"
        assert result.final_patch is None
        assert result.error is not None
