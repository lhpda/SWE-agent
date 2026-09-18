"""
Syntax validator for code patches.

Validates syntax of code before and after applying patches.
"""

import ast
import os
from typing import Dict, List, Any


class SyntaxValidator:
    """Validates syntax of code patches."""

    def __init__(self):
        """Initialize the syntax validator."""
        pass

    def validate_python(self, code: str) -> Dict[str, Any]:
        """
        Validate Python syntax.

        Args:
            code: Python code to validate

        Returns:
            Validation result with is_valid, errors, line_numbers, error_type
        """
        if not code or code.strip() == "":
            return {"is_valid": True, "errors": [], "line_numbers": [], "error_type": ""}

        try:
            ast.parse(code)
            return {"is_valid": True, "errors": [], "line_numbers": [], "error_type": ""}
        except SyntaxError as e:
            return {
                "is_valid": False,
                "errors": [str(e)],
                "line_numbers": [e.lineno] if e.lineno else [],
                "error_type": "SyntaxError",
            }
        except IndentationError as e:
            return {
                "is_valid": False,
                "errors": [str(e)],
                "line_numbers": [e.lineno] if e.lineno else [],
                "error_type": "IndentationError",
            }
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [str(e)],
                "line_numbers": [],
                "error_type": type(e).__name__,
            }

    def validate_javascript(self, code: str) -> Dict[str, Any]:
        """
        Validate JavaScript syntax (simplified).

        Args:
            code: JavaScript code to validate

        Returns:
            Validation result (simplified - just checks bracket matching)
        """
        # Simple bracket matching validation
        stack = []
        pairs = {"(": ")", "[": "]", "{": "}"}

        for char in code:
            if char in pairs:
                stack.append(char)
            elif char in pairs.values():
                if not stack or pairs[stack.pop()] != char:
                    return {
                        "is_valid": False,
                        "errors": ["Mismatched brackets"],
                        "line_numbers": [],
                        "error_type": "SyntaxError",
                    }

        if stack:
            return {
                "is_valid": False,
                "errors": ["Unclosed brackets"],
                "line_numbers": [],
                "error_type": "SyntaxError",
            }

        return {"is_valid": True, "errors": [], "line_numbers": [], "error_type": ""}

    def validate_patch_application(self, file_path: str, patch: str) -> Dict[str, Any]:
        """
        Validate syntax after applying a patch.

        Args:
            file_path: Path to the original file
            patch: Patch content (new code to replace file)

        Returns:
            Validation result

        Raises:
            FileNotFoundError: If file_path does not exist
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Validate the patched code
        if file_path.endswith(".py"):
            return self.validate_python(patch)
        elif file_path.endswith(".js"):
            return self.validate_javascript(patch)
        else:
            # Unknown file type - assume valid
            return {"is_valid": True, "errors": [], "line_numbers": [], "error_type": ""}

    def check_imports(self, code: str) -> Dict[str, Any]:
        """
        Check if import statements are valid.

        Args:
            code: Python code to check

        Returns:
            Validation result
        """
        # Extract import lines
        lines = code.split("\n")
        import_lines = [line for line in lines if line.strip().startswith(("import ", "from "))]

        if not import_lines:
            return {"is_valid": True, "errors": [], "line_numbers": [], "error_type": ""}

        # Try to parse just the imports
        import_code = "\n".join(import_lines)
        try:
            ast.parse(import_code)
            return {"is_valid": True, "errors": [], "line_numbers": [], "error_type": ""}
        except SyntaxError as e:
            return {
                "is_valid": False,
                "errors": [f"Invalid import statement: {e}"],
                "line_numbers": [e.lineno] if e.lineno else [],
                "error_type": "SyntaxError",
            }
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Import validation error: {e}"],
                "line_numbers": [],
                "error_type": type(e).__name__,
            }

    def get_validation_errors(self, result: Dict[str, Any]) -> List[str]:
        """
        Get detailed validation errors from a result.

        Args:
            result: Validation result dictionary

        Returns:
            List of error messages
        """
        return result.get("errors", [])
