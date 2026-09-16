"""Tests for state storage layer (Task 0.4)."""

import json
import time
from pathlib import Path

import pytest

from swe_agent.storage import StateStore
from swe_agent.types import LocalizationResult, StageStatus


class TestStateStoreInitialization:
    """Test StateStore initialization."""

    def test_create_state_store(self, tmp_path):
        """Test creating a StateStore instance."""
        store = StateStore(base_path=tmp_path)
        assert store is not None
        assert store.base_path == tmp_path

    def test_state_store_creates_base_directory(self, tmp_path):
        """Test that StateStore creates base directory."""
        base_path = tmp_path / "test-storage"
        store = StateStore(base_path=base_path)

        assert base_path.exists()
        assert base_path.is_dir()

    def test_state_store_creates_sessions_directory(self, tmp_path):
        """Test that sessions directory is created."""
        store = StateStore(base_path=tmp_path)
        sessions_path = tmp_path / "sessions"

        assert sessions_path.exists()
        assert sessions_path.is_dir()


class TestSessionManagement:
    """Test session directory management."""

    def test_create_session(self, tmp_path):
        """Test creating a new session."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session-123"

        session_path = store.create_session(session_id)

        assert session_path.exists()
        assert session_path.is_dir()
        assert session_path.name == session_id

    def test_session_directory_structure(self, tmp_path):
        """Test that session has correct directory structure."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session-456"

        store.create_session(session_id)
        session_path = tmp_path / "sessions" / session_id

        # Should have metadata file
        metadata_file = session_path / "metadata.json"
        assert metadata_file.exists()

    def test_get_session_path(self, tmp_path):
        """Test getting session path."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session-789"

        store.create_session(session_id)
        session_path = store.get_session_path(session_id)

        assert session_path == tmp_path / "sessions" / session_id

    def test_session_exists(self, tmp_path):
        """Test checking if session exists."""
        store = StateStore(base_path=tmp_path)
        session_id = "existing-session"

        assert not store.session_exists(session_id)

        store.create_session(session_id)

        assert store.session_exists(session_id)


class TestStageResultStorage:
    """Test saving and loading stage results."""

    def test_save_stage_result(self, tmp_path):
        """Test saving a stage result."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        result = LocalizationResult(
            status="success",
            candidates=[],
            search_strategy="test",
            execution_time=1.0,
            tool_calls=5,
        )

        store.save_stage_result(session_id, "localization", result)

        result_file = tmp_path / "sessions" / session_id / "stage_1_localization.json"
        assert result_file.exists()

    def test_load_stage_result(self, tmp_path):
        """Test loading a stage result."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        original_result = LocalizationResult(
            status="success",
            candidates=[{"file_path": "test.py", "confidence": 0.9}],
            search_strategy="stack_trace",
            execution_time=2.5,
            tool_calls=3,
        )

        store.save_stage_result(session_id, "localization", original_result)
        loaded_result = store.load_stage_result(session_id, "localization")

        assert loaded_result is not None
        assert loaded_result["status"] == "success"
        assert loaded_result["execution_time"] == 2.5

    def test_load_nonexistent_stage_result(self, tmp_path):
        """Test loading a stage result that doesn't exist."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        result = store.load_stage_result(session_id, "nonexistent_stage")

        assert result is None

    def test_save_multiple_stage_results(self, tmp_path):
        """Test saving multiple stage results."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        stages = ["localization", "reproduction", "patch_generation"]

        for stage in stages:
            result = {"stage": stage, "status": "success"}
            store.save_stage_result(session_id, stage, result)

        # All stage files should exist
        for i, stage in enumerate(stages, 1):
            result_file = tmp_path / "sessions" / session_id / f"stage_{i}_{stage}.json"
            assert result_file.exists()


class TestLogStorage:
    """Test execution log storage."""

    def test_append_log(self, tmp_path):
        """Test appending to execution log."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        log_entry = {
            "timestamp": "2026-09-16T10:00:00Z",
            "event": "tool_call",
            "tool": "ripgrep_search",
        }

        store.append_log(session_id, log_entry)

        log_file = tmp_path / "sessions" / session_id / "execution_log.jsonl"
        assert log_file.exists()

    def test_append_multiple_logs(self, tmp_path):
        """Test appending multiple log entries."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        log_entries = [
            {"event": "start", "stage": "localization"},
            {"event": "tool_call", "tool": "search"},
            {"event": "end", "stage": "localization"},
        ]

        for entry in log_entries:
            store.append_log(session_id, entry)

        log_file = tmp_path / "sessions" / session_id / "execution_log.jsonl"
        lines = log_file.read_text().strip().split("\n")

        assert len(lines) == 3

        # Verify each line is valid JSON
        for line in lines:
            parsed = json.loads(line)
            assert "event" in parsed

    def test_read_logs(self, tmp_path):
        """Test reading execution logs."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        log_entries = [
            {"id": 1, "message": "first"},
            {"id": 2, "message": "second"},
        ]

        for entry in log_entries:
            store.append_log(session_id, entry)

        logs = store.read_logs(session_id)

        assert len(logs) == 2
        assert logs[0]["id"] == 1
        assert logs[1]["id"] == 2


class TestSessionListing:
    """Test listing sessions."""

    def test_list_sessions_empty(self, tmp_path):
        """Test listing sessions when none exist."""
        store = StateStore(base_path=tmp_path)

        sessions = store.list_sessions()

        assert sessions == []

    def test_list_sessions(self, tmp_path):
        """Test listing existing sessions."""
        store = StateStore(base_path=tmp_path)

        session_ids = ["session-1", "session-2", "session-3"]
        for session_id in session_ids:
            store.create_session(session_id)

        sessions = store.list_sessions()

        assert len(sessions) == 3
        assert all(s in sessions for s in session_ids)

    def test_list_sessions_sorted_by_creation_time(self, tmp_path):
        """Test that sessions are sorted by creation time."""
        store = StateStore(base_path=tmp_path)

        # Create sessions with small delays
        session_ids = ["oldest", "middle", "newest"]
        for session_id in session_ids:
            store.create_session(session_id)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        sessions = store.list_sessions()

        # Should be sorted oldest to newest
        assert len(sessions) == 3


class TestSessionCleanup:
    """Test FIFO session cleanup."""

    def test_cleanup_old_sessions(self, tmp_path):
        """Test that old sessions are cleaned up."""
        store = StateStore(base_path=tmp_path, max_sessions=3)

        # Create 5 sessions
        for i in range(5):
            store.create_session(f"session-{i}")
            time.sleep(0.01)

        # Should only keep 3 most recent
        store.cleanup_old_sessions()

        sessions = store.list_sessions()
        assert len(sessions) == 3

        # Should keep newest sessions
        assert "session-2" in sessions
        assert "session-3" in sessions
        assert "session-4" in sessions

        # Should have removed oldest
        assert "session-0" not in sessions
        assert "session-1" not in sessions

    def test_cleanup_respects_max_sessions(self, tmp_path):
        """Test that cleanup respects max_sessions limit."""
        store = StateStore(base_path=tmp_path, max_sessions=5)

        # Create exactly max_sessions
        for i in range(5):
            store.create_session(f"session-{i}")

        store.cleanup_old_sessions()

        sessions = store.list_sessions()
        assert len(sessions) == 5

    def test_no_cleanup_if_under_limit(self, tmp_path):
        """Test that no cleanup happens if under limit."""
        store = StateStore(base_path=tmp_path, max_sessions=10)

        # Create only 3 sessions
        for i in range(3):
            store.create_session(f"session-{i}")

        store.cleanup_old_sessions()

        sessions = store.list_sessions()
        assert len(sessions) == 3


class TestDiskQuota:
    """Test disk quota enforcement."""

    def test_get_session_size(self, tmp_path):
        """Test calculating session disk usage."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        # Write some data
        large_data = {"data": "x" * 1000}
        store.save_stage_result(session_id, "test_stage", large_data)

        size = store.get_session_size(session_id)

        assert size > 0

    def test_check_disk_quota(self, tmp_path):
        """Test disk quota checking."""
        # Set a small quota for testing
        store = StateStore(base_path=tmp_path, max_session_size=10000)  # 10KB
        session_id = "test-session"
        store.create_session(session_id)

        # Should be under quota initially
        assert store.check_disk_quota(session_id)

    def test_disk_quota_exceeded(self, tmp_path):
        """Test detecting when disk quota is exceeded."""
        # Very small quota
        store = StateStore(base_path=tmp_path, max_session_size=100)  # 100 bytes
        session_id = "test-session"
        store.create_session(session_id)

        # Write data that exceeds quota
        large_data = {"data": "x" * 1000}
        store.save_stage_result(session_id, "test_stage", large_data)

        # Should detect quota exceeded
        assert not store.check_disk_quota(session_id)


class TestSessionMetadata:
    """Test session metadata management."""

    def test_save_session_metadata(self, tmp_path):
        """Test saving session metadata."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        metadata = {
            "issue_id": "123",
            "repository": "/path/to/repo",
            "started_at": "2026-09-16T10:00:00Z",
        }

        store.save_metadata(session_id, metadata)

        metadata_file = tmp_path / "sessions" / session_id / "metadata.json"
        assert metadata_file.exists()

        loaded = json.loads(metadata_file.read_text())
        assert loaded["issue_id"] == "123"

    def test_load_session_metadata(self, tmp_path):
        """Test loading session metadata."""
        store = StateStore(base_path=tmp_path)
        session_id = "test-session"
        store.create_session(session_id)

        metadata = {
            "issue_id": "456",
            "status": "running",
        }

        store.save_metadata(session_id, metadata)
        loaded = store.load_metadata(session_id)

        assert loaded["issue_id"] == "456"
        assert loaded["status"] == "running"
