"""
Test suite for PatchApplicator - TDD approach.

Tests cover:
- Successful patch application
- Automatic rollback on failure
- Snapshot state restoration
- File permission consistency
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
import os
import tempfile
from pathlib import Path

from src.swe_agent.agents.validation.applicator import PatchApplicator


class TestPatchApplicatorInitialization:
    """Test PatchApplicator initialization."""

    def test_init_creates_engine_and_manager(self):
        """Test that initialization creates CodeEditEngine."""
        applicator = PatchApplicator()
        assert applicator.edit_engine is not None
        assert applicator._current_snapshot_id is None

    def test_init_no_snapshot_manager_initially(self):
        """Test that snapshot manager is not created until needed."""
        applicator = PatchApplicator()
        assert applicator.snapshot_manager is None


class TestCreateSnapshot:
    """Test snapshot creation."""

    def test_create_snapshot_success(self):
        """Test successful snapshot creation."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()
        mock_sandbox.container_id = "test-container-123"

        with patch(
            "src.swe_agent.agents.validation.applicator.SnapshotManager"
        ) as MockSnapshotManager:
            mock_manager = Mock()
            mock_manager.create_snapshot.return_value = "snapshot-123"
            MockSnapshotManager.return_value = mock_manager

            snapshot_id = applicator.create_snapshot(mock_sandbox, tag="test")

            assert snapshot_id == "snapshot-123"
            assert applicator._current_snapshot_id == "snapshot-123"
            MockSnapshotManager.assert_called_once_with(mock_sandbox)
            mock_manager.create_snapshot.assert_called_once_with(tag="test")

    def test_create_snapshot_without_tag(self):
        """Test snapshot creation without explicit tag."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()
        mock_sandbox.container_id = "test-container-123"

        with patch(
            "src.swe_agent.agents.validation.applicator.SnapshotManager"
        ) as MockSnapshotManager:
            mock_manager = Mock()
            mock_manager.create_snapshot.return_value = "snapshot-456"
            MockSnapshotManager.return_value = mock_manager

            snapshot_id = applicator.create_snapshot(mock_sandbox)

            assert snapshot_id == "snapshot-456"
            mock_manager.create_snapshot.assert_called_once_with(tag=None)

    def test_create_snapshot_failure_raises_exception(self):
        """Test that snapshot creation failure raises exception."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()

        with patch(
            "src.swe_agent.agents.validation.applicator.SnapshotManager"
        ) as MockSnapshotManager:
            mock_manager = Mock()
            mock_manager.create_snapshot.side_effect = RuntimeError("Snapshot failed")
            MockSnapshotManager.return_value = mock_manager

            with pytest.raises(RuntimeError, match="Snapshot failed"):
                applicator.create_snapshot(mock_sandbox)


class TestRollback:
    """Test rollback functionality."""

    def test_rollback_success(self):
        """Test successful rollback to snapshot."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()

        with patch(
            "src.swe_agent.agents.validation.applicator.SnapshotManager"
        ) as MockSnapshotManager:
            mock_manager = Mock()
            MockSnapshotManager.return_value = mock_manager

            # Simulate snapshot creation first
            applicator._current_snapshot_id = "snapshot-789"
            applicator.snapshot_manager = mock_manager

            result = applicator.rollback()

            assert result["success"] is True
            mock_manager.restore_snapshot.assert_called_once_with("snapshot-789")

    def test_rollback_without_snapshot(self):
        """Test rollback when no snapshot exists."""
        applicator = PatchApplicator()

        result = applicator.rollback()

        assert result["success"] is False
        assert "No snapshot available" in result["error"]

    def test_rollback_failure_returns_error(self):
        """Test rollback failure handling."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()

        with patch(
            "src.swe_agent.agents.validation.applicator.SnapshotManager"
        ) as MockSnapshotManager:
            mock_manager = Mock()
            mock_manager.restore_snapshot.side_effect = Exception("Restore failed")
            MockSnapshotManager.return_value = mock_manager

            applicator._current_snapshot_id = "snapshot-999"
            applicator.snapshot_manager = mock_manager

            result = applicator.rollback()

            assert result["success"] is False
            assert "Restore failed" in result["error"]


class TestVerifyApplication:
    """Test patch verification."""

    def test_verify_application_file_exists(self):
        """Test verification when file exists."""
        applicator = PatchApplicator()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('hello')")
            temp_file = f.name

        try:
            result = applicator.verify_application(temp_file)
            assert result["verified"] is True
            assert result["file_exists"] is True
        finally:
            os.unlink(temp_file)

    def test_verify_application_file_not_exists(self):
        """Test verification when file doesn't exist."""
        applicator = PatchApplicator()

        result = applicator.verify_application("/nonexistent/file.py")

        assert result["verified"] is False
        assert result["file_exists"] is False

    def test_verify_application_with_syntax_check(self):
        """Test verification includes syntax check for Python files."""
        applicator = PatchApplicator()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("def foo():\n    return 42\n")
            temp_file = f.name

        try:
            result = applicator.verify_application(temp_file)
            assert result["verified"] is True
            assert result["syntax_valid"] is True
        finally:
            os.unlink(temp_file)

    def test_verify_application_invalid_syntax(self):
        """Test verification detects syntax errors."""
        applicator = PatchApplicator()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("def foo(\n    return 42\n")  # Missing closing paren
            temp_file = f.name

        try:
            result = applicator.verify_application(temp_file)
            assert result["verified"] is False
            assert result["syntax_valid"] is False
        finally:
            os.unlink(temp_file)


class TestApplyPatch:
    """Test complete patch application workflow."""

    def test_apply_patch_success_clean_repo(self):
        """Test successful patch application to clean repository."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()
        mock_sandbox.container_id = "test-container"

        patch_content = {
            "type": "replace",
            "start_line": 1,
            "end_line": 1,
            "content": "print('updated')\n",
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('original')\n")
            temp_file = f.name

        try:
            with patch(
                "src.swe_agent.agents.validation.applicator.SnapshotManager"
            ) as MockSnapshotManager:
                mock_manager = Mock()
                mock_manager.create_snapshot.return_value = "snapshot-abc"
                MockSnapshotManager.return_value = mock_manager

                result = applicator.apply_patch(patch_content, temp_file, mock_sandbox)

                assert result["success"] is True
                assert result["applied"] is True
                assert result["file_path"] == temp_file
                assert result["snapshot_id"] == "snapshot-abc"
                assert result["error"] is None

                # Verify file was actually modified
                with open(temp_file, "r") as f:
                    content = f.read()
                    assert "updated" in content
        finally:
            os.unlink(temp_file)

    def test_apply_patch_with_rollback_on_syntax_error(self):
        """Test automatic rollback when patch introduces syntax error."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()
        mock_sandbox.container_id = "test-container"

        patch_content = {
            "type": "replace",
            "start_line": 1,
            "end_line": 1,
            "content": "def foo(\n",  # Invalid syntax
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('original')\n")
            temp_file = f.name
            original_content = "print('original')\n"

        try:
            with patch(
                "src.swe_agent.agents.validation.applicator.SnapshotManager"
            ) as MockSnapshotManager:
                mock_manager = Mock()
                mock_manager.create_snapshot.return_value = "snapshot-rollback"
                MockSnapshotManager.return_value = mock_manager

                result = applicator.apply_patch(patch_content, temp_file, mock_sandbox)

                assert result["success"] is False
                assert result["applied"] is False
                assert "Syntax error" in result["error"]

                # Verify rollback was attempted via edit engine
                # File should still have original content since edit engine validates
                with open(temp_file, "r") as f:
                    content = f.read()
                    assert content == original_content
        finally:
            os.unlink(temp_file)

    def test_apply_patch_file_not_found(self):
        """Test patch application when target file doesn't exist."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()

        patch_content = {
            "type": "replace",
            "start_line": 1,
            "end_line": 1,
            "content": "new content\n",
        }

        with patch(
            "src.swe_agent.agents.validation.applicator.SnapshotManager"
        ) as MockSnapshotManager:
            mock_manager = Mock()
            mock_manager.create_snapshot.return_value = "snapshot-notfound"
            MockSnapshotManager.return_value = mock_manager

            result = applicator.apply_patch(patch_content, "/nonexistent/file.py", mock_sandbox)

            assert result["success"] is False
            assert result["applied"] is False
            assert "File not found" in result["error"]

    def test_apply_patch_preserves_file_permissions(self):
        """Test that patch application preserves file permissions."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()
        mock_sandbox.container_id = "test-container"

        patch_content = {
            "type": "replace",
            "start_line": 1,
            "end_line": 1,
            "content": "print('updated')\n",
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('original')\n")
            temp_file = f.name

        # Set specific permissions
        os.chmod(temp_file, 0o644)
        original_perms = os.stat(temp_file).st_mode

        try:
            with patch(
                "src.swe_agent.agents.validation.applicator.SnapshotManager"
            ) as MockSnapshotManager:
                mock_manager = Mock()
                mock_manager.create_snapshot.return_value = "snapshot-perms"
                MockSnapshotManager.return_value = mock_manager

                result = applicator.apply_patch(patch_content, temp_file, mock_sandbox)

                assert result["success"] is True

                # Verify permissions are preserved
                new_perms = os.stat(temp_file).st_mode
                assert new_perms == original_perms
        finally:
            os.unlink(temp_file)

    def test_apply_patch_multiple_operations(self):
        """Test applying multiple patch operations."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()
        mock_sandbox.container_id = "test-container"

        patch_content = {"type": "insert", "start_line": 0, "content": "# Header comment\n"}

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('original')\n")
            temp_file = f.name

        try:
            with patch(
                "src.swe_agent.agents.validation.applicator.SnapshotManager"
            ) as MockSnapshotManager:
                mock_manager = Mock()
                mock_manager.create_snapshot.return_value = "snapshot-multi"
                MockSnapshotManager.return_value = mock_manager

                result = applicator.apply_patch(patch_content, temp_file, mock_sandbox)

                assert result["success"] is True
                assert result["applied"] is True

                with open(temp_file, "r") as f:
                    content = f.read()
                    assert content.startswith("# Header comment")
        finally:
            os.unlink(temp_file)

    def test_apply_patch_without_sandbox_creates_no_snapshot(self):
        """Test patch application without sandbox (no snapshot created)."""
        applicator = PatchApplicator()

        patch_content = {
            "type": "replace",
            "start_line": 1,
            "end_line": 1,
            "content": "print('updated')\n",
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('original')\n")
            temp_file = f.name

        try:
            result = applicator.apply_patch(patch_content, temp_file, sandbox=None)

            assert result["success"] is True
            assert result["applied"] is True
            assert result["snapshot_id"] is None
        finally:
            os.unlink(temp_file)

    def test_apply_patch_invalid_operation_type(self):
        """Test patch application with invalid operation type."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()

        patch_content = {"type": "invalid_type", "content": "something\n"}

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('original')\n")
            temp_file = f.name

        try:
            with patch(
                "src.swe_agent.agents.validation.applicator.SnapshotManager"
            ) as MockSnapshotManager:
                mock_manager = Mock()
                mock_manager.create_snapshot.return_value = "snapshot-invalid"
                MockSnapshotManager.return_value = mock_manager

                result = applicator.apply_patch(patch_content, temp_file, mock_sandbox)

                assert result["success"] is False
                assert result["applied"] is False
                assert "Invalid operation type" in result["error"]
        finally:
            os.unlink(temp_file)


class TestPatchApplicatorEdgeCases:
    """Test edge cases and error handling."""

    def test_apply_patch_to_non_python_file(self):
        """Test applying patch to non-Python file (no syntax check)."""
        applicator = PatchApplicator()
        mock_sandbox = Mock()
        mock_sandbox.container_id = "test-container"

        patch_content = {
            "type": "replace",
            "start_line": 1,
            "end_line": 1,
            "content": "new content\n",
        }

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("original content\n")
            temp_file = f.name

        try:
            with patch(
                "src.swe_agent.agents.validation.applicator.SnapshotManager"
            ) as MockSnapshotManager:
                mock_manager = Mock()
                mock_manager.create_snapshot.return_value = "snapshot-txt"
                MockSnapshotManager.return_value = mock_manager

                result = applicator.apply_patch(patch_content, temp_file, mock_sandbox)

                assert result["success"] is True
                assert result["applied"] is True
        finally:
            os.unlink(temp_file)

    def test_rollback_clears_snapshot_reference(self):
        """Test that rollback clears the current snapshot reference."""
        applicator = PatchApplicator()

        with patch(
            "src.swe_agent.agents.validation.applicator.SnapshotManager"
        ) as MockSnapshotManager:
            mock_manager = Mock()
            MockSnapshotManager.return_value = mock_manager

            applicator._current_snapshot_id = "snapshot-clear"
            applicator.snapshot_manager = mock_manager

            applicator.rollback()

            assert applicator._current_snapshot_id is None

    def test_verify_application_with_permission_info(self):
        """Test that verification includes file permission information."""
        applicator = PatchApplicator()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            f.write("print('test')\n")
            temp_file = f.name

        try:
            result = applicator.verify_application(temp_file)

            assert "permissions" in result
            assert result["permissions"] is not None
        finally:
            os.unlink(temp_file)
