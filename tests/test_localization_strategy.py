"""Unit tests for Code Search Strategy (Task 3.2).

Tests verify multiple search strategies:
- StackTraceStrategy: search based on stack traces
- ErrorMessageStrategy: keyword search based on error messages
- SymbolSearchStrategy: precise location based on symbol names
- SearchResultRanker: confidence scoring and ranking
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.swe_agent.agents.localization.strategy import (
    StackTraceStrategy,
    ErrorMessageStrategy,
    SymbolSearchStrategy,
    SearchResultRanker,
    SearchCandidate,
)
from src.swe_agent.tools.base import ToolResult


class TestStackTraceStrategy:
    """Tests for StackTraceStrategy."""

    def test_search_with_python_stack_trace(self):
        """Test that stack trace matches correct files."""
        strategy = StackTraceStrategy()

        parsed_issue = {
            "stack_traces": [
                {
                    "language": "python",
                    "files": [
                        {"file": "src/utils.py", "line": 42},
                        {"file": "src/handler.py", "line": 15},
                    ],
                    "raw": "Traceback...",
                }
            ],
            "error_messages": ["IndexError: list index out of range"],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        assert len(results) >= 2
        # First file in stack trace should have highest confidence
        assert results[0].file_path == "src/utils.py"
        assert results[0].line_number == 42
        assert results[0].confidence > 0.8
        assert "stack trace" in results[0].reason.lower()

        assert results[1].file_path == "src/handler.py"
        assert results[1].line_number == 15

    def test_search_with_javascript_stack_trace(self):
        """Test JavaScript stack trace parsing."""
        strategy = StackTraceStrategy()

        parsed_issue = {
            "stack_traces": [
                {
                    "language": "javascript",
                    "files": [
                        {"file": "src/api.js", "line": 123, "col": 10},
                        {"file": "src/routes.js", "line": 45, "col": 5},
                    ],
                    "raw": "Error: Cannot read...",
                }
            ],
            "error_messages": ["TypeError: Cannot read property"],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        assert len(results) == 2
        assert results[0].file_path == "src/api.js"
        assert results[0].line_number == 123
        assert results[0].confidence > 0.8

    def test_search_with_multiple_stack_traces(self):
        """Test handling multiple stack traces."""
        strategy = StackTraceStrategy()

        parsed_issue = {
            "stack_traces": [
                {
                    "language": "python",
                    "files": [{"file": "src/a.py", "line": 10}],
                    "raw": "Trace 1",
                },
                {
                    "language": "python",
                    "files": [{"file": "src/b.py", "line": 20}],
                    "raw": "Trace 2",
                },
            ],
            "error_messages": ["Error"],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Should include files from all stack traces
        file_paths = [r.file_path for r in results]
        assert "src/a.py" in file_paths
        assert "src/b.py" in file_paths

    def test_search_without_stack_trace(self):
        """Test that empty list is returned when no stack trace."""
        strategy = StackTraceStrategy()

        parsed_issue = {
            "stack_traces": [],
            "error_messages": ["Some error"],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        assert results == []

    def test_confidence_decreases_with_depth(self):
        """Test that confidence decreases for deeper stack frames."""
        strategy = StackTraceStrategy()

        parsed_issue = {
            "stack_traces": [
                {
                    "language": "python",
                    "files": [
                        {"file": "src/top.py", "line": 1},
                        {"file": "src/middle.py", "line": 2},
                        {"file": "src/bottom.py", "line": 3},
                    ],
                    "raw": "Trace",
                }
            ],
            "error_messages": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Confidence should decrease with stack depth
        assert results[0].confidence > results[1].confidence
        assert results[1].confidence > results[2].confidence


class TestErrorMessageStrategy:
    """Tests for ErrorMessageStrategy."""

    @patch('src.swe_agent.agents.localization.strategy.RipgrepSearchTool')
    def test_search_with_function_name_keyword(self, mock_tool_class):
        """Test keyword search extracts and searches for function names."""
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        # Mock ripgrep results
        mock_tool.execute.return_value = ToolResult(
            output="src/utils.py:42:def process_data(items):\nsrc/utils.py:50:    return process_data(filtered)",
            truncated=False,
            error=None,
        )

        strategy = ErrorMessageStrategy()

        parsed_issue = {
            "error_messages": ["IndexError in process_data: list index out of range"],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Should call ripgrep with extracted keyword
        assert mock_tool.execute.called
        call_args = mock_tool.execute.call_args[1]
        assert "process_data" in call_args["pattern"]

        # Should return candidates with parsed results
        assert len(results) > 0
        assert "src/utils.py" in results[0].file_path
        assert results[0].confidence > 0.5

    @patch('src.swe_agent.agents.localization.strategy.RipgrepSearchTool')
    def test_keyword_extraction_from_error(self, mock_tool_class):
        """Test extraction of keywords from error messages."""
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool
        mock_tool.execute.return_value = ToolResult(
            output="",
            truncated=False,
            error=None,
        )

        strategy = ErrorMessageStrategy()

        parsed_issue = {
            "error_messages": [
                "AttributeError: 'NoneType' object has no attribute 'calculate_total'"
            ],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Should extract 'calculate_total' as keyword
        call_args = mock_tool.execute.call_args[1]
        assert "calculate_total" in call_args["pattern"]

    @patch('src.swe_agent.agents.localization.strategy.RipgrepSearchTool')
    def test_search_ranks_by_relevance(self, mock_tool_class):
        """Test that keyword search results are ranked by relevance."""
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        # File with multiple keyword occurrences
        mock_tool.execute.return_value = ToolResult(
            output="src/core.py:10:def process_data():\nsrc/core.py:15:    process_data\nsrc/core.py:20:    process_data\nsrc/helper.py:5:def process_data():",
            truncated=False,
            error=None,
        )

        strategy = ErrorMessageStrategy()

        parsed_issue = {
            "error_messages": ["Error in process_data function"],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # File with more occurrences should rank higher
        assert len(results) >= 2
        # core.py has 3 occurrences, helper.py has 1
        assert results[0].file_path == "src/core.py"
        assert results[0].confidence > results[1].confidence

    @patch('src.swe_agent.agents.localization.strategy.RipgrepSearchTool')
    def test_search_without_error_messages(self, mock_tool_class):
        """Test that empty list is returned when no error messages."""
        strategy = ErrorMessageStrategy()

        parsed_issue = {
            "error_messages": [],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        assert results == []

    @patch('src.swe_agent.agents.localization.strategy.RipgrepSearchTool')
    def test_handles_ripgrep_errors(self, mock_tool_class):
        """Test handling of ripgrep tool errors."""
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool
        mock_tool.execute.return_value = ToolResult(
            output=None,
            truncated=False,
            error="ripgrep not installed",
        )

        strategy = ErrorMessageStrategy()

        parsed_issue = {
            "error_messages": ["Some error"],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Should return empty list on tool error
        assert results == []


class TestSymbolSearchStrategy:
    """Tests for SymbolSearchStrategy."""

    @patch('src.swe_agent.agents.localization.strategy.SymbolSearchTool')
    def test_search_locates_function(self, mock_tool_class):
        """Test that symbol search locates specific functions."""
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        mock_tool.execute.return_value = ToolResult(
            output="src/calculator.py:25:function:add_numbers\nsrc/math_utils.py:10:function:add_numbers",
            truncated=False,
            error=None,
        )

        strategy = SymbolSearchStrategy()

        parsed_issue = {
            "error_messages": ["Error in add_numbers function"],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Should call symbol search with extracted symbol name
        assert mock_tool.execute.called
        call_args = mock_tool.execute.call_args[1]
        assert call_args["symbol_name"] == "add_numbers"

        # Should return candidates
        assert len(results) == 2
        assert results[0].file_path == "src/calculator.py"
        assert results[0].line_number == 25
        assert "add_numbers" in results[0].relevant_symbols

    @patch('src.swe_agent.agents.localization.strategy.SymbolSearchTool')
    def test_search_locates_class(self, mock_tool_class):
        """Test that symbol search locates classes."""
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        mock_tool.execute.return_value = ToolResult(
            output="src/models.py:100:class:UserManager",
            truncated=False,
            error=None,
        )

        strategy = SymbolSearchStrategy()

        parsed_issue = {
            "error_messages": ["UserManager class throws exception"],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        assert len(results) == 1
        assert results[0].file_path == "src/models.py"
        assert results[0].confidence > 0.7
        assert "class" in results[0].reason.lower()

    @patch('src.swe_agent.agents.localization.strategy.SymbolSearchTool')
    def test_extracts_multiple_symbols(self, mock_tool_class):
        """Test extraction of multiple symbols from error message."""
        mock_tool = Mock()
        mock_tool_class.return_value = mock_tool

        # Mock returns results for both symbols
        def mock_execute(**kwargs):
            symbol = kwargs["symbol_name"]
            if symbol == "validate_input":
                return ToolResult(
                    output="src/validators.py:10:function:validate_input",
                    truncated=False,
                    error=None,
                )
            elif symbol == "process_data":
                return ToolResult(
                    output="src/processor.py:20:function:process_data",
                    truncated=False,
                    error=None,
                )
            return ToolResult(output="", truncated=False, error=None)

        mock_tool.execute.side_effect = mock_execute
        mock_tool_class.return_value = mock_tool

        strategy = SymbolSearchStrategy()

        parsed_issue = {
            "error_messages": ["validate_input failed before process_data"],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Should search for both symbols
        assert len(results) >= 2
        file_paths = [r.file_path for r in results]
        assert "src/validators.py" in file_paths
        assert "src/processor.py" in file_paths

    @patch('src.swe_agent.agents.localization.strategy.SymbolSearchTool')
    def test_no_symbols_found(self, mock_tool_class):
        """Test when no symbols can be extracted."""
        strategy = SymbolSearchStrategy()

        parsed_issue = {
            "error_messages": ["Something went wrong!"],
            "stack_traces": [],
        }

        results = strategy.search(parsed_issue, repo_path="/test/repo")

        # Should return empty list when no symbols extracted
        assert results == []


class TestSearchResultRanker:
    """Tests for SearchResultRanker."""

    def test_rank_by_stack_trace_match(self):
        """Test that files in stack trace get higher confidence."""
        ranker = SearchResultRanker()

        candidates = [
            SearchCandidate(
                file_path="src/utils.py",
                confidence=0.5,
                reason="keyword match",
                relevant_symbols=[],
                code_snippet="",
            ),
            SearchCandidate(
                file_path="src/other.py",
                confidence=0.5,
                reason="keyword match",
                relevant_symbols=[],
                code_snippet="",
            ),
        ]

        parsed_issue = {
            "stack_traces": [
                {
                    "language": "python",
                    "files": [{"file": "src/utils.py", "line": 42}],
                }
            ],
            "error_messages": [],
        }

        ranked = ranker.rank(candidates, parsed_issue)

        # utils.py should rank higher due to stack trace match
        assert ranked[0].file_path == "src/utils.py"
        assert ranked[0].confidence > candidates[0].confidence

    def test_rank_by_keyword_density(self):
        """Test ranking by keyword occurrence count."""
        ranker = SearchResultRanker()

        candidates = [
            SearchCandidate(
                file_path="src/a.py",
                confidence=0.5,
                reason="3 occurrences",
                relevant_symbols=[],
                code_snippet="process process process",
            ),
            SearchCandidate(
                file_path="src/b.py",
                confidence=0.5,
                reason="1 occurrence",
                relevant_symbols=[],
                code_snippet="process",
            ),
        ]

        parsed_issue = {
            "error_messages": ["Error in process function"],
            "stack_traces": [],
        }

        ranked = ranker.rank(candidates, parsed_issue)

        # File with more keyword occurrences should rank higher
        assert ranked[0].file_path == "src/a.py"
        assert ranked[0].confidence > ranked[1].confidence

    def test_penalize_test_files(self):
        """Test that test files get lower confidence."""
        ranker = SearchResultRanker()

        candidates = [
            SearchCandidate(
                file_path="src/utils.py",
                confidence=0.7,
                reason="match",
                relevant_symbols=[],
                code_snippet="",
            ),
            SearchCandidate(
                file_path="tests/test_utils.py",
                confidence=0.7,
                reason="match",
                relevant_symbols=[],
                code_snippet="",
            ),
        ]

        parsed_issue = {
            "error_messages": [],
            "stack_traces": [],
        }

        ranked = ranker.rank(candidates, parsed_issue)

        # Non-test file should rank higher
        assert ranked[0].file_path == "src/utils.py"
        assert ranked[1].file_path == "tests/test_utils.py"
        assert ranked[0].confidence > ranked[1].confidence

    def test_top_3_confidence_sum_threshold(self):
        """Test that Top-3 confidence sum exceeds 0.6."""
        ranker = SearchResultRanker()

        candidates = [
            SearchCandidate(
                file_path=f"src/file{i}.py",
                confidence=0.5,
                reason="match",
                relevant_symbols=[],
                code_snippet="",
            )
            for i in range(5)
        ]

        parsed_issue = {
            "error_messages": ["function_name error"],
            "stack_traces": [
                {
                    "language": "python",
                    "files": [{"file": "src/file0.py", "line": 10}],
                }
            ],
        }

        ranked = ranker.rank(candidates, parsed_issue)

        # Top-3 should have confidence sum > 0.6
        top_3_sum = sum(c.confidence for c in ranked[:3])
        assert top_3_sum > 0.6

    def test_deduplication(self):
        """Test that duplicate file paths are deduplicated."""
        ranker = SearchResultRanker()

        candidates = [
            SearchCandidate(
                file_path="src/utils.py",
                confidence=0.7,
                reason="stack trace",
                relevant_symbols=[],
                code_snippet="",
                line_number=10,
            ),
            SearchCandidate(
                file_path="src/utils.py",
                confidence=0.6,
                reason="keyword match",
                relevant_symbols=[],
                code_snippet="",
                line_number=20,
            ),
            SearchCandidate(
                file_path="src/other.py",
                confidence=0.5,
                reason="match",
                relevant_symbols=[],
                code_snippet="",
            ),
        ]

        parsed_issue = {
            "error_messages": [],
            "stack_traces": [],
        }

        ranked = ranker.rank(candidates, parsed_issue)

        # Should keep higher confidence instance
        file_paths = [c.file_path for c in ranked]
        assert file_paths.count("src/utils.py") == 1
        assert ranked[0].file_path == "src/utils.py"
        assert ranked[0].confidence >= 0.7


class TestSearchCandidate:
    """Tests for SearchCandidate dataclass."""

    def test_candidate_creation(self):
        """Test creating a search candidate."""
        candidate = SearchCandidate(
            file_path="src/test.py",
            confidence=0.85,
            reason="Found in stack trace",
            relevant_symbols=["func1", "Class1"],
            code_snippet="def func1():\n    pass",
            line_number=42,
        )

        assert candidate.file_path == "src/test.py"
        assert candidate.confidence == 0.85
        assert candidate.line_number == 42
        assert len(candidate.relevant_symbols) == 2

    def test_candidate_to_dict(self):
        """Test conversion of candidate to dictionary format."""
        candidate = SearchCandidate(
            file_path="src/test.py",
            confidence=0.85,
            reason="stack trace",
            relevant_symbols=["func1"],
            code_snippet="code",
        )

        result = candidate.to_dict()

        assert isinstance(result, dict)
        assert result["file_path"] == "src/test.py"
        assert result["confidence"] == 0.85
        assert result["reason"] == "stack trace"
        assert "relevant_symbols" in result
