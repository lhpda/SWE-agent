"""Tests for project setup and infrastructure (Task 0.1)."""

import sys
import subprocess
from pathlib import Path

import pytest


class TestProjectStructure:
    """Test basic project structure."""

    def test_src_directory_exists(self):
        """Verify src/ directory exists."""
        src_dir = Path("src")
        assert src_dir.exists()
        assert src_dir.is_dir()

    def test_tests_directory_exists(self):
        """Verify tests/ directory exists."""
        tests_dir = Path("tests")
        assert tests_dir.exists()
        assert tests_dir.is_dir()

    def test_docs_directory_exists(self):
        """Verify docs/ directory exists."""
        docs_dir = Path("docs")
        assert docs_dir.exists()
        assert docs_dir.is_dir()

    def test_swe_agent_package_exists(self):
        """Verify swe_agent package exists."""
        package_dir = Path("src/swe_agent")
        assert package_dir.exists()
        assert package_dir.is_dir()
        assert (package_dir / "__init__.py").exists()


class TestPythonVersion:
    """Test Python version requirements."""

    def test_python_version_is_3_11_or_higher(self):
        """Verify Python version is 3.11+."""
        version_info = sys.version_info
        assert version_info.major == 3
        assert version_info.minor >= 11, f"Python 3.11+ required, got {version_info.major}.{version_info.minor}"


class TestDependencies:
    """Test that core dependencies are installed."""

    def test_anthropic_import(self):
        """Verify anthropic package is installed."""
        import anthropic
        assert anthropic is not None

    def test_docker_import(self):
        """Verify docker package is installed."""
        import docker
        assert docker is not None

    def test_pydantic_import(self):
        """Verify pydantic package is installed."""
        import pydantic
        assert pydantic is not None
        # Verify it's v2
        assert hasattr(pydantic, "BaseModel")

    def test_gitpython_import(self):
        """Verify gitpython package is installed."""
        import git
        assert git is not None

    def test_structlog_import(self):
        """Verify structlog package is installed."""
        import structlog
        assert structlog is not None


class TestDevDependencies:
    """Test that development dependencies are installed."""

    def test_pytest_import(self):
        """Verify pytest is installed."""
        import pytest
        assert pytest is not None

    def test_black_available(self):
        """Verify black is available."""
        result = subprocess.run(
            ["poetry", "run", "black", "--version"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "black" in result.stdout.lower()

    def test_ruff_available(self):
        """Verify ruff is available."""
        result = subprocess.run(
            ["poetry", "run", "ruff", "--version"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "ruff" in result.stdout.lower()

    def test_mypy_available(self):
        """Verify mypy is available."""
        result = subprocess.run(
            ["poetry", "run", "mypy", "--version"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "mypy" in result.stdout.lower()


class TestProjectFiles:
    """Test that essential project files exist."""

    def test_pyproject_toml_exists(self):
        """Verify pyproject.toml exists."""
        pyproject = Path("pyproject.toml")
        assert pyproject.exists()
        assert pyproject.is_file()

    def test_readme_exists(self):
        """Verify README.md exists."""
        readme = Path("README.md")
        assert readme.exists()
        assert readme.is_file()

    def test_gitignore_exists(self):
        """Verify .gitignore exists."""
        gitignore = Path(".gitignore")
        assert gitignore.exists()
        assert gitignore.is_file()

    def test_pyproject_toml_has_required_sections(self):
        """Verify pyproject.toml has required configuration sections."""
        pyproject = Path("pyproject.toml")
        content = pyproject.read_text()

        # Check for essential sections
        assert "[tool.poetry]" in content
        assert "[tool.poetry.dependencies]" in content
        assert "[tool.poetry.group.dev.dependencies]" in content
        assert "[build-system]" in content

        # Check for core dependencies
        assert "anthropic" in content
        assert "docker" in content
        assert "pydantic" in content
        assert "gitpython" in content
        assert "structlog" in content

        # Check for dev dependencies
        assert "pytest" in content
        assert "black" in content
        assert "ruff" in content
        assert "mypy" in content
