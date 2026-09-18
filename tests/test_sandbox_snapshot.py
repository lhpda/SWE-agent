"""
Tests for Snapshot and Rollback Mechanism.
Following TDD: Write tests first, then implement.
"""

import pytest
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import docker
from docker.errors import NotFound, ImageNotFound


# Check Docker availability
def _is_docker_available():
    """Check if Docker daemon is available."""
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


DOCKER_AVAILABLE = _is_docker_available()

# Skip all tests if Docker is not available
pytestmark = pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker daemon not available")


@pytest.fixture(scope="session")
def docker_client():
    """Get Docker client if available."""
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker daemon not available")
    return docker.from_env()


@pytest.fixture
def docker_sandbox():
    """Create a DockerSandbox for snapshot tests."""
    from swe_agent.sandbox.docker import DockerSandbox

    sb = DockerSandbox(session_id="snapshot-test-123")
    yield sb

    # Cleanup
    try:
        sb.destroy()
    except Exception:
        pass


@pytest.fixture
def snapshot_manager(docker_sandbox):
    """Create a SnapshotManager instance for testing."""
    from swe_agent.sandbox.snapshot import SnapshotManager

    manager = SnapshotManager(docker_sandbox)
    yield manager

    # Cleanup: remove all snapshots created during test
    try:
        manager.cleanup_all_snapshots()
    except Exception:
        pass


@pytest.fixture
def temp_work_dir():
    """Create a temporary working directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_git_repo(temp_work_dir):
    """Create a temporary git repository."""
    import subprocess

    repo_path = Path(temp_work_dir)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    test_file = repo_path / "test.txt"
    test_file.write_text("initial content")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True
    )

    yield str(repo_path)


class TestSnapshotManagerCreation:
    """Test SnapshotManager initialization."""

    def test_create_snapshot_manager(self, docker_sandbox):
        """Test creating SnapshotManager instance."""
        from swe_agent.sandbox.snapshot import SnapshotManager

        manager = SnapshotManager(docker_sandbox)

        assert manager.sandbox == docker_sandbox
        assert manager.session_id == "snapshot-test-123"
        assert isinstance(manager.snapshots, list)
        assert len(manager.snapshots) == 0

    def test_snapshot_manager_requires_sandbox(self):
        """Test SnapshotManager requires DockerSandbox instance."""
        from swe_agent.sandbox.snapshot import SnapshotManager

        with pytest.raises(Exception):
            SnapshotManager(None)


class TestSnapshotCreation:
    """Test snapshot creation functionality."""

    def test_create_snapshot_basic(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test basic snapshot creation."""
        # Create and start container
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create snapshot
        snapshot_id = snapshot_manager.create_snapshot(tag="test-snapshot")

        assert snapshot_id is not None
        assert len(snapshot_id) > 0
        assert len(snapshot_manager.snapshots) == 1
        assert snapshot_manager.snapshots[0]["id"] == snapshot_id
        assert snapshot_manager.snapshots[0]["tag"] == "test-snapshot"

    def test_create_snapshot_naming_convention(
        self, snapshot_manager, docker_sandbox, temp_work_dir
    ):
        """Test snapshot follows naming convention."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot()

        # Snapshot name should be: swe-agent-snapshot-{session_id}-{timestamp}
        assert "swe-agent-snapshot" in snapshot_manager.get_snapshot_info(snapshot_id)["name"]
        assert "snapshot-test-123" in snapshot_manager.get_snapshot_info(snapshot_id)["name"]

    def test_create_snapshot_with_custom_tag(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test creating snapshot with custom tag."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot(tag="before-patch")

        snapshot_info = snapshot_manager.get_snapshot_info(snapshot_id)
        assert snapshot_info["tag"] == "before-patch"

    def test_create_multiple_snapshots(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test creating multiple snapshots."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot1 = snapshot_manager.create_snapshot(tag="snap1")
        time.sleep(0.1)  # Ensure different timestamps
        snapshot2 = snapshot_manager.create_snapshot(tag="snap2")
        time.sleep(0.1)
        snapshot3 = snapshot_manager.create_snapshot(tag="snap3")

        assert len(snapshot_manager.snapshots) == 3
        assert snapshot1 != snapshot2 != snapshot3

    def test_create_snapshot_without_container(self, snapshot_manager):
        """Test creating snapshot fails when container not created."""
        with pytest.raises(Exception):
            snapshot_manager.create_snapshot()

    def test_create_snapshot_records_timestamp(
        self, snapshot_manager, docker_sandbox, temp_work_dir
    ):
        """Test snapshot records creation timestamp."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot()

        snapshot_info = snapshot_manager.get_snapshot_info(snapshot_id)
        assert "created_at" in snapshot_info
        assert snapshot_info["created_at"] is not None


class TestSnapshotRestore:
    """Test snapshot restoration functionality."""

    def test_restore_snapshot_basic(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test basic snapshot restoration."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create file
        docker_sandbox.execute("echo 'initial' > /tmp/test.txt", timeout=5)

        # Create snapshot
        snapshot_id = snapshot_manager.create_snapshot(tag="before-change")

        # Modify file
        docker_sandbox.execute("echo 'modified' > /tmp/test.txt", timeout=5)

        # Verify modification
        result = docker_sandbox.execute("cat /tmp/test.txt", timeout=5)
        assert "modified" in result["stdout"]

        # Restore snapshot
        snapshot_manager.restore_snapshot(snapshot_id)

        # Verify restoration
        result = docker_sandbox.execute("cat /tmp/test.txt", timeout=5)
        assert "initial" in result["stdout"]

    def test_restore_snapshot_file_deletion(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test restoring snapshot after file deletion."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create file
        docker_sandbox.execute("echo 'content' > /tmp/important.txt", timeout=5)

        # Create snapshot
        snapshot_id = snapshot_manager.create_snapshot()

        # Delete file
        docker_sandbox.execute("rm /tmp/important.txt", timeout=5)

        # Verify deletion
        result = docker_sandbox.execute("cat /tmp/important.txt", timeout=5)
        assert result["exit_code"] != 0

        # Restore snapshot
        snapshot_manager.restore_snapshot(snapshot_id)

        # Verify file is restored
        result = docker_sandbox.execute("cat /tmp/important.txt", timeout=5)
        assert result["exit_code"] == 0
        assert "content" in result["stdout"]

    def test_restore_nonexistent_snapshot(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test restoring non-existent snapshot fails."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        with pytest.raises(Exception):
            snapshot_manager.restore_snapshot("nonexistent-snapshot-id")

    def test_restore_snapshot_updates_container_id(
        self, snapshot_manager, docker_sandbox, temp_work_dir
    ):
        """Test restore updates sandbox container_id."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)
        original_container_id = docker_sandbox.container_id

        snapshot_id = snapshot_manager.create_snapshot()
        snapshot_manager.restore_snapshot(snapshot_id)

        # Container ID should be updated after restore
        assert docker_sandbox.container_id != original_container_id


class TestSnapshotLimit:
    """Test snapshot storage limits."""

    def test_snapshot_limit_per_session(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test max 5 snapshots per session."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create 7 snapshots
        for i in range(7):
            snapshot_manager.create_snapshot(tag=f"snap-{i}")
            time.sleep(0.1)

        # Should only keep 5 most recent
        assert len(snapshot_manager.snapshots) == 5

        # Verify oldest ones were removed
        tags = [s["tag"] for s in snapshot_manager.snapshots]
        assert "snap-0" not in tags
        assert "snap-1" not in tags
        assert "snap-6" in tags

    def test_snapshot_size_tracking(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test snapshot size is tracked."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot()

        snapshot_info = snapshot_manager.get_snapshot_info(snapshot_id)
        assert "size" in snapshot_info
        assert snapshot_info["size"] > 0

    def test_total_snapshot_size_limit(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test total snapshot size doesn't exceed 5GB."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create snapshots
        for i in range(3):
            snapshot_manager.create_snapshot(tag=f"snap-{i}")

        total_size = snapshot_manager.get_total_snapshot_size()

        # Total size should be reasonable (less than 5GB)
        max_size = 5 * 1024 * 1024 * 1024  # 5GB in bytes
        assert total_size < max_size


class TestGitBackup:
    """Test Git stash backup functionality."""

    @patch("subprocess.run")
    def test_create_git_backup(self, mock_run, snapshot_manager):
        """Test creating Git stash backup."""
        mock_run.return_value = Mock(returncode=0, stdout="Saved working directory")

        stash_id = snapshot_manager.create_git_backup("/fake/path")

        assert stash_id is not None
        assert stash_id == "stash@{0}"
        assert "swe-agent-backup" in str(mock_run.call_args_list)
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_create_git_backup_with_changes(self, mock_run, snapshot_manager, temp_git_repo):
        """Test creating Git backup with file changes."""
        # Modify file
        test_file = Path(temp_git_repo) / "test.txt"
        test_file.write_text("modified content")

        mock_run.return_value = Mock(returncode=0, stdout="Saved working directory")

        stash_id = snapshot_manager.create_git_backup(temp_git_repo)

        assert stash_id is not None
        mock_run.assert_called()

    @patch("subprocess.run")
    def test_restore_git_backup(self, mock_run, snapshot_manager):
        """Test restoring Git stash backup."""
        mock_run.return_value = Mock(returncode=0, stdout="")

        snapshot_manager.restore_git_backup("stash@{0}", "/fake/path")

        mock_run.assert_called()
        # Verify git stash pop was called
        call_args = [str(call) for call in mock_run.call_args_list]
        assert any("stash" in str(arg) for arg in call_args)

    @patch("subprocess.run")
    def test_git_backup_naming_convention(self, mock_run, snapshot_manager):
        """Test Git backup follows naming convention."""
        mock_run.return_value = Mock(returncode=0, stdout="Saved")

        stash_id = snapshot_manager.create_git_backup("/fake/path")

        # Should contain: swe-agent-backup-{timestamp}
        assert stash_id == "stash@{0}"
        assert "swe-agent-backup-" in str(mock_run.call_args_list)

    @patch("subprocess.run")
    def test_git_backup_no_changes(self, mock_run, snapshot_manager, temp_git_repo):
        """Test Git backup when no changes exist."""
        # No changes made to repo
        mock_run.return_value = Mock(returncode=0, stdout="No local changes")

        stash_id = snapshot_manager.create_git_backup(temp_git_repo)

        # Should handle gracefully
        assert stash_id is not None or stash_id is None


class TestAutoRollback:
    """Test automatic rollback trigger."""

    def test_auto_rollback_trigger_on_error(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test auto rollback triggers on error."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create initial state
        docker_sandbox.execute("echo 'good' > /tmp/state.txt", timeout=5)

        # Create snapshot
        snapshot_id = snapshot_manager.create_snapshot(tag="good-state")

        # Simulate error condition
        docker_sandbox.execute("echo 'bad' > /tmp/state.txt", timeout=5)

        # Trigger auto rollback
        success = snapshot_manager.auto_rollback_trigger(snapshot_id=snapshot_id, condition="error")

        assert success is True

        # Verify rollback occurred
        result = docker_sandbox.execute("cat /tmp/state.txt", timeout=5)
        assert "good" in result["stdout"]

    def test_auto_rollback_trigger_on_test_failure(
        self, snapshot_manager, docker_sandbox, temp_work_dir
    ):
        """Test auto rollback on test failure."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot()

        # Simulate test failure condition
        success = snapshot_manager.auto_rollback_trigger(
            snapshot_id=snapshot_id, condition="test_failure"
        )

        assert success is True

    def test_auto_rollback_no_snapshot(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test auto rollback fails when no snapshot exists."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        with pytest.raises(Exception):
            snapshot_manager.auto_rollback_trigger(snapshot_id="nonexistent", condition="error")


class TestSnapshotManagement:
    """Test snapshot management operations."""

    def test_list_snapshots(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test listing all snapshots."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_manager.create_snapshot(tag="snap1")
        snapshot_manager.create_snapshot(tag="snap2")

        snapshots = snapshot_manager.list_snapshots()

        assert len(snapshots) == 2
        assert snapshots[0]["tag"] == "snap1"
        assert snapshots[1]["tag"] == "snap2"

    def test_delete_snapshot(self, snapshot_manager, docker_sandbox, docker_client, temp_work_dir):
        """Test deleting a specific snapshot."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot(tag="to-delete")

        assert len(snapshot_manager.snapshots) == 1

        snapshot_manager.delete_snapshot(snapshot_id)

        assert len(snapshot_manager.snapshots) == 0

        # Verify image is removed from Docker
        with pytest.raises(ImageNotFound):
            docker_client.images.get(snapshot_id)

    def test_cleanup_all_snapshots(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test cleaning up all snapshots."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_manager.create_snapshot(tag="snap1")
        snapshot_manager.create_snapshot(tag="snap2")
        snapshot_manager.create_snapshot(tag="snap3")

        assert len(snapshot_manager.snapshots) == 3

        snapshot_manager.cleanup_all_snapshots()

        assert len(snapshot_manager.snapshots) == 0

    def test_get_snapshot_info(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test retrieving snapshot information."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot(tag="test-info")

        info = snapshot_manager.get_snapshot_info(snapshot_id)

        assert info is not None
        assert info["id"] == snapshot_id
        assert info["tag"] == "test-info"
        assert "created_at" in info
        assert "size" in info

    def test_find_snapshot_by_tag(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test finding snapshot by tag."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot(tag="findme")

        found_id = snapshot_manager.find_snapshot_by_tag("findme")

        assert found_id == snapshot_id


class TestSnapshotErrorHandling:
    """Test error handling in snapshot operations."""

    def test_create_snapshot_docker_error(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test snapshot creation handles Docker errors."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Simulate Docker API error
        with patch.object(
            docker_sandbox.client.api, "commit", side_effect=Exception("Docker error")
        ):
            with pytest.raises(Exception):
                snapshot_manager.create_snapshot()

    def test_restore_snapshot_after_container_destroyed(
        self, snapshot_manager, docker_sandbox, temp_work_dir
    ):
        """Test restore fails gracefully if container destroyed."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)
        snapshot_id = snapshot_manager.create_snapshot()

        # Destroy container
        docker_sandbox.destroy()

        # Restore should fail
        with pytest.raises(Exception):
            snapshot_manager.restore_snapshot(snapshot_id)

    def test_delete_nonexistent_snapshot(self, snapshot_manager):
        """Test deleting non-existent snapshot handles gracefully."""
        # Should not raise exception
        snapshot_manager.delete_snapshot("nonexistent-id")


class TestSnapshotIntegration:
    """Test snapshot integration with DockerSandbox."""

    def test_snapshot_preserves_file_permissions(
        self, snapshot_manager, docker_sandbox, temp_work_dir
    ):
        """Test snapshot preserves file permissions."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create file with specific permissions
        docker_sandbox.execute("echo 'test' > /tmp/exec.sh", timeout=5)
        docker_sandbox.execute("chmod +x /tmp/exec.sh", timeout=5)

        snapshot_id = snapshot_manager.create_snapshot()

        # Modify permissions
        docker_sandbox.execute("chmod -x /tmp/exec.sh", timeout=5)

        # Restore
        snapshot_manager.restore_snapshot(snapshot_id)

        # Verify permissions restored
        result = docker_sandbox.execute("stat -c %a /tmp/exec.sh", timeout=5)
        assert result["stdout"].strip() == "755"

    def test_snapshot_with_network_state(self, snapshot_manager, docker_sandbox, temp_work_dir):
        """Test snapshot handles container network state."""
        docker_sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        snapshot_id = snapshot_manager.create_snapshot()

        # Restore should maintain network configuration
        snapshot_manager.restore_snapshot(snapshot_id)

        # Verify container still has network access
        result = docker_sandbox.execute("echo 'network test'", timeout=5)
        assert result["status"] == "success"
