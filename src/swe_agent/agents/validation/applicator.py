"""
Patch Applicator - Apply patches with snapshot and rollback support.

Provides functionality to:
- Apply patches to sandbox files
- Create snapshots before application
- Rollback on failure
- Verify application success
"""

import os
import ast
from typing import Dict, Any, Optional
from pathlib import Path

from ...agents.patch.edit_engine import CodeEditEngine
from ...sandbox.snapshot import SnapshotManager


class PatchApplicator:
    """
    Applies patches to files with snapshot and rollback capabilities.

    Workflow:
    1. Create snapshot (if sandbox provided)
    2. Read target file
    3. Apply patch using EditEngine
    4. Verify syntax (for Python files)
    5. Rollback snapshot if failure occurs
    """

    def __init__(self):
        """Initialize PatchApplicator with CodeEditEngine."""
        self.edit_engine = CodeEditEngine()
        self.snapshot_manager: Optional[SnapshotManager] = None
        self._current_snapshot_id: Optional[str] = None

    def create_snapshot(self, sandbox, tag: Optional[str] = None) -> str:
        """
        Create a snapshot of the current sandbox state.

        Args:
            sandbox: DockerSandbox instance
            tag: Optional tag for the snapshot

        Returns:
            Snapshot ID

        Raises:
            RuntimeError: If snapshot creation fails
        """
        if self.snapshot_manager is None:
            self.snapshot_manager = SnapshotManager(sandbox)

        snapshot_id = self.snapshot_manager.create_snapshot(tag=tag)
        self._current_snapshot_id = snapshot_id
        return snapshot_id

    def rollback(self) -> Dict[str, Any]:
        """
        Rollback to the last created snapshot.

        Returns:
            Dict with:
                - success: bool
                - error: str (if failed)
        """
        if self._current_snapshot_id is None or self.snapshot_manager is None:
            return {"success": False, "error": "No snapshot available for rollback"}

        try:
            self.snapshot_manager.restore_snapshot(self._current_snapshot_id)
            self._current_snapshot_id = None
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def verify_application(self, file_path: str) -> Dict[str, Any]:
        """
        Verify that patch was correctly applied.

        Args:
            file_path: Path to the file to verify

        Returns:
            Dict with:
                - verified: bool
                - file_exists: bool
                - syntax_valid: bool (for Python files)
                - permissions: int (file permissions)
        """
        path = Path(file_path)

        result = {
            "verified": True,
            "file_exists": path.exists(),
            "syntax_valid": True,
            "permissions": None,
        }

        # Check file exists
        if not path.exists():
            result["verified"] = False
            return result

        # Get file permissions
        try:
            result["permissions"] = os.stat(file_path).st_mode
        except Exception:
            pass

        # Validate syntax for Python files
        if file_path.endswith(".py"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                ast.parse(content)
                result["syntax_valid"] = True
            except SyntaxError:
                result["syntax_valid"] = False
                result["verified"] = False
            except Exception:
                result["syntax_valid"] = False
                result["verified"] = False

        return result

    def apply_patch(
        self, patch_content: Dict[str, Any], file_path: str, sandbox: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Apply a patch to a file with snapshot and rollback support.

        Args:
            patch_content: Patch operation dictionary containing:
                - type: "insert" | "replace" | "delete"
                - start_line: Starting line number
                - end_line: Ending line number (for replace/delete)
                - content: New content (for insert/replace)
            file_path: Path to the target file
            sandbox: Optional DockerSandbox instance for snapshotting

        Returns:
            Dict with:
                - success: bool
                - file_path: str
                - applied: bool
                - error: str | None
                - snapshot_id: str | None
        """
        result = {
            "success": False,
            "file_path": file_path,
            "applied": False,
            "error": None,
            "snapshot_id": None,
        }

        try:
            # Create snapshot if sandbox provided
            if sandbox is not None:
                snapshot_id = self.create_snapshot(sandbox, tag="before_patch")
                result["snapshot_id"] = snapshot_id

            # Apply the patch using EditEngine
            edit_result = self.edit_engine.apply_edit(file_path, patch_content)

            if not edit_result.get("success", False):
                result["error"] = edit_result.get("error", "Unknown error")
                result["applied"] = False

                # Rollback snapshot if it was created
                if result["snapshot_id"] is not None:
                    self.rollback()

                return result

            # Verify the application
            verification = self.verify_application(file_path)

            if not verification["verified"]:
                result["error"] = "Verification failed: " + (
                    "File not found"
                    if not verification["file_exists"]
                    else (
                        "Syntax error"
                        if not verification["syntax_valid"]
                        else "Unknown verification error"
                    )
                )
                result["applied"] = False

                # Rollback snapshot if it was created
                if result["snapshot_id"] is not None:
                    self.rollback()

                return result

            # Success
            result["success"] = True
            result["applied"] = True
            return result

        except Exception as e:
            result["error"] = str(e)
            result["applied"] = False

            # Attempt rollback on exception
            if result["snapshot_id"] is not None:
                try:
                    self.rollback()
                except Exception:
                    pass  # Rollback failed, but original error is more important

            return result
