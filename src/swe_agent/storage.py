"""State storage layer for SWE Agent.

This module provides persistent storage for pipeline execution state.
Based on SYSTEM_DESIGN.md Section 3.8: Storage Layer.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from swe_agent.logging import get_logger

logger = get_logger(__name__)


class StateStore:
    """Manages persistent storage of pipeline state and execution logs.

    Storage structure:
        .swe-agent/
        └── sessions/
            └── {session_id}/
                ├── metadata.json
                ├── stage_1_localization.json
                ├── stage_2_reproduction.json
                ├── stage_3_patch_generation.json
                ├── stage_4_validation.json
                └── execution_log.jsonl
    """

    def __init__(
        self,
        base_path: Path = Path(".swe-agent"),
        max_sessions: int = 100,
        max_session_size: int = 1024 * 1024 * 1024,  # 1GB
    ):
        """Initialize StateStore.

        Args:
            base_path: Base directory for storage
            max_sessions: Maximum number of sessions to retain (FIFO)
            max_session_size: Maximum size per session in bytes
        """
        self.base_path = Path(base_path)
        self.max_sessions = max_sessions
        self.max_session_size = max_session_size

        # Create base directories
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.sessions_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "state_store_initialized",
            base_path=str(self.base_path),
            max_sessions=max_sessions,
        )

    @property
    def sessions_path(self) -> Path:
        """Get the sessions directory path."""
        return self.base_path / "sessions"

    def create_session(self, session_id: str) -> Path:
        """Create a new session directory.

        Args:
            session_id: Unique session identifier

        Returns:
            Path to the created session directory
        """
        session_path = self.sessions_path / session_id
        session_path.mkdir(parents=True, exist_ok=True)

        # Create initial metadata
        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
        }
        self.save_metadata(session_id, metadata)

        logger.info("session_created", session_id=session_id)
        return session_path

    def get_session_path(self, session_id: str) -> Path:
        """Get path to a session directory.

        Args:
            session_id: Session identifier

        Returns:
            Path to the session directory
        """
        return self.sessions_path / session_id

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: Session identifier

        Returns:
            True if session exists
        """
        return self.get_session_path(session_id).exists()

    def load_state(self, session_id: str):
        from swe_agent.orchestrator.pipeline import PipelineOrchestrator

        return PipelineOrchestrator.resume(session_id, self).get_state()

    def save_stage_result(
        self,
        session_id: str,
        stage: str,
        result: Any,
    ) -> None:
        """Save a stage result to disk.

        Args:
            session_id: Session identifier
            stage: Stage name (localization, reproduction, etc.)
            result: Stage result (Pydantic model or dict)
        """
        session_path = self.get_session_path(session_id)
        if not session_path.exists():
            raise ValueError(f"Session {session_id} does not exist")

        # Map stage names to file numbers
        stage_numbers = {
            "localization": 1,
            "reproduction": 2,
            "patch_generation": 3,
            "validation": 4,
        }

        stage_num = stage_numbers.get(stage, 0)
        filename = f"stage_{stage_num}_{stage}.json"
        result_file = session_path / filename

        # Convert Pydantic model to dict if needed
        if isinstance(result, BaseModel):
            result_data = result.model_dump()
        else:
            result_data = result

        # Write result
        result_file.write_text(json.dumps(result_data, indent=2))

        logger.debug(
            "stage_result_saved",
            session_id=session_id,
            stage=stage,
            file=filename,
        )

    def load_stage_result(
        self,
        session_id: str,
        stage: str,
    ) -> Optional[Dict[str, Any]]:
        """Load a stage result from disk.

        Args:
            session_id: Session identifier
            stage: Stage name

        Returns:
            Stage result as dictionary, or None if not found
        """
        session_path = self.get_session_path(session_id)
        if not session_path.exists():
            return None

        # Map stage names to file numbers
        stage_numbers = {
            "localization": 1,
            "reproduction": 2,
            "patch_generation": 3,
            "validation": 4,
        }

        stage_num = stage_numbers.get(stage, 0)
        filename = f"stage_{stage_num}_{stage}.json"
        result_file = session_path / filename

        if not result_file.exists():
            return None

        try:
            return json.loads(result_file.read_text())
        except Exception as e:
            logger.error(
                "failed_to_load_stage_result",
                session_id=session_id,
                stage=stage,
                error=str(e),
            )
            return None

    def append_log(
        self,
        session_id: str,
        log_entry: Dict[str, Any],
    ) -> None:
        """Append an entry to the execution log.

        Args:
            session_id: Session identifier
            log_entry: Log entry as dictionary
        """
        session_path = self.get_session_path(session_id)
        if not session_path.exists():
            raise ValueError(f"Session {session_id} does not exist")

        log_file = session_path / "execution_log.jsonl"

        # Append as JSON Lines
        with log_file.open("a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def read_logs(self, session_id: str) -> List[Dict[str, Any]]:
        """Read all log entries for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of log entries
        """
        session_path = self.get_session_path(session_id)
        log_file = session_path / "execution_log.jsonl"

        if not log_file.exists():
            return []

        logs = []
        with log_file.open("r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return logs

    def save_metadata(
        self,
        session_id: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Save session metadata.

        Args:
            session_id: Session identifier
            metadata: Metadata dictionary
        """
        session_path = self.get_session_path(session_id)
        metadata_file = session_path / "metadata.json"

        metadata_file.write_text(json.dumps(metadata, indent=2))

    def load_metadata(self, session_id: str) -> Dict[str, Any]:
        """Load session metadata.

        Args:
            session_id: Session identifier

        Returns:
            Metadata dictionary
        """
        session_path = self.get_session_path(session_id)
        metadata_file = session_path / "metadata.json"

        if not metadata_file.exists():
            return {}

        try:
            return json.loads(metadata_file.read_text())
        except Exception:
            return {}

    def list_sessions(self) -> List[str]:
        """List all session IDs.

        Returns:
            List of session IDs, sorted by creation time (oldest first)
        """
        if not self.sessions_path.exists():
            return []

        sessions = []
        for session_dir in self.sessions_path.iterdir():
            if session_dir.is_dir():
                sessions.append((session_dir.name, session_dir.stat().st_mtime))

        # Sort by modification time (oldest first)
        sessions.sort(key=lambda x: x[1])

        return [session_id for session_id, _ in sessions]

    def cleanup_old_sessions(self) -> None:
        """Remove old sessions to maintain max_sessions limit (FIFO).

        Keeps the most recent max_sessions sessions and removes older ones.
        """
        sessions = self.list_sessions()

        if len(sessions) <= self.max_sessions:
            return

        # Calculate how many to remove
        num_to_remove = len(sessions) - self.max_sessions

        # Remove oldest sessions
        for session_id in sessions[:num_to_remove]:
            session_path = self.get_session_path(session_id)
            try:
                shutil.rmtree(session_path)
                logger.info("session_removed", session_id=session_id, reason="fifo_cleanup")
            except Exception as e:
                logger.error(
                    "failed_to_remove_session",
                    session_id=session_id,
                    error=str(e),
                )

    def get_session_size(self, session_id: str) -> int:
        """Calculate total disk usage of a session.

        Args:
            session_id: Session identifier

        Returns:
            Size in bytes
        """
        session_path = self.get_session_path(session_id)
        if not session_path.exists():
            return 0

        total_size = 0
        for item in session_path.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size

        return total_size

    def check_disk_quota(self, session_id: str) -> bool:
        """Check if a session is within disk quota.

        Args:
            session_id: Session identifier

        Returns:
            True if under quota, False if exceeded
        """
        size = self.get_session_size(session_id)
        under_quota = size <= self.max_session_size

        if not under_quota:
            logger.warning(
                "disk_quota_exceeded",
                session_id=session_id,
                size=size,
                limit=self.max_session_size,
            )

        return under_quota
