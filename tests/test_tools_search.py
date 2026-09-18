"""Tests for search tools.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Tests for Task 1.2: Search Tool Implementation
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from swe_agent.tools.search import AstQueryTool, RipgrepSearchTool, SymbolSearchTool


@pytest.fixture
def temp_repo() -> Generator[Path, None, None]:
    """Create a temporary repository with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create Python test file
        (repo_path / "example.py").write_text(
            """def hello_world():
    '''A simple greeting function'''
    print("Hello, World!")
    return "Hello"

class Calculator:
    '''A basic calculator class'''

    def add(self, a, b):
        '''Add two numbers'''
        return a + b

    def subtract(self, a, b):
        '''Subtract b from a'''
        return a - b

def process_data(data):
    '''Process some data'''
    result = []
    for item in data:
        result.append(item * 2)
    return result
"""
        )

        # Create JavaScript test file
        (repo_path / "example.js").write_text(
            """function greet(name) {
    return "Hello, " + name;
}

class Person {
    constructor(name, age) {
        this.name = name;
        this.age = age;
    }

    sayHello() {
        console.log("Hello from " + this.name);
    }
}

const multiply = (a, b) => a * b;
"""
        )

        # Create file with many matches
        many_matches = "\n".join([f"line {i}: test pattern here" for i in range(150)])
        (repo_path / "many_matches.txt").write_text(many_matches)

        yield repo_path


class TestRipgrepSearchTool:
    """Tests for ripgrep_search tool."""

    @patch("subprocess.run")
    def test_simple_search(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test basic text search."""
        # Mock successful ripgrep output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="example.py:1:def hello_world():\n",
            stderr="",
        )

        tool = RipgrepSearchTool()
        result = tool.execute(pattern="hello_world", path=str(temp_repo))

        assert result.error is None
        assert result.output is not None
        assert "example.py" in result.output
        assert "hello_world" in result.output

        # Verify ripgrep was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "rg" in call_args
        assert "hello_world" in call_args

    @patch("subprocess.run")
    def test_search_with_file_type(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test search filtered by file type."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='example.py:3:    print("Hello, World!")\n',
            stderr="",
        )

        tool = RipgrepSearchTool()
        result = tool.execute(pattern="Hello", path=str(temp_repo), file_types=["py"])

        assert result.error is None
        assert result.output is not None
        assert "example.py" in result.output

        # Verify --type py was used
        call_args = mock_run.call_args[0][0]
        assert "--type" in call_args
        assert "py" in call_args

    @patch("subprocess.run")
    def test_case_insensitive_search(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test case-insensitive search."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="example.py:1:def hello_world():\n",
            stderr="",
        )

        tool = RipgrepSearchTool()
        result = tool.execute(pattern="HELLO", path=str(temp_repo), case_sensitive=False)

        assert result.error is None
        assert result.output is not None
        assert "hello" in result.output.lower()

        # Verify --ignore-case was used
        call_args = mock_run.call_args[0][0]
        assert "--ignore-case" in call_args

    @patch("subprocess.run")
    def test_truncation_at_100_results(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test that results are truncated at 100 matches."""
        # Mock 100 results
        mock_output = "\n".join([f"file.txt:{i}:test pattern" for i in range(100)])
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr="",
        )

        tool = RipgrepSearchTool()
        result = tool.execute(pattern="test pattern", path=str(temp_repo))

        assert result.error is None
        assert result.output is not None

        # Should have truncation marker
        assert "Truncated" in result.output or "truncated" in result.output

        # Verify max-count parameter was used
        call_args = mock_run.call_args[0][0]
        assert "--max-count" in call_args
        assert "100" in call_args

    @patch("subprocess.run")
    def test_no_matches(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test search with no matches."""
        mock_run.return_value = MagicMock(
            returncode=1,  # ripgrep returns 1 for no matches
            stdout="",
            stderr="",
        )

        tool = RipgrepSearchTool()
        result = tool.execute(pattern="nonexistent_pattern_xyz", path=str(temp_repo))

        assert result.error is None
        assert result.output is not None
        assert "No matches found" in result.output

    def test_invalid_path(self) -> None:
        """Test search with invalid path."""
        tool = RipgrepSearchTool()
        result = tool.execute(pattern="test", path="/nonexistent/path/xyz")

        assert result.error is not None

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        tool = RipgrepSearchTool()

        # Valid parameters
        valid_params = {"pattern": "test", "path": "/some/path"}
        assert tool.validate_parameters(valid_params)

        # Missing required parameter
        invalid_params = {"path": "/some/path"}
        assert not tool.validate_parameters(invalid_params)

    @patch("subprocess.run")
    def test_line_numbers_in_output(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test that output includes line numbers."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="example.py:1:def hello_world():\n",
            stderr="",
        )

        tool = RipgrepSearchTool()
        result = tool.execute(pattern="def hello_world", path=str(temp_repo))

        assert result.error is None
        assert result.output is not None
        # ripgrep shows line numbers like "example.py:1:def hello_world"
        assert ":" in result.output
        assert "example.py" in result.output

        # Verify --line-number was used
        call_args = mock_run.call_args[0][0]
        assert "--line-number" in call_args


class TestSymbolSearchTool:
    """Tests for symbol_search tool."""

    @patch("subprocess.run")
    def test_search_function(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test searching for a function symbol."""
        # Mock ctags JSON output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name":"hello_world","path":"example.py","line":1,"kind":"function"}\n',
            stderr="",
        )

        tool = SymbolSearchTool()
        result = tool.execute(
            symbol_name="hello_world", path=str(temp_repo), symbol_type="function"
        )

        assert result.error is None
        assert result.output is not None
        assert "hello_world" in result.output
        assert "example.py" in result.output

    @patch("subprocess.run")
    def test_search_class(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test searching for a class symbol."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name":"Calculator","path":"example.py","line":6,"kind":"class"}\n',
            stderr="",
        )

        tool = SymbolSearchTool()
        result = tool.execute(symbol_name="Calculator", path=str(temp_repo), symbol_type="class")

        assert result.error is None
        assert result.output is not None
        assert "Calculator" in result.output
        assert "example.py" in result.output

    @patch("subprocess.run")
    def test_search_any_symbol(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test searching for any symbol type."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name":"add","path":"example.py","line":9,"kind":"method"}\n',
            stderr="",
        )

        tool = SymbolSearchTool()
        result = tool.execute(symbol_name="add", path=str(temp_repo))

        assert result.error is None
        assert result.output is not None
        assert "add" in result.output

    @patch("subprocess.run")
    def test_no_symbol_matches(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test search with no matching symbols."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        tool = SymbolSearchTool()
        result = tool.execute(symbol_name="nonexistent_symbol_xyz", path=str(temp_repo))

        assert result.error is None
        assert result.output is not None
        assert "No symbols found" in result.output

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        tool = SymbolSearchTool()

        # Valid parameters
        valid_params = {"symbol_name": "test", "path": "/some/path"}
        assert tool.validate_parameters(valid_params)

        # Missing required parameter
        invalid_params = {"path": "/some/path"}
        assert not tool.validate_parameters(invalid_params)

    @patch("subprocess.run")
    def test_multiple_symbols_same_name(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test finding multiple symbols with the same name."""
        # Mock multiple results with same name
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"name":"process","path":"duplicate.py","line":1,"kind":"function"}\n'
            '{"name":"process","path":"duplicate.py","line":5,"kind":"method"}\n',
            stderr="",
        )

        tool = SymbolSearchTool()
        result = tool.execute(symbol_name="process", path=str(temp_repo))

        assert result.error is None
        assert result.output is not None
        # Should find both occurrences
        assert result.output.count("process") >= 2


class TestAstQueryTool:
    """Tests for ast_query tool."""

    def test_find_function_calls(self, temp_repo: Path) -> None:
        """Test finding function call nodes."""
        tool = AstQueryTool()
        result = tool.execute(query_type="function_call", path=str(temp_repo / "example.py"))

        assert result.error is None
        assert result.output is not None
        # Should find print() and append() calls
        assert "print" in result.output or "call" in result.output.lower()

    def test_find_class_definitions(self, temp_repo: Path) -> None:
        """Test finding class definition nodes."""
        tool = AstQueryTool()
        result = tool.execute(query_type="class_definition", path=str(temp_repo / "example.py"))

        assert result.error is None
        assert result.output is not None
        assert "Calculator" in result.output

    def test_find_function_definitions(self, temp_repo: Path) -> None:
        """Test finding function definition nodes."""
        tool = AstQueryTool()
        result = tool.execute(query_type="function_definition", path=str(temp_repo / "example.py"))

        assert result.error is None
        assert result.output is not None
        assert "hello_world" in result.output or "def" in result.output.lower()

    def test_unsupported_file_type(self, temp_repo: Path) -> None:
        """Test handling unsupported file types."""
        # Create unsupported file
        (temp_repo / "test.xyz").write_text("some content")

        tool = AstQueryTool()
        result = tool.execute(query_type="function_definition", path=str(temp_repo / "test.xyz"))

        # Should return error or empty result
        assert result.error is not None or (
            result.output is not None and "not supported" in result.output.lower()
        )

    def test_invalid_file_path(self) -> None:
        """Test handling invalid file paths."""
        tool = AstQueryTool()
        result = tool.execute(query_type="function_definition", path="/nonexistent/file.py")

        assert result.error is not None

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        tool = AstQueryTool()

        # Valid parameters
        valid_params = {"query_type": "function_definition", "path": "/some/file.py"}
        assert tool.validate_parameters(valid_params)

        # Missing required parameter
        invalid_params = {"path": "/some/file.py"}
        assert not tool.validate_parameters(invalid_params)

    def test_javascript_ast_query(self, temp_repo: Path) -> None:
        """Test AST query on JavaScript file."""
        tool = AstQueryTool()
        result = tool.execute(query_type="function_definition", path=str(temp_repo / "example.js"))

        assert result.error is None
        assert result.output is not None
        # Should find function definitions in JS file
        assert "greet" in result.output or "function" in result.output.lower()

    def test_syntax_error_handling(self, temp_repo: Path) -> None:
        """Test handling files with syntax errors."""
        # Create file with syntax error
        (temp_repo / "syntax_error.py").write_text(
            """def broken_function(
    # Missing closing parenthesis
    print("test")
"""
        )

        tool = AstQueryTool()
        result = tool.execute(
            query_type="function_definition", path=str(temp_repo / "syntax_error.py")
        )

        # Should handle gracefully - either return error or partial results
        assert result.error is not None or result.output is not None


class TestSearchToolIntegration:
    """Integration tests for search tools working together."""

    @patch("subprocess.run")
    def test_ripgrep_then_symbol_search(self, mock_run: MagicMock, temp_repo: Path) -> None:
        """Test using ripgrep to find files, then symbol search for details."""
        # First call: ripgrep
        # Second call: ctags
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout="example.py:6:class Calculator:\n",
                stderr="",
            ),
            MagicMock(
                returncode=0,
                stdout='{"name":"Calculator","path":"example.py","line":6,"kind":"class"}\n',
                stderr="",
            ),
        ]

        # First use ripgrep to find files containing "Calculator"
        ripgrep = RipgrepSearchTool()
        rg_result = ripgrep.execute(pattern="Calculator", path=str(temp_repo))

        assert rg_result.error is None
        assert "example.py" in rg_result.output

        # Then use symbol search to find the class definition
        symbol = SymbolSearchTool()
        sym_result = symbol.execute(
            symbol_name="Calculator", path=str(temp_repo), symbol_type="class"
        )

        assert sym_result.error is None
        assert "Calculator" in sym_result.output

    def test_symbol_then_ast_query(self, temp_repo: Path) -> None:
        """Test using symbol search to find files, then AST query for structure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='{"name":"process_data","path":"example.py","line":19,"kind":"function"}\n',
                stderr="",
            )

            # First find the file containing "process_data"
            symbol = SymbolSearchTool()
            sym_result = symbol.execute(symbol_name="process_data", path=str(temp_repo))

            assert sym_result.error is None
            assert "example.py" in sym_result.output

        # Then query AST for function calls in that file (no mock needed, uses real tree-sitter)
        ast = AstQueryTool()
        ast_result = ast.execute(query_type="function_call", path=str(temp_repo / "example.py"))

        assert ast_result.error is None
        assert ast_result.output is not None
