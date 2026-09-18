"""
Tests for CodeEditEngine - code editing and manipulation engine.

Following TDD: These tests are written BEFORE implementation.
"""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Dict, Any

# Import will be added after implementation
# from swe_agent.agents.patch.edit_engine import CodeEditEngine


class TestCodeEditEngineBasics:
    """Test basic CodeEditEngine initialization and structure."""

    @pytest.fixture
    def engine(self):
        """Create a CodeEditEngine instance."""
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    @pytest.fixture
    def temp_python_file(self, tmp_path):
        """Create a temporary Python file for testing."""
        file_path = tmp_path / "test_file.py"
        content = """def hello():
    print("Hello")
    return True

def goodbye():
    print("Goodbye")
    return False
"""
        file_path.write_text(content)
        return str(file_path)

    def test_engine_initialization(self, engine):
        """Test that engine can be initialized."""
        assert engine is not None


class TestInsertOperations:
    """Test insert code operations."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    @pytest.fixture
    def temp_file(self, tmp_path):
        """Create temp file with simple content."""
        file_path = tmp_path / "insert_test.py"
        content = """line1
line2
line3
"""
        file_path.write_text(content)
        return str(file_path)

    def test_insert_at_beginning(self, engine, temp_file):
        """Test inserting code at the beginning of file."""
        edit_op = {
            "type": "insert",
            "file_path": temp_file,
            "start_line": 0,
            "content": "# Header comment\n",
        }
        result = engine.apply_edit(temp_file, edit_op)
        assert result["success"] is True

        with open(temp_file, "r") as f:
            lines = f.readlines()
        assert lines[0] == "# Header comment\n"
        assert lines[1] == "line1\n"

    def test_insert_in_middle(self, engine, temp_file):
        """Test inserting code in the middle of file."""
        edit_op = {
            "type": "insert",
            "file_path": temp_file,
            "start_line": 2,
            "content": "inserted_line\n",
        }
        result = engine.apply_edit(temp_file, edit_op)
        assert result["success"] is True

        with open(temp_file, "r") as f:
            lines = f.readlines()
        assert "inserted_line\n" in lines

    def test_insert_at_end(self, engine, temp_file):
        """Test inserting code at the end of file."""
        with open(temp_file, "r") as f:
            original_lines = f.readlines()

        edit_op = {
            "type": "insert",
            "file_path": temp_file,
            "start_line": len(original_lines),
            "content": "last_line\n",
        }
        result = engine.apply_edit(temp_file, edit_op)
        assert result["success"] is True

        with open(temp_file, "r") as f:
            lines = f.readlines()
        assert lines[-1] == "last_line\n"

    def test_insert_multiline(self, engine, temp_file):
        """Test inserting multiple lines."""
        edit_op = {
            "type": "insert",
            "file_path": temp_file,
            "start_line": 1,
            "content": "new_line1\nnew_line2\nnew_line3\n",
        }
        result = engine.apply_edit(temp_file, edit_op)
        assert result["success"] is True

        with open(temp_file, "r") as f:
            content = f.read()
        assert "new_line1" in content
        assert "new_line2" in content
        assert "new_line3" in content


class TestReplaceOperations:
    """Test replace code block operations."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    @pytest.fixture
    def temp_python_file(self, tmp_path):
        file_path = tmp_path / "replace_test.py"
        content = """def old_function():
    print("Old")
    return 1

def keep_function():
    print("Keep")
    return 2
"""
        file_path.write_text(content)
        return str(file_path)

    def test_replace_single_line(self, engine, temp_python_file):
        """Test replacing a single line."""
        edit_op = {
            "type": "replace",
            "file_path": temp_python_file,
            "start_line": 2,
            "end_line": 2,
            "content": '    print("New")\n',
        }
        result = engine.apply_edit(temp_python_file, edit_op)
        assert result["success"] is True

        with open(temp_python_file, "r") as f:
            content = f.read()
        assert 'print("New")' in content
        assert 'print("Old")' not in content

    def test_replace_multiple_lines(self, engine, temp_python_file):
        """Test replacing multiple lines (entire function)."""
        edit_op = {
            "type": "replace",
            "file_path": temp_python_file,
            "start_line": 1,
            "end_line": 3,
            "content": """def new_function():
    print("Replaced")
    return 99
""",
        }
        result = engine.apply_edit(temp_python_file, edit_op)
        assert result["success"] is True

        with open(temp_python_file, "r") as f:
            content = f.read()
        assert "new_function" in content
        assert "old_function" not in content
        assert "keep_function" in content  # Should not affect other parts

    def test_replace_with_empty_content(self, engine, tmp_path):
        """Test replacing lines with empty content (effectively delete)."""
        # Create a file where removing lines won't break syntax
        file_path = tmp_path / "replace_empty.py"
        content = """# Comment line 1
# Comment line 2
# Comment line 3

def keep_function():
    pass
"""
        file_path.write_text(content)

        edit_op = {
            "type": "replace",
            "file_path": str(file_path),
            "start_line": 2,
            "end_line": 3,
            "content": "",
        }
        result = engine.apply_edit(str(file_path), edit_op)
        assert result["success"] is True

        # Verify the comments were removed
        with open(str(file_path), "r") as f:
            content = f.read()
        assert "Comment line 1" in content
        assert "Comment line 2" not in content
        assert "Comment line 3" not in content
        assert "keep_function" in content


class TestDeleteOperations:
    """Test delete code operations."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    @pytest.fixture
    def temp_file(self, tmp_path):
        file_path = tmp_path / "delete_test.py"
        content = """line1
line2
line3
line4
line5
"""
        file_path.write_text(content)
        return str(file_path)

    def test_delete_single_line(self, engine, temp_file):
        """Test deleting a single line."""
        edit_op = {"type": "delete", "file_path": temp_file, "start_line": 2, "end_line": 2}
        result = engine.apply_edit(temp_file, edit_op)
        assert result["success"] is True

        with open(temp_file, "r") as f:
            content = f.read()
        assert "line2" not in content
        assert "line1" in content
        assert "line3" in content

    def test_delete_multiple_lines(self, engine, temp_file):
        """Test deleting multiple consecutive lines."""
        edit_op = {"type": "delete", "file_path": temp_file, "start_line": 2, "end_line": 4}
        result = engine.apply_edit(temp_file, edit_op)
        assert result["success"] is True

        with open(temp_file, "r") as f:
            content = f.read()
        assert "line2" not in content
        assert "line3" not in content
        assert "line4" not in content
        assert "line1" in content
        assert "line5" in content

    def test_delete_first_line(self, engine, temp_file):
        """Test deleting the first line."""
        edit_op = {"type": "delete", "file_path": temp_file, "start_line": 1, "end_line": 1}
        result = engine.apply_edit(temp_file, edit_op)
        assert result["success"] is True

        with open(temp_file, "r") as f:
            lines = f.readlines()
        assert lines[0] == "line2\n"


class TestSyntaxValidation:
    """Test syntax validation functionality."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    def test_validate_valid_python_syntax(self, engine):
        """Test validation accepts valid Python code."""
        valid_code = """def test():
    x = 1
    return x + 2
"""
        result = engine.validate_syntax("test.py", valid_code)
        assert result["valid"] is True

    def test_validate_invalid_python_syntax(self, engine):
        """Test validation rejects invalid Python syntax."""
        invalid_code = """def test()
    x = 1
    return x +
"""
        result = engine.validate_syntax("test.py", invalid_code)
        assert result["valid"] is False
        assert "error" in result or "message" in result

    def test_validate_indentation_error(self, engine):
        """Test validation detects indentation errors."""
        bad_indent = """def test():
x = 1
    return x
"""
        result = engine.validate_syntax("test.py", bad_indent)
        assert result["valid"] is False

    def test_validate_syntax_rejects_invalid_edit(self, engine, tmp_path):
        """Test that apply_edit rejects operations that create syntax errors."""
        file_path = tmp_path / "syntax_test.py"
        content = """def valid():
    return True
"""
        file_path.write_text(content)

        # Try to insert invalid syntax
        edit_op = {
            "type": "insert",
            "file_path": str(file_path),
            "start_line": 2,
            "content": "    return x +\n",  # Incomplete expression
        }
        result = engine.apply_edit(str(file_path), edit_op)
        assert result["success"] is False
        assert "syntax" in result.get("error", "").lower()


class TestDiffGeneration:
    """Test diff generation functionality."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    def test_generate_diff_basic(self, engine):
        """Test generating a basic unified diff."""
        original = """line1
line2
line3
"""
        modified = """line1
line2_modified
line3
"""
        diff = engine.generate_diff(original, modified)
        assert diff is not None
        assert "line2" in diff
        assert "line2_modified" in diff
        assert "-" in diff  # Should have removal marker
        assert "+" in diff  # Should have addition marker

    def test_generate_diff_no_changes(self, engine):
        """Test diff generation when content is identical."""
        content = """line1
line2
"""
        diff = engine.generate_diff(content, content)
        # Should return empty diff or minimal output
        assert diff is not None

    def test_generate_diff_addition(self, engine):
        """Test diff shows addition."""
        original = """line1
line2
"""
        modified = """line1
line2
line3
"""
        diff = engine.generate_diff(original, modified)
        assert "+line3" in diff or "+ line3" in diff


class TestRollbackFunctionality:
    """Test rollback/undo functionality."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    @pytest.fixture
    def temp_file(self, tmp_path):
        file_path = tmp_path / "rollback_test.py"
        content = """original_line1
original_line2
"""
        file_path.write_text(content)
        return str(file_path)

    def test_rollback_after_edit(self, engine, temp_file):
        """Test rollback restores original content."""
        # Read original
        with open(temp_file, "r") as f:
            original = f.read()

        # Apply edit
        edit_op = {
            "type": "replace",
            "file_path": temp_file,
            "start_line": 1,
            "end_line": 1,
            "content": "modified_line1\n",
        }
        engine.apply_edit(temp_file, edit_op)

        # Verify it changed
        with open(temp_file, "r") as f:
            modified = f.read()
        assert modified != original

        # Rollback
        rollback_result = engine.rollback_edit(temp_file)
        assert rollback_result["success"] is True

        # Verify restored
        with open(temp_file, "r") as f:
            restored = f.read()
        assert restored == original

    def test_rollback_without_prior_edit(self, engine, temp_file):
        """Test rollback behavior when no edit was made."""
        result = engine.rollback_edit(temp_file)
        # Should either succeed gracefully or indicate no backup exists
        assert "success" in result


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    def test_apply_edit_nonexistent_file(self, engine):
        """Test error handling for nonexistent file."""
        edit_op = {
            "type": "insert",
            "file_path": "/nonexistent/path/file.py",
            "start_line": 1,
            "content": "test\n",
        }
        result = engine.apply_edit("/nonexistent/path/file.py", edit_op)
        assert result["success"] is False

    def test_apply_edit_invalid_operation_type(self, engine, tmp_path):
        """Test error handling for invalid operation type."""
        file_path = tmp_path / "test.py"
        file_path.write_text("content\n")

        edit_op = {"type": "invalid_type", "file_path": str(file_path), "start_line": 1}
        result = engine.apply_edit(str(file_path), edit_op)
        assert result["success"] is False

    def test_apply_edit_invalid_line_numbers(self, engine, tmp_path):
        """Test error handling for invalid line numbers."""
        file_path = tmp_path / "test.py"
        file_path.write_text("line1\nline2\n")

        edit_op = {
            "type": "delete",
            "file_path": str(file_path),
            "start_line": 10,  # Beyond file length
            "end_line": 20,
        }
        result = engine.apply_edit(str(file_path), edit_op)
        assert result["success"] is False


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    @pytest.fixture
    def engine(self):
        from swe_agent.agents.patch.edit_engine import CodeEditEngine

        return CodeEditEngine()

    def test_multiple_sequential_edits(self, engine, tmp_path):
        """Test applying multiple edits in sequence."""
        file_path = tmp_path / "multi_edit.py"
        content = """def func1():
    pass

def func2():
    pass
"""
        file_path.write_text(content)

        # Edit 1: Insert
        edit1 = {
            "type": "insert",
            "file_path": str(file_path),
            "start_line": 0,
            "content": "# Header\n",
        }
        result1 = engine.apply_edit(str(file_path), edit1)
        assert result1["success"] is True

        # Edit 2: Replace
        edit2 = {
            "type": "replace",
            "file_path": str(file_path),
            "start_line": 2,
            "end_line": 2,
            "content": "def func1_renamed():\n",
        }
        result2 = engine.apply_edit(str(file_path), edit2)
        assert result2["success"] is True

        # Verify final result
        with open(file_path, "r") as f:
            final = f.read()
        assert "# Header" in final
        assert "func1_renamed" in final
