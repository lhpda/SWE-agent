"""Tests for file operation tools.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Tests for Task 1.3: File Operations Tool Implementation
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from swe_agent.tools.file_ops import (
    ApplyPatchDryRunTool,
    ApplyPatchTool,
    ReadFileTool,
    ReadFileWithContextTool,
)


@pytest.fixture
def temp_repo() -> Generator[Path, None, None]:
    """Create a temporary repository with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create Python test file with 100 lines
        lines = []
        for i in range(1, 101):
            lines.append(f"# Line {i}\n")
            if i % 10 == 0:
                lines.append(f"def function_{i}():\n")
                lines.append(f"    return {i}\n")

        (repo_path / "test_file.py").write_text("".join(lines))

        # Create small test file
        (repo_path / "small.txt").write_text(
            "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        )

        # Create large file (for truncation testing)
        large_content = "x" * 60000  # 60KB, exceeds 50K limit
        (repo_path / "large.txt").write_text(large_content)

        # Create file for patching
        (repo_path / "patch_target.py").write_text(
            "def greet(name):\n"
            '    print("Hello")\n'
            "    return name\n"
            "\n"
            "def calculate(a, b):\n"
            "    return a + b\n"
        )

        yield repo_path


class TestReadFileTool:
    """Tests for read_file tool."""

    def test_read_entire_file(self, temp_repo: Path) -> None:
        """Test reading entire file."""
        tool = ReadFileTool()
        result = tool.execute(path=str(temp_repo / "small.txt"))

        assert result.error is None
        assert result.output is not None
        assert "Line 1" in result.output
        assert "Line 5" in result.output
        assert result.truncated is False

    def test_read_with_line_range(self, temp_repo: Path) -> None:
        """Test reading specific line range."""
        tool = ReadFileTool()
        result = tool.execute(
            path=str(temp_repo / "small.txt"),
            line_range={"start": 2, "end": 4}
        )

        assert result.error is None
        assert result.output is not None
        assert "Line 2" in result.output
        assert "Line 3" in result.output
        assert "Line 4" in result.output
        assert "Line 1" not in result.output
        assert "Line 5" not in result.output

    def test_read_from_start_line(self, temp_repo: Path) -> None:
        """Test reading from start line to end."""
        tool = ReadFileTool()
        result = tool.execute(
            path=str(temp_repo / "small.txt"),
            line_range={"start": 3}
        )

        assert result.error is None
        assert result.output is not None
        assert "Line 1" not in result.output
        assert "Line 2" not in result.output
        assert "Line 3" in result.output
        assert "Line 5" in result.output

    def test_read_to_end_line(self, temp_repo: Path) -> None:
        """Test reading from beginning to end line."""
        tool = ReadFileTool()
        result = tool.execute(
            path=str(temp_repo / "small.txt"),
            line_range={"end": 3}
        )

        assert result.error is None
        assert result.output is not None
        assert "Line 1" in result.output
        assert "Line 3" in result.output
        assert "Line 4" not in result.output
        assert "Line 5" not in result.output

    def test_read_nonexistent_file(self) -> None:
        """Test reading nonexistent file."""
        tool = ReadFileTool()
        result = tool.execute(path="/nonexistent/file.txt")

        assert result.error is not None
        assert "not found" in result.error.lower() or "does not exist" in result.error.lower()

    def test_truncation_at_50k_chars(self, temp_repo: Path) -> None:
        """Test file content truncated at 50,000 characters."""
        tool = ReadFileTool()
        result = tool.execute(path=str(temp_repo / "large.txt"))

        assert result.error is None
        assert result.output is not None
        assert result.truncated is True
        assert len(result.output) <= 50100  # 50K + truncation message
        assert "truncated" in result.output.lower()

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        tool = ReadFileTool()

        # Valid parameters
        valid_params = {"path": "/some/path"}
        assert tool.validate_parameters(valid_params)

        # Missing required parameter
        invalid_params = {}
        assert not tool.validate_parameters(invalid_params)

    def test_invalid_line_range(self, temp_repo: Path) -> None:
        """Test invalid line range (start > end)."""
        tool = ReadFileTool()
        result = tool.execute(
            path=str(temp_repo / "small.txt"),
            line_range={"start": 4, "end": 2}
        )

        assert result.error is not None
        assert "invalid" in result.error.lower() or "range" in result.error.lower()

    def test_line_range_out_of_bounds(self, temp_repo: Path) -> None:
        """Test line range exceeding file length."""
        tool = ReadFileTool()
        result = tool.execute(
            path=str(temp_repo / "small.txt"),
            line_range={"start": 1, "end": 1000}
        )

        # Should succeed but only return available lines
        assert result.error is None
        assert result.output is not None
        assert "Line 5" in result.output


class TestReadFileWithContextTool:
    """Tests for read_file_with_context tool."""

    def test_read_with_default_context(self, temp_repo: Path) -> None:
        """Test reading with default 50 lines context."""
        tool = ReadFileWithContextTool()
        result = tool.execute(
            path=str(temp_repo / "test_file.py"),
            focus_lines=[50]
        )

        assert result.error is None
        assert result.output is not None
        # Should include focus line 50 and context (default 50 lines before and after)
        # Line 1 to line 100 (up to 100 since file only has ~100 lines)
        assert "Line 1" in result.output or "Line 2" in result.output  # Context before
        assert "Line 50" in result.output  # Focus line
        assert result.metadata.get("focus_lines") == [50]
        assert result.metadata.get("context_lines") == 50

    def test_read_with_custom_context(self, temp_repo: Path) -> None:
        """Test reading with custom context lines."""
        tool = ReadFileWithContextTool()
        result = tool.execute(
            path=str(temp_repo / "test_file.py"),
            focus_lines=[20],
            context_lines=5
        )

        assert result.error is None
        assert result.output is not None
        # Should include lines 15-25 (20 ± 5)
        # The output includes line numbers, check that line 20 is included
        assert "  20 |" in result.output or "  20|" in result.output
        # Check we have context (line 15 and line 25)
        assert "  15 |" in result.output or "  15|" in result.output
        assert "  25 |" in result.output or "  25|" in result.output

    def test_multiple_focus_lines(self, temp_repo: Path) -> None:
        """Test reading multiple focus lines."""
        tool = ReadFileWithContextTool()
        result = tool.execute(
            path=str(temp_repo / "test_file.py"),
            focus_lines=[10, 50],
            context_lines=3
        )

        assert result.error is None
        assert result.output is not None
        # Should include context around both lines (check for line numbers)
        assert "  10 |" in result.output or "  10|" in result.output
        assert "  50 |" in result.output or "  50|" in result.output

    def test_context_at_file_boundaries(self, temp_repo: Path) -> None:
        """Test context lines at file start and end."""
        tool = ReadFileWithContextTool()

        # Test at start
        result_start = tool.execute(
            path=str(temp_repo / "small.txt"),
            focus_lines=[1],
            context_lines=50
        )
        assert result_start.error is None
        assert "Line 1" in result_start.output

        # Test at end
        result_end = tool.execute(
            path=str(temp_repo / "small.txt"),
            focus_lines=[5],
            context_lines=50
        )
        assert result_end.error is None
        assert "Line 5" in result_end.output

    def test_nonexistent_file(self) -> None:
        """Test reading nonexistent file with context."""
        tool = ReadFileWithContextTool()
        result = tool.execute(
            path="/nonexistent/file.txt",
            focus_lines=[10]
        )

        assert result.error is not None

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        tool = ReadFileWithContextTool()

        # Valid parameters
        valid_params = {"path": "/some/path", "focus_lines": [10]}
        assert tool.validate_parameters(valid_params)

        # Missing required parameter
        invalid_params = {"path": "/some/path"}
        assert not tool.validate_parameters(invalid_params)

    def test_truncation_at_50k_chars(self, temp_repo: Path) -> None:
        """Test content truncated at 50,000 characters."""
        tool = ReadFileWithContextTool()
        result = tool.execute(
            path=str(temp_repo / "large.txt"),
            focus_lines=[1]
        )

        assert result.error is None
        assert result.output is not None
        assert result.truncated is True
        assert len(result.output) <= 50100  # 50K + truncation message


class TestApplyPatchTool:
    """Tests for apply_patch tool."""

    def test_apply_clean_patch(self, temp_repo: Path) -> None:
        """Test applying patch without conflicts."""
        # Initialize git repo for patch to work
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_repo, capture_output=True)

        patch_content = (
            "--- a/patch_target.py\n"
            "+++ b/patch_target.py\n"
            "@@ -1,6 +1,6 @@\n"
            " def greet(name):\n"
            '-    print("Hello")\n'
            '+    print("Hello, World!")\n'
            "     return name\n"
            " \n"
            " def calculate(a, b):\n"
            "     return a + b\n"
        )

        tool = ApplyPatchTool()
        result = tool.execute(
            path=str(temp_repo / "patch_target.py"),
            patch=patch_content
        )

        assert result.error is None
        assert result.output is not None
        assert "success" in result.output.lower() or "applied" in result.output.lower()

        # Verify file was actually modified
        modified_content = (temp_repo / "patch_target.py").read_text()
        assert "Hello, World!" in modified_content

    def test_apply_patch_with_conflict(self, temp_repo: Path) -> None:
        """Test applying patch with conflicts."""
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_repo, capture_output=True)

        # Modify the file to create conflict
        (temp_repo / "patch_target.py").write_text(
            "def greet(name):\n"
            '    print("Goodbye")  # Changed from "Hello"\n'
            "    return name\n"
            "\n"
            "def calculate(a, b):\n"
            "    return a + b\n"
        )

        # Try to apply patch that conflicts
        patch_content = (
            "--- a/patch_target.py\n"
            "+++ b/patch_target.py\n"
            "@@ -1,6 +1,6 @@\n"
            " def greet(name):\n"
            '-    print("Hello")\n'
            '+    print("Hello, World!")\n'
            "     return name\n"
            " \n"
            " def calculate(a, b):\n"
            "     return a + b\n"
        )

        tool = ApplyPatchTool()
        result = tool.execute(
            path=str(temp_repo / "patch_target.py"),
            patch=patch_content
        )

        assert result.error is not None or (result.output and "conflict" in result.output.lower())

    def test_nonexistent_file(self) -> None:
        """Test applying patch to nonexistent file."""
        patch_content = """--- a/nonexistent.py
+++ b/nonexistent.py
@@ -1,1 +1,1 @@
-old line
+new line
"""

        tool = ApplyPatchTool()
        result = tool.execute(
            path="/nonexistent/file.py",
            patch=patch_content
        )

        assert result.error is not None

    def test_invalid_patch_format(self, temp_repo: Path) -> None:
        """Test applying invalid patch format."""
        tool = ApplyPatchTool()
        result = tool.execute(
            path=str(temp_repo / "patch_target.py"),
            patch="This is not a valid patch"
        )

        assert result.error is not None

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        tool = ApplyPatchTool()

        # Valid parameters
        valid_params = {"path": "/some/path", "patch": "some patch content"}
        assert tool.validate_parameters(valid_params)

        # Missing required parameter
        invalid_params = {"path": "/some/path"}
        assert not tool.validate_parameters(invalid_params)


class TestApplyPatchDryRunTool:
    """Tests for apply_patch_dry_run tool."""

    def test_dry_run_clean_patch(self, temp_repo: Path) -> None:
        """Test dry run with patch that would apply cleanly."""
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_repo, capture_output=True)

        patch_content = (
            "--- a/patch_target.py\n"
            "+++ b/patch_target.py\n"
            "@@ -1,6 +1,6 @@\n"
            " def greet(name):\n"
            '-    print("Hello")\n'
            '+    print("Hello, World!")\n'
            "     return name\n"
            " \n"
            " def calculate(a, b):\n"
            "     return a + b\n"
        )

        tool = ApplyPatchDryRunTool()
        result = tool.execute(
            path=str(temp_repo / "patch_target.py"),
            patch=patch_content
        )

        assert result.error is None
        assert result.output is not None
        assert "success" in result.output.lower() or "clean" in result.output.lower()

        # Verify file was NOT modified
        original_content = (temp_repo / "patch_target.py").read_text()
        assert "Hello, World!" not in original_content
        assert "Hello" in original_content  # Original content unchanged

    def test_dry_run_with_conflict(self, temp_repo: Path) -> None:
        """Test dry run detecting conflicts."""
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=temp_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=temp_repo, capture_output=True)

        # Modify the file to create conflict
        (temp_repo / "patch_target.py").write_text(
            "def greet(name):\n"
            '    print("Goodbye")  # Changed\n'
            "    return name\n"
            "\n"
            "def calculate(a, b):\n"
            "    return a + b\n"
        )

        # Try dry run with conflicting patch
        patch_content = (
            "--- a/patch_target.py\n"
            "+++ b/patch_target.py\n"
            "@@ -1,6 +1,6 @@\n"
            " def greet(name):\n"
            '-    print("Hello")\n'
            '+    print("Hello, World!")\n'
            "     return name\n"
            " \n"
            " def calculate(a, b):\n"
            "     return a + b\n"
        )

        tool = ApplyPatchDryRunTool()
        result = tool.execute(
            path=str(temp_repo / "patch_target.py"),
            patch=patch_content
        )

        assert result.error is not None or (result.output and "conflict" in result.output.lower())

        # Verify file was NOT modified
        content = (temp_repo / "patch_target.py").read_text()
        assert "Goodbye" in content

    def test_nonexistent_file(self) -> None:
        """Test dry run on nonexistent file."""
        patch_content = """--- a/nonexistent.py
+++ b/nonexistent.py
@@ -1,1 +1,1 @@
-old line
+new line
"""

        tool = ApplyPatchDryRunTool()
        result = tool.execute(
            path="/nonexistent/file.py",
            patch=patch_content
        )

        assert result.error is not None

    def test_parameter_validation(self) -> None:
        """Test parameter validation."""
        tool = ApplyPatchDryRunTool()

        # Valid parameters
        valid_params = {"path": "/some/path", "patch": "some patch content"}
        assert tool.validate_parameters(valid_params)

        # Missing required parameter
        invalid_params = {"patch": "some patch"}
        assert not tool.validate_parameters(invalid_params)
