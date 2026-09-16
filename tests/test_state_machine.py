"""Tests for state machine implementation.

Test coverage:
- State initialization
- Valid state transitions
- Invalid state transitions
- State persistence (save/load)
- State history tracking
- Recovery from any stage
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from swe_agent.orchestrator.state_machine import StateMachine, State


class TestStateMachineInitialization:
    """Test state machine initialization."""

    def test_initial_state_is_idle(self):
        """Test that new state machine starts in IDLE state."""
        sm = StateMachine(session_id="test-session")
        assert sm.get_current_state() == State.IDLE

    def test_session_id_is_stored(self):
        """Test that session ID is properly stored."""
        sm = StateMachine(session_id="test-session-123")
        assert sm.session_id == "test-session-123"

    def test_history_starts_empty(self):
        """Test that history starts with only initial state."""
        sm = StateMachine(session_id="test-session")
        history = sm.get_history()
        assert len(history) == 1
        assert history[0]["state"] == State.IDLE.value

    def test_metadata_can_be_initialized(self):
        """Test that metadata can be provided during initialization."""
        metadata = {"issue_id": "123", "repo": "test/repo"}
        sm = StateMachine(session_id="test-session", metadata=metadata)
        state_data = sm.to_dict()
        assert state_data["metadata"] == metadata


class TestValidStateTransitions:
    """Test all valid state transitions."""

    def test_idle_to_localizing(self):
        """Test IDLE -> LOCALIZING transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        assert sm.get_current_state() == State.LOCALIZING

    def test_localizing_to_reproducing(self):
        """Test LOCALIZING -> REPRODUCING transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        assert sm.get_current_state() == State.REPRODUCING

    def test_localizing_to_failed(self):
        """Test LOCALIZING -> FAILED transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.FAILED)
        assert sm.get_current_state() == State.FAILED

    def test_reproducing_to_patching(self):
        """Test REPRODUCING -> PATCHING transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        assert sm.get_current_state() == State.PATCHING

    def test_reproducing_to_failed(self):
        """Test REPRODUCING -> FAILED transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.FAILED)
        assert sm.get_current_state() == State.FAILED

    def test_patching_to_validating(self):
        """Test PATCHING -> VALIDATING transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        sm.transition(State.VALIDATING)
        assert sm.get_current_state() == State.VALIDATING

    def test_patching_to_failed(self):
        """Test PATCHING -> FAILED transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        sm.transition(State.FAILED)
        assert sm.get_current_state() == State.FAILED

    def test_validating_to_done(self):
        """Test VALIDATING -> DONE transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        sm.transition(State.VALIDATING)
        sm.transition(State.DONE)
        assert sm.get_current_state() == State.DONE

    def test_validating_to_patching_rollback(self):
        """Test VALIDATING -> PATCHING rollback transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        sm.transition(State.VALIDATING)
        sm.transition(State.PATCHING)
        assert sm.get_current_state() == State.PATCHING

    def test_validating_to_failed(self):
        """Test VALIDATING -> FAILED transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        sm.transition(State.VALIDATING)
        sm.transition(State.FAILED)
        assert sm.get_current_state() == State.FAILED


class TestInvalidStateTransitions:
    """Test invalid state transitions are rejected."""

    def test_idle_to_reproducing_invalid(self):
        """Test IDLE -> REPRODUCING is invalid."""
        sm = StateMachine(session_id="test-session")
        assert not sm.can_transition(State.REPRODUCING)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(State.REPRODUCING)

    def test_idle_to_done_invalid(self):
        """Test IDLE -> DONE is invalid."""
        sm = StateMachine(session_id="test-session")
        assert not sm.can_transition(State.DONE)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(State.DONE)

    def test_localizing_to_patching_invalid(self):
        """Test LOCALIZING -> PATCHING is invalid."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        assert not sm.can_transition(State.PATCHING)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition(State.PATCHING)

    def test_failed_is_terminal(self):
        """Test that FAILED state cannot transition to any other state."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.FAILED)

        assert not sm.can_transition(State.IDLE)
        assert not sm.can_transition(State.LOCALIZING)
        with pytest.raises(ValueError, match="Cannot transition from terminal state"):
            sm.transition(State.IDLE)

    def test_done_is_terminal(self):
        """Test that DONE state cannot transition to any other state."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        sm.transition(State.VALIDATING)
        sm.transition(State.DONE)

        assert not sm.can_transition(State.IDLE)
        assert not sm.can_transition(State.PATCHING)
        with pytest.raises(ValueError, match="Cannot transition from terminal state"):
            sm.transition(State.PATCHING)


class TestStateHistory:
    """Test state history tracking."""

    def test_history_records_all_transitions(self):
        """Test that history records every state transition."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)

        history = sm.get_history()
        assert len(history) == 4  # IDLE + 3 transitions
        assert history[0]["state"] == State.IDLE.value
        assert history[1]["state"] == State.LOCALIZING.value
        assert history[2]["state"] == State.REPRODUCING.value
        assert history[3]["state"] == State.PATCHING.value

    def test_history_includes_timestamps(self):
        """Test that history entries include timestamps."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)

        history = sm.get_history()
        for entry in history:
            assert "timestamp" in entry
            # Verify timestamp is ISO format
            datetime.fromisoformat(entry["timestamp"])

    def test_transition_with_metadata(self):
        """Test that transition metadata is recorded in history."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING, data={"files_found": 5})

        history = sm.get_history()
        last_entry = history[-1]
        assert last_entry["data"] == {"files_found": 5}

    def test_history_preserves_order(self):
        """Test that history maintains chronological order."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)
        sm.transition(State.REPRODUCING)
        sm.transition(State.PATCHING)
        sm.transition(State.VALIDATING)
        sm.transition(State.PATCHING)  # Rollback

        history = sm.get_history()
        timestamps = [datetime.fromisoformat(e["timestamp"]) for e in history]
        assert timestamps == sorted(timestamps)


class TestStatePersistence:
    """Test state save/load functionality."""

    def test_save_state_to_store(self):
        """Test saving state to StateStore."""
        sm = StateMachine(session_id="test-session")
        sm.transition(State.LOCALIZING)

        mock_store = Mock()
        sm.save_state(mock_store)

        mock_store.save_metadata.assert_called_once()
        call_args = mock_store.save_metadata.call_args
        assert call_args[0][0] == "test-session"

        saved_data = call_args[0][1]
        assert saved_data["current_state"] == State.LOCALIZING.value
        assert saved_data["session_id"] == "test-session"
        assert "history" in saved_data

    def test_load_state_from_store(self):
        """Test loading state from StateStore."""
        # Create initial state machine and save
        sm1 = StateMachine(session_id="test-session")
        sm1.transition(State.LOCALIZING)
        sm1.transition(State.REPRODUCING)

        saved_data = sm1.to_dict()

        # Mock store to return saved data
        mock_store = Mock()
        mock_store.load_metadata.return_value = saved_data

        # Load into new state machine
        sm2 = StateMachine.load_state(mock_store, "test-session")

        assert sm2.get_current_state() == State.REPRODUCING
        assert sm2.session_id == "test-session"
        assert len(sm2.get_history()) == 3  # IDLE + 2 transitions

    def test_load_nonexistent_session_returns_none(self):
        """Test loading non-existent session returns None."""
        mock_store = Mock()
        mock_store.load_metadata.return_value = {}

        sm = StateMachine.load_state(mock_store, "nonexistent")
        assert sm is None

    def test_save_preserves_metadata(self):
        """Test that save/load preserves custom metadata."""
        metadata = {"issue_id": "456", "repo": "test/repo"}
        sm1 = StateMachine(session_id="test-session", metadata=metadata)
        sm1.transition(State.LOCALIZING)

        saved_data = sm1.to_dict()

        mock_store = Mock()
        mock_store.load_metadata.return_value = saved_data

        sm2 = StateMachine.load_state(mock_store, "test-session")
        assert sm2.to_dict()["metadata"] == metadata


class TestStateRecovery:
    """Test recovery from any stage."""

    def test_recover_from_localizing(self):
        """Test recovery from LOCALIZING stage."""
        sm1 = StateMachine(session_id="test-session")
        sm1.transition(State.LOCALIZING)

        saved_data = sm1.to_dict()
        mock_store = Mock()
        mock_store.load_metadata.return_value = saved_data

        sm2 = StateMachine.load_state(mock_store, "test-session")
        assert sm2.get_current_state() == State.LOCALIZING
        # Should be able to continue
        sm2.transition(State.REPRODUCING)
        assert sm2.get_current_state() == State.REPRODUCING

    def test_recover_from_patching(self):
        """Test recovery from PATCHING stage."""
        sm1 = StateMachine(session_id="test-session")
        sm1.transition(State.LOCALIZING)
        sm1.transition(State.REPRODUCING)
        sm1.transition(State.PATCHING)

        saved_data = sm1.to_dict()
        mock_store = Mock()
        mock_store.load_metadata.return_value = saved_data

        sm2 = StateMachine.load_state(mock_store, "test-session")
        assert sm2.get_current_state() == State.PATCHING
        # Should be able to continue
        sm2.transition(State.VALIDATING)
        assert sm2.get_current_state() == State.VALIDATING

    def test_recover_from_validating(self):
        """Test recovery from VALIDATING stage."""
        sm1 = StateMachine(session_id="test-session")
        sm1.transition(State.LOCALIZING)
        sm1.transition(State.REPRODUCING)
        sm1.transition(State.PATCHING)
        sm1.transition(State.VALIDATING)

        saved_data = sm1.to_dict()
        mock_store = Mock()
        mock_store.load_metadata.return_value = saved_data

        sm2 = StateMachine.load_state(mock_store, "test-session")
        assert sm2.get_current_state() == State.VALIDATING
        # Should be able to complete or rollback
        sm2.transition(State.DONE)
        assert sm2.get_current_state() == State.DONE

    def test_recover_terminal_state(self):
        """Test recovery from terminal states."""
        sm1 = StateMachine(session_id="test-session")
        sm1.transition(State.LOCALIZING)
        sm1.transition(State.FAILED)

        saved_data = sm1.to_dict()
        mock_store = Mock()
        mock_store.load_metadata.return_value = saved_data

        sm2 = StateMachine.load_state(mock_store, "test-session")
        assert sm2.get_current_state() == State.FAILED
        # Cannot transition from terminal state
        assert not sm2.can_transition(State.LOCALIZING)


class TestStateMachineEdgeCases:
    """Test edge cases and error handling."""

    def test_can_transition_check_before_transition(self):
        """Test that can_transition correctly predicts transition validity."""
        sm = StateMachine(session_id="test-session")

        # Valid transition
        assert sm.can_transition(State.LOCALIZING)
        sm.transition(State.LOCALIZING)

        # Invalid transition
        assert not sm.can_transition(State.DONE)

    def test_to_dict_structure(self):
        """Test that to_dict returns expected structure."""
        sm = StateMachine(session_id="test-session", metadata={"test": "data"})
        sm.transition(State.LOCALIZING)

        data = sm.to_dict()
        assert "current_state" in data
        assert "history" in data
        assert "session_id" in data
        assert "metadata" in data
        assert data["session_id"] == "test-session"
        assert data["metadata"]["test"] == "data"

    def test_transition_to_same_state_invalid(self):
        """Test that transitioning to current state is invalid."""
        sm = StateMachine(session_id="test-session")
        assert not sm.can_transition(State.IDLE)
        with pytest.raises(ValueError):
            sm.transition(State.IDLE)
