"""State machine for orchestrating SWE Agent pipeline execution.

This module implements a state machine that manages transitions between
different stages of the bug-fixing pipeline.

State transitions:
    IDLE → LOCALIZING
    LOCALIZING → REPRODUCING | FAILED
    REPRODUCING → PATCHING | FAILED
    PATCHING → VALIDATING | FAILED
    VALIDATING → DONE | PATCHING (rollback) | FAILED
    FAILED → terminal state
    DONE → terminal state
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from swe_agent.logging import get_logger

logger = get_logger(__name__)


class State(Enum):
    """Pipeline execution states."""

    IDLE = "idle"
    LOCALIZING = "localizing"
    REPRODUCING = "reproducing"
    PATCHING = "patching"
    VALIDATING = "validating"
    DONE = "done"
    FAILED = "failed"


# Define valid state transitions as a directed graph
STATE_TRANSITIONS = {
    State.IDLE: {State.LOCALIZING},
    State.LOCALIZING: {State.REPRODUCING, State.FAILED},
    State.REPRODUCING: {State.PATCHING, State.FAILED},
    State.PATCHING: {State.VALIDATING, State.FAILED},
    State.VALIDATING: {State.DONE, State.PATCHING, State.FAILED},
    State.DONE: set(),  # Terminal state
    State.FAILED: set(),  # Terminal state
}


class StateMachine:
    """Manages state transitions and persistence for pipeline execution.

    Example:
        >>> sm = StateMachine(session_id="session-123")
        >>> sm.transition(State.LOCALIZING)
        >>> sm.get_current_state()
        <State.LOCALIZING: 'localizing'>
        >>> sm.save_state(store)
    """

    def __init__(self, session_id: str, metadata: Optional[Dict[str, Any]] = None):
        """Initialize state machine.

        Args:
            session_id: Unique session identifier
            metadata: Optional metadata to store with state
        """
        self.session_id = session_id
        self.metadata = metadata or {}
        self._current_state = State.IDLE
        self._history: List[Dict[str, Any]] = []

        # Record initial state
        self._add_history_entry(State.IDLE, data=None)

        logger.info(
            "state_machine_initialized",
            session_id=session_id,
            initial_state=State.IDLE.value,
        )

    def get_current_state(self) -> State:
        """Get the current state.

        Returns:
            Current state enum value
        """
        return self._current_state

    def can_transition(self, to_state: State) -> bool:
        """Check if transition to target state is valid.

        Args:
            to_state: Target state

        Returns:
            True if transition is allowed, False otherwise
        """
        # Cannot transition to same state
        if to_state == self._current_state:
            return False

        # Check if transition is in the allowed transitions
        allowed_transitions = STATE_TRANSITIONS.get(self._current_state, set())
        return to_state in allowed_transitions

    def transition(self, to_state: State, data: Optional[Dict[str, Any]] = None) -> None:
        """Transition to a new state.

        Args:
            to_state: Target state
            data: Optional data to record with this transition

        Raises:
            ValueError: If transition is not allowed
        """
        # Check if we're in a terminal state
        if self._current_state in {State.DONE, State.FAILED}:
            raise ValueError(
                f"Cannot transition from terminal state {self._current_state.value}"
            )

        # Check if transition is valid
        if not self.can_transition(to_state):
            raise ValueError(
                f"Invalid transition from {self._current_state.value} to {to_state.value}"
            )

        old_state = self._current_state
        self._current_state = to_state
        self._add_history_entry(to_state, data)

        logger.info(
            "state_transition",
            session_id=self.session_id,
            from_state=old_state.value,
            to_state=to_state.value,
        )

    def get_history(self) -> List[Dict[str, Any]]:
        """Get the state transition history.

        Returns:
            List of history entries, each containing:
                - state: State name
                - timestamp: ISO format timestamp
                - data: Optional transition data
        """
        return self._history.copy()

    def to_dict(self) -> Dict[str, Any]:
        """Convert state machine to dictionary for serialization.

        Returns:
            Dictionary containing current state, history, session_id, and metadata
        """
        return {
            "current_state": self._current_state.value,
            "history": self._history.copy(),
            "session_id": self.session_id,
            "metadata": self.metadata.copy(),
        }

    def save_state(self, store) -> None:
        """Persist state to StateStore.

        Args:
            store: StateStore instance to save to
        """
        state_data = self.to_dict()
        store.save_metadata(self.session_id, state_data)

        logger.debug(
            "state_saved",
            session_id=self.session_id,
            current_state=self._current_state.value,
        )

    @classmethod
    def load_state(cls, store, session_id: str) -> Optional["StateMachine"]:
        """Load state from StateStore.

        Args:
            store: StateStore instance to load from
            session_id: Session identifier to load

        Returns:
            StateMachine instance if found, None otherwise
        """
        state_data = store.load_metadata(session_id)

        if not state_data or "current_state" not in state_data:
            logger.warning(
                "state_not_found",
                session_id=session_id,
            )
            return None

        # Create instance without calling __init__ to avoid duplicate history
        instance = cls.__new__(cls)
        instance.session_id = session_id
        instance.metadata = state_data.get("metadata", {})
        instance._current_state = State(state_data["current_state"])
        instance._history = state_data.get("history", [])

        logger.info(
            "state_loaded",
            session_id=session_id,
            current_state=instance._current_state.value,
            history_length=len(instance._history),
        )

        return instance

    def _add_history_entry(
        self, state: State, data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add an entry to the state history.

        Args:
            state: State to record
            data: Optional data associated with this state
        """
        entry = {
            "state": state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if data is not None:
            entry["data"] = data

        self._history.append(entry)
