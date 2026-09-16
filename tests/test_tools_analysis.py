"""Tests for code analysis tools.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Tests for Task 1.4: Code Analysis Tool Implementation
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest

from swe_agent.tools.analysis import (
    DetectProjectTypeTool,
    GetImportsTool,
    ParseASTTool,
    SyntaxCheckTool,
)


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


class TestSyntaxCheckTool:
    """Test SyntaxCheckTool for multiple languages."""

    def test_valid_python_code(self, temp_workspace: Path):
        """Test syntax check with valid Python code."""
        tool = SyntaxCheckTool()
        py_file = temp_workspace / "valid.py"
        py_file.write_text("def hello():\n    return 'world'\n")

        result = tool.execute(file_path=str(py_file))

        assert result.error is None
        assert result.output["valid"] is True
        assert result.output["language"] == "python"
        assert result.truncated is False

    def test_invalid_python_code(self, temp_workspace: Path):
        """Test syntax check with invalid Python code."""
        tool = SyntaxCheckTool()
        py_file = temp_workspace / "invalid.py"
        py_file.write_text("def hello(\n    return 'missing colon and paren'\n")

        result = tool.execute(file_path=str(py_file))

        assert result.error is None
        assert result.output["valid"] is False
        assert result.output["language"] == "python"
        assert "error_message" in result.output
        assert len(result.output["error_message"]) > 0

    def test_valid_javascript_code(self, temp_workspace: Path):
        """Test syntax check with valid JavaScript code."""
        tool = SyntaxCheckTool()
        js_file = temp_workspace / "valid.js"
        js_file.write_text("function hello() {\n    return 'world';\n}\n")

        result = tool.execute(file_path=str(js_file))

        assert result.error is None
        assert result.output["valid"] is True
        assert result.output["language"] == "javascript"

    def test_invalid_javascript_code(self, temp_workspace: Path):
        """Test syntax check with invalid JavaScript code."""
        tool = SyntaxCheckTool()
        js_file = temp_workspace / "invalid.js"
        js_file.write_text("function hello( {\n    return 'missing paren';\n}\n")

        result = tool.execute(file_path=str(js_file))

        assert result.error is None
        assert result.output["valid"] is False
        assert result.output["language"] == "javascript"

    def test_unsupported_language(self, temp_workspace: Path):
        """Test syntax check with unsupported file extension."""
        tool = SyntaxCheckTool()
        file = temp_workspace / "test.xyz"
        file.write_text("some content")

        result = tool.execute(file_path=str(file))

        assert result.error is not None
        assert "not supported" in result.error.lower()

    def test_nonexistent_file(self):
        """Test syntax check with non-existent file."""
        tool = SyntaxCheckTool()

        result = tool.execute(file_path="/nonexistent/file.py")

        assert result.error is not None
        assert "not found" in result.error.lower()


class TestParseASTTool:
    """Test ParseASTTool for AST parsing."""

    def test_parse_python_ast(self, temp_workspace: Path):
        """Test AST parsing of Python code."""
        tool = ParseASTTool()
        py_file = temp_workspace / "test.py"
        py_file.write_text(
            """def greet(name):
    return f"Hello, {name}"

class Person:
    def __init__(self, name):
        self.name = name
"""
        )

        result = tool.execute(file_path=str(py_file))

        assert result.error is None
        assert "tree" in result.output
        assert "function_definitions" in result.output
        assert "class_definitions" in result.output
        assert len(result.output["function_definitions"]) >= 1
        assert len(result.output["class_definitions"]) >= 1

    def test_parse_javascript_ast(self, temp_workspace: Path):
        """Test AST parsing of JavaScript code."""
        tool = ParseASTTool()
        js_file = temp_workspace / "test.js"
        js_file.write_text(
            """function greet(name) {
    return "Hello, " + name;
}

class Person {
    constructor(name) {
        this.name = name;
    }
}
"""
        )

        result = tool.execute(file_path=str(js_file))

        assert result.error is None
        assert "tree" in result.output
        assert "function_definitions" in result.output
        assert "class_definitions" in result.output

    def test_parse_invalid_syntax(self, temp_workspace: Path):
        """Test AST parsing with syntax errors."""
        tool = ParseASTTool()
        py_file = temp_workspace / "invalid.py"
        py_file.write_text("def incomplete(")

        result = tool.execute(file_path=str(py_file))

        # Should still parse but may have error nodes
        assert result.error is None
        assert "tree" in result.output
        assert result.output.get("has_errors", False) is True


class TestGetImportsTool:
    """Test GetImportsTool for import extraction."""

    def test_python_imports_simple(self, temp_workspace: Path):
        """Test extracting simple Python imports."""
        tool = GetImportsTool()
        py_file = temp_workspace / "test.py"
        py_file.write_text(
            """import os
import sys
from pathlib import Path
from typing import List, Dict
"""
        )

        result = tool.execute(file_path=str(py_file))

        assert result.error is None
        assert "imports" in result.output
        imports = result.output["imports"]
        assert any("os" in imp for imp in imports)
        assert any("sys" in imp for imp in imports)
        assert any("pathlib" in imp for imp in imports)
        assert any("typing" in imp for imp in imports)

    def test_python_imports_complex(self, temp_workspace: Path):
        """Test extracting complex Python imports."""
        tool = GetImportsTool()
        py_file = temp_workspace / "test.py"
        py_file.write_text(
            """import numpy as np
from collections.abc import Iterable
from .local_module import LocalClass
from ..parent_module import ParentClass
"""
        )

        result = tool.execute(file_path=str(py_file))

        assert result.error is None
        imports = result.output["imports"]
        assert len(imports) >= 4

    def test_javascript_imports(self, temp_workspace: Path):
        """Test extracting JavaScript imports."""
        tool = GetImportsTool()
        js_file = temp_workspace / "test.js"
        js_file.write_text(
            """import React from 'react';
import { useState, useEffect } from 'react';
const axios = require('axios');
const { join } = require('path');
"""
        )

        result = tool.execute(file_path=str(js_file))

        assert result.error is None
        imports = result.output["imports"]
        assert any("react" in imp for imp in imports)
        assert any("axios" in imp for imp in imports)
        assert any("path" in imp for imp in imports)

    def test_java_imports(self, temp_workspace: Path):
        """Test extracting Java imports."""
        tool = GetImportsTool()
        java_file = temp_workspace / "Test.java"
        java_file.write_text(
            """package com.example;

import java.util.List;
import java.util.ArrayList;
import java.io.File;
import static java.lang.Math.PI;
"""
        )

        result = tool.execute(file_path=str(java_file))

        assert result.error is None
        imports = result.output["imports"]
        assert any("java.util.List" in imp for imp in imports)
        assert any("java.util.ArrayList" in imp for imp in imports)
        assert any("java.io.File" in imp for imp in imports)

    def test_no_imports(self, temp_workspace: Path):
        """Test file with no imports."""
        tool = GetImportsTool()
        py_file = temp_workspace / "test.py"
        py_file.write_text(
            """def hello():
    return "world"
"""
        )

        result = tool.execute(file_path=str(py_file))

        assert result.error is None
        assert result.output["imports"] == []


class TestDetectProjectTypeTool:
    """Test DetectProjectTypeTool for project type detection."""

    def test_detect_python_project(self, temp_workspace: Path):
        """Test detecting Python project."""
        tool = DetectProjectTypeTool()
        (temp_workspace / "requirements.txt").write_text("flask==2.0.0\n")
        (temp_workspace / "setup.py").write_text("from setuptools import setup\n")

        result = tool.execute(directory=str(temp_workspace))

        assert result.error is None
        assert "python" in result.output["project_types"]
        assert "indicators" in result.output

    def test_detect_nodejs_project(self, temp_workspace: Path):
        """Test detecting Node.js project."""
        tool = DetectProjectTypeTool()
        (temp_workspace / "package.json").write_text('{"name": "test-project"}\n')

        result = tool.execute(directory=str(temp_workspace))

        assert result.error is None
        assert "nodejs" in result.output["project_types"]

    def test_detect_java_project(self, temp_workspace: Path):
        """Test detecting Java project."""
        tool = DetectProjectTypeTool()
        (temp_workspace / "pom.xml").write_text("<project></project>\n")

        result = tool.execute(directory=str(temp_workspace))

        assert result.error is None
        assert "java" in result.output["project_types"]

    def test_detect_rust_project(self, temp_workspace: Path):
        """Test detecting Rust project."""
        tool = DetectProjectTypeTool()
        (temp_workspace / "Cargo.toml").write_text('[package]\nname = "test"\n')

        result = tool.execute(directory=str(temp_workspace))

        assert result.error is None
        assert "rust" in result.output["project_types"]

    def test_detect_multiple_project_types(self, temp_workspace: Path):
        """Test detecting multiple project types (polyglot project)."""
        tool = DetectProjectTypeTool()
        (temp_workspace / "package.json").write_text('{"name": "test"}\n')
        (temp_workspace / "requirements.txt").write_text("flask==2.0.0\n")

        result = tool.execute(directory=str(temp_workspace))

        assert result.error is None
        assert len(result.output["project_types"]) >= 2
        assert "python" in result.output["project_types"]
        assert "nodejs" in result.output["project_types"]

    def test_detect_no_project_type(self, temp_workspace: Path):
        """Test directory with no recognizable project type."""
        tool = DetectProjectTypeTool()
        (temp_workspace / "random.txt").write_text("just a file\n")

        result = tool.execute(directory=str(temp_workspace))

        assert result.error is None
        assert result.output["project_types"] == []

    def test_nonexistent_directory(self):
        """Test with non-existent directory."""
        tool = DetectProjectTypeTool()

        result = tool.execute(directory="/nonexistent/directory")

        assert result.error is not None
        assert "not found" in result.error.lower()
