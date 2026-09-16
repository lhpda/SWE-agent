"""Tests for LocalizationAgent.

Implements comprehensive tests for Task 3.3: LocalizationAgent implementation.
Tests cover LLM orchestration, tool calling, result aggregation, and error handling.
"""

import time
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest

from swe_agent.agents.localization.agent import LocalizationAgent
from swe_agent.agents.localization.strategy import SearchCandidate
from swe_agent.types import IssueContext, LocalizationResult, RepositoryContext


@pytest.fixture
def issue_context():
    """Create a sample IssueContext for testing."""
    return IssueContext(
        issue_id="test-123",
        title="Test Issue",
        body="# Bug Report\n\nAttributeError: 'NoneType' object has no attribute 'value'",
        parsed={
            "error_messages": ["AttributeError: 'NoneType' object has no attribute 'value'"],
            "stack_traces": [
                {
                    "language": "python",
                    "files": [
                        {"file": "src/app.py", "line": 42},
                        {"file": "src/utils.py", "line": 15},
                    ],
                    "raw": "Traceback...",
                }
            ],
            "reproduction_steps": ["Run the application", "Click submit button"],
            "expected_behavior": "Should succeed",
            "actual_behavior": "Raises AttributeError",
            "quality": "high",
            "confidence": 0.9,
        },
        metadata={},
    )


@pytest.fixture
def repo_context():
    """Create a sample RepositoryContext for testing."""
    return RepositoryContext(
        path="/tmp/test-repo",
        git={"branch": "main", "commit": "abc123"},
        project_type="python",
        test_framework="pytest",
        dependencies={},
    )


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response structure."""
    return {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "I'll analyze the issue and search for the bug location.",
            }
        ],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }


class TestLocalizationAgentInit:
    """Test LocalizationAgent initialization."""

    def test_init_with_valid_contexts(self, issue_context, repo_context):
        """Test initialization with valid contexts."""
        agent = LocalizationAgent(issue_context, repo_context)

        assert agent.issue_context == issue_context
        assert agent.repo_context == repo_context
        assert agent.tool_call_count == 0
        assert agent.start_time is None

    def test_init_validates_issue_context(self, repo_context):
        """Test that invalid issue context is rejected."""
        with pytest.raises((TypeError, AttributeError)):
            LocalizationAgent(None, repo_context)

    def test_init_validates_repo_context(self, issue_context):
        """Test that invalid repo context is rejected."""
        with pytest.raises((TypeError, AttributeError)):
            LocalizationAgent(issue_context, None)


class TestLocalizationAgentParsing:
    """Test issue parsing functionality."""

    def test_parse_issue_extracts_data(self, issue_context, repo_context):
        """Test that _parse_issue correctly extracts data."""
        agent = LocalizationAgent(issue_context, repo_context)
        parsed = agent._parse_issue()

        assert "error_messages" in parsed
        assert "stack_traces" in parsed
        assert "reproduction_steps" in parsed
        assert len(parsed["error_messages"]) > 0

    def test_parse_issue_handles_minimal_data(self, repo_context):
        """Test parsing with minimal issue data."""
        minimal_issue = IssueContext(
            issue_id="min-1",
            title="Simple issue",
            body="Something is broken",
            parsed={
                "error_messages": [],
                "stack_traces": [],
                "reproduction_steps": [],
                "expected_behavior": None,
                "actual_behavior": None,
                "quality": "vague",
                "confidence": 0.2,
            },
            metadata={},
        )

        agent = LocalizationAgent(minimal_issue, repo_context)
        parsed = agent._parse_issue()

        assert parsed is not None
        assert "error_messages" in parsed


class TestLocalizationAgentSearchStrategies:
    """Test search strategy execution."""

    def test_search_with_strategies_calls_all(self, issue_context, repo_context):
        """Test that all search strategies are called."""
        # Setup mocks
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate(
                file_path="src/app.py",
                confidence=0.9,
                reason="Stack trace",
                relevant_symbols=[],
                code_snippet="",
                line_number=42,
            )
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        parsed_issue = agent._parse_issue()
        candidates = agent._search_with_strategies(parsed_issue)

        # Verify all strategies were called
        mock_stack_instance.search.assert_called_once()
        mock_error_instance.search.assert_called_once()
        mock_symbol_instance.search.assert_called_once()

        assert len(candidates) > 0

    def test_search_aggregates_multiple_results(self, issue_context, repo_context):
        """Test that results from multiple strategies are aggregated."""
        # Setup mocks with different results
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate("src/app.py", 0.9, "Stack", [], "", 42)
        ]
        mock_error_instance.search.return_value = [
            SearchCandidate("src/utils.py", 0.7, "Error msg", [], "", 15)
        ]
        mock_symbol_instance.search.return_value = [
            SearchCandidate("src/models.py", 0.8, "Symbol", [], "", 20)
        ]

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        parsed_issue = agent._parse_issue()
        candidates = agent._search_with_strategies(parsed_issue)

        assert len(candidates) >= 3


class TestLocalizationAgentAggregation:
    """Test result aggregation and ranking."""

    def test_aggregate_results_returns_sorted(self, issue_context, repo_context):
        """Test that _aggregate_results returns sorted candidates."""
        candidates = [
            SearchCandidate("file1.py", 0.5, "Low", [], "", None),
            SearchCandidate("file2.py", 0.9, "High", [], "", None),
            SearchCandidate("file3.py", 0.7, "Medium", [], "", None),
        ]

        agent = LocalizationAgent(issue_context, repo_context)
        parsed_issue = agent._parse_issue()
        ranked = agent._aggregate_results(candidates, parsed_issue)

        # Should be sorted by confidence descending
        assert ranked[0].confidence >= ranked[1].confidence
        assert ranked[1].confidence >= ranked[2].confidence

    def test_aggregate_results_deduplicates(self, issue_context, repo_context):
        """Test that duplicate files are deduplicated."""
        candidates = [
            SearchCandidate("file1.py", 0.5, "First", [], "", None),
            SearchCandidate("file1.py", 0.9, "Second", [], "", None),
            SearchCandidate("file2.py", 0.7, "Other", [], "", None),
        ]

        agent = LocalizationAgent(issue_context, repo_context)
        parsed_issue = agent._parse_issue()
        ranked = agent._aggregate_results(candidates, parsed_issue)

        # Should keep only highest confidence for duplicates
        file_paths = [c.file_path for c in ranked]
        assert len(file_paths) == len(set(file_paths))

        # file1.py should have confidence 0.9 (higher one)
        file1_candidate = next(c for c in ranked if c.file_path == "file1.py")
        assert file1_candidate.confidence >= 0.9

    def test_aggregate_results_handles_empty(self, issue_context, repo_context):
        """Test aggregation with empty candidate list."""
        agent = LocalizationAgent(issue_context, repo_context)
        parsed_issue = agent._parse_issue()
        ranked = agent._aggregate_results([], parsed_issue)

        assert ranked == []


class TestLocalizationAgentRun:
    """Test main run() method."""

    def test_run_returns_localization_result(self, issue_context, repo_context):
        """Test that run() returns a valid LocalizationResult."""
        # Setup mocks
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate("src/app.py", 0.9, "Stack trace", [], "code", 42)
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        # Verify result structure
        assert isinstance(result, LocalizationResult)
        assert result.status in ["success", "partial", "failed"]
        assert isinstance(result.candidates, list)
        assert isinstance(result.search_strategy, str)
        assert isinstance(result.execution_time, float)
        assert isinstance(result.tool_calls, int)

    def test_run_returns_at_least_one_candidate(self, issue_context, repo_context):
        """Test that run() returns at least 1 candidate when successful."""
        # Setup mocks
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate("src/app.py", 0.9, "Found", [], "", 42)
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        assert result.status in ["success", "partial"]
        assert len(result.candidates) >= 1

    def test_run_execution_time_under_limit(self, issue_context, repo_context):
        """Test that execution time is under 5 minutes (300 seconds)."""
        # Setup mocks
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate("src/app.py", 0.9, "Found", [], "", 42)
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        # Should be well under 300 seconds (5 minutes)
        assert result.execution_time < 300.0
        # In mocked tests, should be very fast
        assert result.execution_time < 10.0

    def test_run_tracks_tool_calls(self, issue_context, repo_context):
        """Test that tool calls are tracked correctly."""
        # Setup mocks
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [SearchCandidate("f.py", 0.9, "R", [], "", 1)]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        # Should have tool calls (at least the 3 search strategies)
        assert result.tool_calls >= 3

    def test_run_handles_no_candidates(self, issue_context, repo_context):
        """Test run() when no candidates are found."""
        # Setup mocks to return no results
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = []
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        # Should return failed or partial status
        assert result.status in ["failed", "partial"]
        assert isinstance(result.candidates, list)

    def test_run_handles_strategy_exception(self, issue_context, repo_context):
        """Test that run() handles exceptions from strategies gracefully."""
        # Setup mock to raise exception
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.side_effect = Exception("Search failed")
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )

        # Should not raise, should handle gracefully
        result = agent.run()

        assert isinstance(result, LocalizationResult)
        # Status should reflect the error
        assert result.status in ["failed", "partial"]


class TestLocalizationAgentCandidateFormat:
    """Test candidate format in results."""

    def test_candidates_have_required_fields(self, issue_context, repo_context):
        """Test that candidates contain all required fields."""
        # Setup mocks
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate(
                file_path="src/app.py",
                confidence=0.9,
                reason="Stack trace match",
                relevant_symbols=["my_func"],
                code_snippet="def my_func():",
                line_number=42,
            )
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        assert len(result.candidates) > 0

        candidate = result.candidates[0]
        assert "file_path" in candidate
        assert "confidence" in candidate
        assert "reason" in candidate

    def test_candidates_sorted_by_confidence(self, issue_context, repo_context):
        """Test that candidates are sorted by confidence descending."""
        # Setup mocks with multiple results
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate("file1.py", 0.5, "Low", [], "", None),
            SearchCandidate("file2.py", 0.9, "High", [], "", None),
            SearchCandidate("file3.py", 0.7, "Med", [], "", None),
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        # Check that confidences are in descending order
        confidences = [c["confidence"] for c in result.candidates]
        assert confidences == sorted(confidences, reverse=True)


class TestLocalizationAgentStatusDetermination:
    """Test status determination logic."""

    def test_status_success_with_high_confidence(self, issue_context, repo_context):
        """Test that status is 'success' with high confidence candidates."""
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate("file.py", 0.9, "High conf", [], "", 42)
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        assert result.status == "success"

    def test_status_partial_with_low_confidence(self, issue_context, repo_context):
        """Test that status is 'partial' with low confidence candidates."""
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = [
            SearchCandidate("file.py", 0.4, "Low conf", [], "", None)
        ]
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        assert result.status in ["partial", "success"]

    def test_status_failed_with_no_candidates(self, issue_context, repo_context):
        """Test that status is 'failed' when no candidates found."""
        mock_stack_instance = Mock()
        mock_error_instance = Mock()
        mock_symbol_instance = Mock()

        mock_stack_instance.search.return_value = []
        mock_error_instance.search.return_value = []
        mock_symbol_instance.search.return_value = []

        agent = LocalizationAgent(
            issue_context,
            repo_context,
            stack_trace_strategy=mock_stack_instance,
            error_message_strategy=mock_error_instance,
            symbol_search_strategy=mock_symbol_instance,
        )
        result = agent.run()

        assert result.status == "failed"
