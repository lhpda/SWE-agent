"""File operation tools for code manipulation.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Implements Task 1.3: File Operations Tool Implementation
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from swe_agent.logging import get_logger
from swe_agent.tools.base import Tool, ToolResult

logger = get_logger(__name__)


class ReadFileTool(Tool):
    """Read file content with optional line range.

    Supports:
    - Reading entire file
    - Reading specific line range
    - Content truncation at 50,000 characters
    """

    name = "read_file"
    description = "Read file content with optional line range"
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to read",
            },
            "line_range": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "integer",
                        "description": "Start line (1-indexed, inclusive)",
                        "minimum": 1,
                    },
                    "end": {
                        "type": "integer",
                        "description": "End line (1-indexed, inclusive)",
                        "minimum": 1,
                    },
                },
                "description": "Optional line range to read",
            },
        },
        "required": ["path"],
    }
    max_content_size = 50000  # 50K characters from TASKS.md

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute file read.

        Args:
            path: File path to read
            line_range: Optional dict with 'start' and/or 'end' line numbers

        Returns:
            ToolResult with file content or error
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        path = kwargs["path"]
        line_range = kwargs.get("line_range")

        # Check if file exists
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("read_file_not_found", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {path}",
            )

        if not file_path.is_file():
            logger.warning("read_path_not_file", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Path is not a file: {path}",
            )

        try:
            # Read file
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # Apply line range if specified
            if line_range:
                start = line_range.get("start")
                end = line_range.get("end")

                # Validate range
                if start is not None and end is not None and start > end:
                    logger.warning("invalid_line_range", start=start, end=end)
                    return ToolResult(
                        output=None,
                        truncated=False,
                        error=f"Invalid line range: start ({start}) > end ({end})",
                    )

                # Convert to 0-indexed and slice
                start_idx = (start - 1) if start is not None else 0
                end_idx = end if end is not None else len(lines)

                # Clamp to file bounds
                start_idx = max(0, start_idx)
                end_idx = min(len(lines), end_idx)

                lines = lines[start_idx:end_idx]

            content = "".join(lines)

            # Check if truncation needed
            truncated = len(content) > self.max_content_size

            if truncated:
                content = content[:self.max_content_size]
                content += f"\n\n[Truncated: original size {len(''.join(lines))} chars, showing first {self.max_content_size} chars]"
                logger.info(
                    "read_file_truncated",
                    path=path,
                    original_size=len("".join(lines)),
                    truncated_size=self.max_content_size,
                )

            logger.info(
                "read_file_completed",
                path=path,
                lines=len(lines),
                truncated=truncated,
            )

            return ToolResult(
                output=content,
                truncated=truncated,
                metadata={"lines": len(lines), "path": str(file_path)},
            )

        except UnicodeDecodeError as e:
            logger.warning("read_file_encoding_error", path=path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File encoding error: {str(e)}",
            )
        except Exception as e:
            logger.error("read_file_unexpected_error", path=path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unexpected error: {str(e)}",
            )


class ReadFileWithContextTool(Tool):
    """Read file with focus lines and surrounding context.

    Reads specified focus lines plus context_lines before and after each.
    Default context is 50 lines (from TASKS.md).
    """

    name = "read_file_with_context"
    description = "Read file with focus lines and surrounding context"
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to read",
            },
            "focus_lines": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "description": "Line numbers to focus on (1-indexed)",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of context lines before and after focus (default 50)",
                "default": 50,
                "minimum": 0,
            },
        },
        "required": ["path", "focus_lines"],
    }
    max_content_size = 50000  # 50K characters from TASKS.md

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute file read with context.

        Args:
            path: File path to read
            focus_lines: List of line numbers to focus on
            context_lines: Number of lines before/after each focus line (default 50)

        Returns:
            ToolResult with file content or error
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        path = kwargs["path"]
        focus_lines = kwargs["focus_lines"]
        context_lines = kwargs.get("context_lines", 50)

        # Check if file exists
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("read_file_with_context_not_found", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {path}",
            )

        if not file_path.is_file():
            logger.warning("read_with_context_not_file", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Path is not a file: {path}",
            )

        try:
            # Read file
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # Calculate line ranges to include
            line_set = set()
            for focus_line in focus_lines:
                # Convert to 0-indexed
                focus_idx = focus_line - 1

                # Add context range
                start_idx = max(0, focus_idx - context_lines)
                end_idx = min(len(lines), focus_idx + context_lines + 1)

                for i in range(start_idx, end_idx):
                    line_set.add(i)

            # Sort line indices
            line_indices = sorted(line_set)

            # Build output with line numbers
            output_lines = []
            for idx in line_indices:
                if idx < len(lines):
                    # Include line number (1-indexed) in output
                    output_lines.append(f"{idx + 1:4d} | {lines[idx]}")

            content = "".join(output_lines)

            # Check if truncation needed
            truncated = len(content) > self.max_content_size

            if truncated:
                content = content[:self.max_content_size]
                content += f"\n\n[Truncated: showing first {self.max_content_size} chars]"
                logger.info(
                    "read_with_context_truncated",
                    path=path,
                    truncated_size=self.max_content_size,
                )

            logger.info(
                "read_file_with_context_completed",
                path=path,
                focus_lines=focus_lines,
                context_lines=context_lines,
                lines_included=len(line_indices),
                truncated=truncated,
            )

            return ToolResult(
                output=content,
                truncated=truncated,
                metadata={
                    "focus_lines": focus_lines,
                    "context_lines": context_lines,
                    "lines_included": len(line_indices),
                    "path": str(file_path),
                },
            )

        except UnicodeDecodeError as e:
            logger.warning("read_with_context_encoding_error", path=path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File encoding error: {str(e)}",
            )
        except Exception as e:
            logger.error("read_with_context_unexpected_error", path=path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unexpected error: {str(e)}",
            )


class ApplyPatchTool(Tool):
    """Apply Git unified diff patch to a file.

    Uses `git apply` to apply patches with conflict detection.
    """

    name = "apply_patch"
    description = "Apply Git unified diff patch to a file"
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to apply patch to",
            },
            "patch": {
                "type": "string",
                "description": "Unified diff patch content",
            },
        },
        "required": ["path", "patch"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute patch application.

        Args:
            path: File path to patch
            patch: Unified diff patch content

        Returns:
            ToolResult with success/failure status
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        path = kwargs["path"]
        patch_content = kwargs["patch"]

        # Check if file exists
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("apply_patch_file_not_found", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {path}",
            )

        try:
            # Write patch to temporary file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, encoding="utf-8"
            ) as patch_file:
                patch_file.write(patch_content)
                patch_file_path = patch_file.name

            try:
                # Apply patch using git apply
                result = subprocess.run(
                    ["git", "apply", "--verbose", patch_file_path],
                    cwd=file_path.parent,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    logger.info("apply_patch_success", path=path)
                    return ToolResult(
                        output="Patch applied successfully",
                        truncated=False,
                        metadata={"path": str(file_path)},
                    )
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    logger.warning("apply_patch_failed", path=path, error=error_msg)
                    return ToolResult(
                        output=None,
                        truncated=False,
                        error=f"Patch failed to apply: {error_msg}",
                    )

            finally:
                # Clean up temporary patch file
                Path(patch_file_path).unlink(missing_ok=True)

        except FileNotFoundError:
            logger.error("git_not_installed")
            return ToolResult(
                output=None,
                truncated=False,
                error="git is not installed or not in PATH",
            )
        except subprocess.TimeoutExpired:
            logger.warning("apply_patch_timeout", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error="Patch application timed out after 30 seconds",
            )
        except Exception as e:
            logger.error("apply_patch_unexpected_error", path=path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unexpected error: {str(e)}",
            )


class ApplyPatchDryRunTool(Tool):
    """Simulate applying a patch to check for conflicts.

    Uses `git apply --check` to verify if patch would apply cleanly
    without modifying files.
    """

    name = "apply_patch_dry_run"
    description = "Simulate patch application to check for conflicts"
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path to check patch against",
            },
            "patch": {
                "type": "string",
                "description": "Unified diff patch content",
            },
        },
        "required": ["path", "patch"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute patch dry run.

        Args:
            path: File path to check patch against
            patch: Unified diff patch content

        Returns:
            ToolResult indicating if patch would apply cleanly
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        path = kwargs["path"]
        patch_content = kwargs["patch"]

        # Check if file exists
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("dry_run_file_not_found", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {path}",
            )

        try:
            # Write patch to temporary file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, encoding="utf-8"
            ) as patch_file:
                patch_file.write(patch_content)
                patch_file_path = patch_file.name

            try:
                # Dry run using git apply --check
                result = subprocess.run(
                    ["git", "apply", "--check", "--verbose", patch_file_path],
                    cwd=file_path.parent,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    logger.info("dry_run_success", path=path)
                    return ToolResult(
                        output="Patch would apply cleanly (no conflicts)",
                        truncated=False,
                        metadata={"path": str(file_path), "conflicts": False},
                    )
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    logger.warning("dry_run_conflicts", path=path, error=error_msg)
                    return ToolResult(
                        output=None,
                        truncated=False,
                        error=f"Patch has conflicts: {error_msg}",
                    )

            finally:
                # Clean up temporary patch file
                Path(patch_file_path).unlink(missing_ok=True)

        except FileNotFoundError:
            logger.error("git_not_installed")
            return ToolResult(
                output=None,
                truncated=False,
                error="git is not installed or not in PATH",
            )
        except subprocess.TimeoutExpired:
            logger.warning("dry_run_timeout", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error="Dry run timed out after 30 seconds",
            )
        except Exception as e:
            logger.error("dry_run_unexpected_error", path=path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unexpected error: {str(e)}",
            )
