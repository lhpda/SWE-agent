"""
Code Edit Engine - Apply, validate, and rollback code edits.

Supports insert, replace, and delete operations with syntax validation.
"""

import ast
import difflib
from pathlib import Path
from typing import Dict, Any, Optional
import shutil
import tempfile


class CodeEditEngine:
    """Engine for applying code edits with validation and rollback support."""

    def __init__(self):
        """Initialize the edit engine with backup storage."""
        self._backups: Dict[str, str] = {}

    def apply_edit(self, file_path: str, edit_operation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a code edit operation to a file.

        Args:
            file_path: Path to the file to edit
            edit_operation: Dictionary containing:
                - type: "insert" | "replace" | "delete"
                - file_path: Path to file (redundant but kept for interface)
                - start_line: Starting line number (1-indexed)
                - end_line: Ending line number (for replace/delete)
                - content: New content (for insert/replace)

        Returns:
            Dict with:
                - success: bool
                - error: str (if failed)
                - diff: str (if successful)
        """
        try:
            # Validate operation structure
            op_type = edit_operation.get("type")
            if op_type not in ["insert", "replace", "delete"]:
                return {"success": False, "error": f"Invalid operation type: {op_type}"}

            # Check file exists
            path = Path(file_path)
            if not path.exists():
                return {"success": False, "error": f"File not found: {file_path}"}

            # Read original content
            with open(file_path, "r", encoding="utf-8") as f:
                original_lines = f.readlines()

            # Store backup before edit
            original_content = "".join(original_lines)
            self._backups[file_path] = original_content

            # Apply the operation
            if op_type == "insert":
                new_lines = self._apply_insert(original_lines, edit_operation)
            elif op_type == "replace":
                new_lines = self._apply_replace(original_lines, edit_operation)
            elif op_type == "delete":
                new_lines = self._apply_delete(original_lines, edit_operation)
            else:
                return {"success": False, "error": f"Unknown operation: {op_type}"}

            new_content = "".join(new_lines)

            # Validate syntax for Python files
            if file_path.endswith(".py"):
                validation = self.validate_syntax(file_path, new_content)
                if not validation["valid"]:
                    return {
                        "success": False,
                        "error": f"Syntax error: {validation.get('error', 'Invalid syntax')}",
                    }

            # Write the modified content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Generate diff
            diff = self.generate_diff(original_content, new_content)

            return {"success": True, "diff": diff}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _apply_insert(self, lines: list, operation: Dict[str, Any]) -> list:
        """Apply an insert operation."""
        start_line = operation.get("start_line", 0)
        content = operation.get("content", "")

        # Validate line number
        if start_line < 0 or start_line > len(lines):
            raise ValueError(f"Invalid start_line: {start_line}")

        # Insert content
        new_lines = content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        result = lines[:start_line] + new_lines + lines[start_line:]
        return result

    def _apply_replace(self, lines: list, operation: Dict[str, Any]) -> list:
        """Apply a replace operation."""
        start_line = operation.get("start_line", 1)
        end_line = operation.get("end_line", start_line)
        content = operation.get("content", "")

        # Convert to 0-indexed
        start_idx = start_line - 1
        end_idx = end_line

        # Validate line numbers
        if start_idx < 0 or end_idx > len(lines):
            raise ValueError(f"Invalid line range: {start_line}-{end_line}")

        # Replace content
        new_lines = content.splitlines(keepends=True) if content else []
        if new_lines and not new_lines[-1].endswith("\n") and content.endswith("\n"):
            new_lines[-1] += "\n"

        result = lines[:start_idx] + new_lines + lines[end_idx:]
        return result

    def _apply_delete(self, lines: list, operation: Dict[str, Any]) -> list:
        """Apply a delete operation."""
        start_line = operation.get("start_line", 1)
        end_line = operation.get("end_line", start_line)

        # Convert to 0-indexed
        start_idx = start_line - 1
        end_idx = end_line

        # Validate line numbers
        if start_idx < 0 or end_idx > len(lines):
            raise ValueError(f"Invalid line range: {start_line}-{end_line}")

        # Delete lines
        result = lines[:start_idx] + lines[end_idx:]
        return result

    def validate_syntax(self, file_path: str, content: str) -> Dict[str, Any]:
        """
        Validate syntax of code content.

        Currently supports Python files (.py).

        Args:
            file_path: Path to file (used to determine language)
            content: Code content to validate

        Returns:
            Dict with:
                - valid: bool
                - error: str (if invalid)
        """
        # Only validate Python files
        if not file_path.endswith(".py"):
            return {"valid": True}

        try:
            ast.parse(content)
            return {"valid": True}
        except SyntaxError as e:
            return {"valid": False, "error": f"{e.msg} at line {e.lineno}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def generate_diff(self, original: str, modified: str) -> str:
        """
        Generate unified diff between original and modified content.

        Args:
            original: Original content
            modified: Modified content

        Returns:
            Unified diff string
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines, modified_lines, fromfile="original", tofile="modified", lineterm=""
        )

        return "".join(diff)

    def rollback_edit(self, file_path: str) -> Dict[str, Any]:
        """
        Rollback the last edit to a file.

        Args:
            file_path: Path to file to rollback

        Returns:
            Dict with:
                - success: bool
                - error: str (if failed)
        """
        try:
            if file_path not in self._backups:
                return {"success": True, "message": "No backup found for this file"}

            # Restore from backup
            backup_content = self._backups[file_path]
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(backup_content)

            # Remove backup after successful restore
            del self._backups[file_path]

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}
