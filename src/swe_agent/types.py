"""Core data structures for SWE Agent.

This module defines all Pydantic models used throughout the pipeline.
Based on SYSTEM_DESIGN.md Section 4: Core Data Structure Definitions.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# 4.1 Base Types
# ============================================================================


class IssueContext(BaseModel):
    """Context information extracted from a GitHub Issue."""

    issue_id: str = Field(..., description="GitHub Issue ID")
    title: str = Field(..., description="Issue title")
    body: str = Field(..., description="Original Markdown content")
    parsed: Dict[str, Any] = Field(
        ...,
        description="Parsed issue components",
    )
    metadata: Dict[str, Any] = Field(..., description="Issue metadata")

    model_config = {"extra": "forbid"}


class RepositoryContext(BaseModel):
    """Context information about the target repository."""

    path: str = Field(..., description="Absolute path to repository")
    git: Dict[str, Any] = Field(..., description="Git information")
    project_type: str = Field(..., description="Project type (python, nodejs, etc.)")
    test_framework: Optional[str] = Field(None, description="Detected test framework")
    dependencies: Dict[str, Any] = Field(..., description="Dependency information")

    model_config = {"extra": "forbid"}


# ============================================================================
# 4.2 Stage Result Types
# ============================================================================


class LocalizationResult(BaseModel):
    """Result from the Localization stage."""

    status: Literal["success", "partial", "failed"] = Field(..., description="Localization status")
    candidates: List[Dict[str, Any]] = Field(
        ..., description="Candidate files with confidence scores"
    )
    search_strategy: str = Field(..., description="Search strategy used")
    execution_time: float = Field(..., description="Execution time in seconds")
    tool_calls: int = Field(..., description="Number of tool calls made")

    model_config = {"extra": "forbid"}


class ReproductionResult(BaseModel):
    """Result from the Reproduction stage."""

    status: Literal["reproduced", "not_reproduced", "error"] = Field(
        ..., description="Reproduction status"
    )
    root_cause: Optional[Dict[str, Any]] = Field(
        None, description="Root cause information if reproduced"
    )
    error_details: Optional[Dict[str, Any]] = Field(None, description="Error details if reproduced")
    test_command: str = Field(..., description="Command used for reproduction")
    test_output: str = Field(..., description="Test execution output (truncated to 5KB)")
    execution_time: float = Field(..., description="Execution time in seconds")
    attempts: int = Field(..., description="Number of attempts made")

    model_config = {"extra": "forbid"}


class PatchResult(BaseModel):
    """Result from the Patch Generation stage."""

    status: Literal["generated", "failed"] = Field(..., description="Generation status")
    patches: List[Dict[str, Any]] = Field(..., description="List of generated patch candidates")
    generation_strategy: str = Field(..., description="Strategy used (single_fix or beam_search)")
    execution_time: float = Field(..., description="Execution time in seconds")

    model_config = {"extra": "forbid"}


class ValidationResult(BaseModel):
    """Result from the Validation stage."""

    status: Literal["passed", "failed", "error"] = Field(..., description="Validation status")
    patch_id: str = Field(..., description="ID of the patch being validated")
    test_results: Dict[str, int] = Field(..., description="Test execution statistics")
    target_test_status: Literal["passed", "failed", "not_found"] = Field(
        ..., description="Status of the target test related to the issue"
    )
    regression_check: Dict[str, Any] = Field(..., description="Regression check results")
    test_output: str = Field(..., description="Test output (truncated to 10KB)")
    execution_time: float = Field(..., description="Execution time in seconds")

    model_config = {"extra": "forbid"}


# ============================================================================
# 4.3 Execution State Types
# ============================================================================


class ErrorInfo(BaseModel):
    """Information about an error that occurred."""

    type: Literal["tool_error", "agent_error", "validation_error", "timeout", "resource_limit"] = (
        Field(..., description="Error type")
    )
    message: str = Field(..., description="Error message")
    details: Dict[str, Any] = Field(..., description="Structured error details")
    recoverable: bool = Field(..., description="Whether the error is recoverable")
    timestamp: str = Field(..., description="ISO 8601 timestamp")

    model_config = {"extra": "forbid"}


class StageStatus(BaseModel):
    """Status information for a pipeline stage."""

    status: Literal["pending", "running", "success", "failed", "skipped"] = Field(
        ..., description="Stage status"
    )
    started_at: Optional[str] = Field(None, description="ISO 8601 start timestamp")
    completed_at: Optional[str] = Field(None, description="ISO 8601 completion timestamp")
    duration: Optional[float] = Field(None, description="Duration in seconds")
    result: Optional[Dict[str, Any]] = Field(None, description="Stage result data")
    error: Optional[ErrorInfo] = Field(None, description="Error information if failed")
    retries: int = Field(..., description="Number of retries attempted")

    model_config = {"extra": "forbid"}


class PipelineState(BaseModel):
    """Overall state of the pipeline execution."""

    session_id: str = Field(..., description="Unique session identifier")
    status: Literal["idle", "running", "success", "failed", "cancelled"] = Field(
        ..., description="Overall pipeline status"
    )
    current_stage: Optional[
        Literal["localization", "reproduction", "patch_generation", "validation"]
    ] = Field(None, description="Currently executing stage")
    stages: Dict[str, StageStatus] = Field(..., description="Status of all stages")
    retry_count: int = Field(..., description="Global retry count")
    max_retries: int = Field(..., description="Maximum retries allowed")
    started_at: str = Field(..., description="ISO 8601 start timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    completed_at: Optional[str] = Field(None, description="ISO 8601 completion timestamp")
    error: Optional[ErrorInfo] = Field(None, description="Global error if failed")

    model_config = {"extra": "forbid"}


# ============================================================================
# 4.4 Tool Call Types
# ============================================================================


class ToolCall(BaseModel):
    """Record of a tool invocation."""

    id: str = Field(..., description="Unique call identifier (UUID)")
    tool_name: str = Field(..., description="Name of the tool being called")
    parameters: Dict[str, Any] = Field(..., description="Tool parameters (JSON Schema validated)")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    caller: str = Field(..., description="Agent or component making the call")

    model_config = {"extra": "forbid"}


class ToolResult(BaseModel):
    """Result from a tool execution."""

    call_id: str = Field(..., description="Corresponding ToolCall ID")
    status: Literal["success", "error"] = Field(..., description="Execution status")
    output: Optional[Any] = Field(None, description="Tool output (string or object)")
    error: Optional[str] = Field(None, description="Error message if failed")
    execution_time: float = Field(..., description="Execution time in milliseconds")
    truncated: bool = Field(..., description="Whether output was truncated")
    metadata: Dict[str, bool] = Field(..., description="Execution metadata")

    model_config = {"extra": "forbid"}


# ============================================================================
# 4.5 Final Output Type
# ============================================================================


class PipelineResult(BaseModel):
    """Final result from the entire pipeline execution."""

    session_id: str = Field(..., description="Session identifier")
    status: Literal["success", "failed"] = Field(..., description="Overall status")
    issue: IssueContext = Field(..., description="Original issue context")
    repository: RepositoryContext = Field(..., description="Repository context")
    final_patch: Optional[Dict[str, Any]] = Field(None, description="Final validated patch")
    execution_summary: Dict[str, Any] = Field(..., description="Execution statistics")
    audit_log: str = Field(..., description="Path to execution log file")
    error: Optional[ErrorInfo] = Field(None, description="Error if failed")

    model_config = {"extra": "forbid"}
