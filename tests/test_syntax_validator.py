"""
Tests for SyntaxValidator class.
"""

import pytest
import tempfile
import os
from pathlib import Path
from src.swe_agent.agents.patch.validator import SyntaxValidator


class TestSyntaxValidatorInit:
    """Test SyntaxValidator initialization."""

    def test_init(self):
        """Test basic initialization."""
        validator = SyntaxValidator()
        assert validator is not None


class TestPythonValidation:
    """Test Python syntax validation."""

    def test_validate_valid_python(self):
        """Test validation of valid Python code."""
        validator = SyntaxValidator()
        code = """
def hello():
    return "world"
"""
        result = validator.validate_python(code)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_invalid_python_syntax(self):
        """Test validation of invalid Python syntax."""
        validator = SyntaxValidator()
        code = """
def hello(
    return "world"
"""
        result = validator.validate_python(code)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0
        assert "SyntaxError" in result["error_type"]

    def test_validate_invalid_indentation(self):
        """Test validation of invalid indentation."""
        validator = SyntaxValidator()
        code = """
def hello():
return "world"
"""
        result = validator.validate_python(code)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_validate_empty_code(self):
        """Test validation of empty code."""
        validator = SyntaxValidator()
        result = validator.validate_python("")
        assert result["is_valid"] is True


class TestImportValidation:
    """Test import statement validation."""

    def test_check_valid_imports(self):
        """Test checking valid import statements."""
        validator = SyntaxValidator()
        code = """
import os
from pathlib import Path
import sys
"""
        result = validator.check_imports(code)
        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    def test_check_invalid_imports(self):
        """Test checking invalid import statements."""
        validator = SyntaxValidator()
        code = """
import os
from pathlib import
import sys
"""
        result = validator.check_imports(code)
        assert result["is_valid"] is False
        assert len(result["errors"]) > 0

    def test_check_no_imports(self):
        """Test code with no imports."""
        validator = SyntaxValidator()
        code = """
def hello():
    return "world"
"""
        result = validator.check_imports(code)
        assert result["is_valid"] is True


class TestPatchApplication:
    """Test patch application validation."""

    def test_validate_patch_application_valid(self):
        """Test validation of valid patch application."""
        validator = SyntaxValidator()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
def add(a, b):
    return a + b
""")
            temp_path = f.name

        try:
            patch = """
def add(a, b):
    return a + b + 1
"""
            result = validator.validate_patch_application(temp_path, patch)
            assert result["is_valid"] is True
            assert len(result["errors"]) == 0
        finally:
            os.unlink(temp_path)

    def test_validate_patch_application_invalid(self):
        """Test validation of invalid patch application."""
        validator = SyntaxValidator()

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("""
def add(a, b):
    return a + b
""")
            temp_path = f.name

        try:
            patch = """
def add(a, b
    return a + b
"""
            result = validator.validate_patch_application(temp_path, patch)
            assert result["is_valid"] is False
            assert len(result["errors"]) > 0
        finally:
            os.unlink(temp_path)

    def test_validate_patch_application_file_not_found(self):
        """Test validation with non-existent file."""
        validator = SyntaxValidator()

        patch = """
def add(a, b):
    return a + b
"""
        with pytest.raises(FileNotFoundError):
            validator.validate_patch_application("/nonexistent/file.py", patch)


class TestErrorDetails:
    """Test detailed error information."""

    def test_get_validation_errors_with_line_numbers(self):
        """Test getting validation errors with line numbers."""
        validator = SyntaxValidator()
        code = """
def hello():
return "world"
"""
        result = validator.validate_python(code)
        assert result["is_valid"] is False
        assert len(result["line_numbers"]) > 0
        assert 3 in result["line_numbers"]  # Line 3 has indentation error

    def test_error_message_clarity(self):
        """Test that error messages are clear and helpful."""
        validator = SyntaxValidator()
        code = """
def hello(
    return "world"
"""
        result = validator.validate_python(code)
        assert result["is_valid"] is False
        error_msg = result["errors"][0].lower()
        # Error message should contain information about the syntax issue
        assert any(word in error_msg for word in ["syntax", "error", "closed", "unexpected"])


class TestComplexScenarios:
    """Test complex validation scenarios."""

    def test_validate_multiline_strings(self):
        """Test validation of code with multiline strings."""
        validator = SyntaxValidator()
        code = '''
def doc():
    """
    This is a multiline
    docstring.
    """
    return True
'''
        result = validator.validate_python(code)
        assert result["is_valid"] is True

    def test_validate_nested_functions(self):
        """Test validation of nested functions."""
        validator = SyntaxValidator()
        code = """
def outer():
    def inner():
        return 42
    return inner()
"""
        result = validator.validate_python(code)
        assert result["is_valid"] is True

    def test_validate_class_definition(self):
        """Test validation of class definitions."""
        validator = SyntaxValidator()
        code = """
class MyClass:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1
"""
        result = validator.validate_python(code)
        assert result["is_valid"] is True
