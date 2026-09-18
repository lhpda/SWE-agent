"""Unit tests for project type and test framework detection.

Based on TASKS.md Task 4.1: Project Type & Test Framework Detection
Following TDD: Tests written first, implementation follows.
"""

import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest

from swe_agent.agents.reproduction.detector import (
    ProjectTypeDetector,
    TestFrameworkDetector,
    TestCommandInferrer,
    DependencyInstallDetector,
)


class TestProjectTypeDetector:
    """Test project type detection from characteristic files."""

    def test_detect_python_from_requirements_txt(self, tmp_path: Path):
        """Test Python project detection via requirements.txt."""
        (tmp_path / "requirements.txt").write_text("pytest>=7.0.0\nrequests==2.28.0\n")

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "python"
        assert "requirements.txt" in result["indicators"]

    def test_detect_python_from_pyproject_toml(self, tmp_path: Path):
        """Test Python project detection via pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n")

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "python"
        assert "pyproject.toml" in result["indicators"]

    def test_detect_python_from_setup_py(self, tmp_path: Path):
        """Test Python project detection via setup.py."""
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "python"
        assert "setup.py" in result["indicators"]

    def test_detect_python_from_pipfile(self, tmp_path: Path):
        """Test Python project detection via Pipfile."""
        (tmp_path / "Pipfile").write_text("[[source]]\nurl = 'https://pypi.org/simple'\n")

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "python"
        assert "Pipfile" in result["indicators"]

    def test_detect_nodejs_from_package_json(self, tmp_path: Path):
        """Test Node.js project detection via package.json."""
        (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "nodejs"
        assert "package.json" in result["indicators"]

    def test_detect_nodejs_from_package_lock(self, tmp_path: Path):
        """Test Node.js project detection via package-lock.json."""
        (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 2}')

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "nodejs"
        assert "package-lock.json" in result["indicators"]

    def test_detect_java_from_pom_xml(self, tmp_path: Path):
        """Test Java project detection via pom.xml."""
        (tmp_path / "pom.xml").write_text("<project><modelVersion>4.0.0</modelVersion></project>")

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "java"
        assert "pom.xml" in result["indicators"]

    def test_detect_java_from_build_gradle(self, tmp_path: Path):
        """Test Java project detection via build.gradle."""
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }")

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "java"
        assert "build.gradle" in result["indicators"]

    def test_detect_rust_from_cargo_toml(self, tmp_path: Path):
        """Test Rust project detection via Cargo.toml."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\nversion = "0.1.0"\n')

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "rust"
        assert "Cargo.toml" in result["indicators"]

    def test_detect_unknown_project_type(self, tmp_path: Path):
        """Test detection returns unknown for unrecognized projects."""
        (tmp_path / "random.txt").write_text("nothing")

        detector = ProjectTypeDetector(str(tmp_path))
        result = detector.detect()

        assert result["project_type"] == "unknown"
        assert result["indicators"] == []


class TestTestFrameworkDetector:
    """Test test framework detection from project configuration."""

    def test_detect_pytest_from_pytest_ini(self, tmp_path: Path):
        """Test pytest detection via pytest.ini."""
        (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
        (tmp_path / "requirements.txt").write_text("pytest\n")

        detector = TestFrameworkDetector(str(tmp_path), "python")
        result = detector.detect()

        assert result["framework"] == "pytest"
        assert "pytest.ini" in result["indicators"]

    def test_detect_pytest_from_requirements(self, tmp_path: Path):
        """Test pytest detection from requirements.txt."""
        (tmp_path / "requirements.txt").write_text("pytest>=7.0.0\nrequests\n")

        detector = TestFrameworkDetector(str(tmp_path), "python")
        result = detector.detect()

        assert result["framework"] == "pytest"
        assert "requirements.txt" in result["indicators"]

    def test_detect_pytest_from_pyproject_toml(self, tmp_path: Path):
        """Test pytest detection from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
        )

        detector = TestFrameworkDetector(str(tmp_path), "python")
        result = detector.detect()

        assert result["framework"] == "pytest"

    def test_detect_unittest_from_setup_py(self, tmp_path: Path):
        """Test unittest detection from setup.py."""
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(test_suite='tests')"
        )

        detector = TestFrameworkDetector(str(tmp_path), "python")
        result = detector.detect()

        assert result["framework"] == "unittest"

    def test_detect_jest_from_package_json(self, tmp_path: Path):
        """Test Jest detection from package.json."""
        (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29.0.0"}}')

        detector = TestFrameworkDetector(str(tmp_path), "nodejs")
        result = detector.detect()

        assert result["framework"] == "jest"

    def test_detect_mocha_from_package_json(self, tmp_path: Path):
        """Test Mocha detection from package.json."""
        (tmp_path / "package.json").write_text('{"devDependencies": {"mocha": "^10.0.0"}}')

        detector = TestFrameworkDetector(str(tmp_path), "nodejs")
        result = detector.detect()

        assert result["framework"] == "mocha"

    def test_detect_junit_from_pom_xml(self, tmp_path: Path):
        """Test JUnit detection from pom.xml."""
        (tmp_path / "pom.xml").write_text(
            "<project><dependencies><dependency>"
            "<artifactId>junit</artifactId></dependency></dependencies></project>"
        )

        detector = TestFrameworkDetector(str(tmp_path), "java")
        result = detector.detect()

        assert result["framework"] == "junit"

    def test_detect_cargo_test_for_rust(self, tmp_path: Path):
        """Test cargo test detection for Rust projects."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')

        detector = TestFrameworkDetector(str(tmp_path), "rust")
        result = detector.detect()

        assert result["framework"] == "cargo-test"


class TestTestCommandInferrer:
    """Test test command inference from project configuration."""

    def test_infer_pytest_command(self, tmp_path: Path):
        """Test pytest command inference."""
        (tmp_path / "pytest.ini").write_text("[pytest]\n")

        inferrer = TestCommandInferrer(str(tmp_path), "python", "pytest")
        result = inferrer.infer()

        assert result["command"] == "pytest"
        assert result["full_command"] == ["pytest"]

    def test_infer_pytest_with_coverage(self, tmp_path: Path):
        """Test pytest command with coverage options."""
        (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --cov=src\n")

        inferrer = TestCommandInferrer(str(tmp_path), "python", "pytest")
        result = inferrer.infer()

        assert "--cov" in result["inferred_options"]

    def test_infer_npm_test_from_package_json(self, tmp_path: Path):
        """Test npm test command inference from package.json."""
        (tmp_path / "package.json").write_text('{"scripts": {"test": "jest --coverage"}}')

        inferrer = TestCommandInferrer(str(tmp_path), "nodejs", "jest")
        result = inferrer.infer()

        assert result["command"] == "npm test"

    def test_infer_jest_direct_command(self, tmp_path: Path):
        """Test direct jest command when no npm script."""
        (tmp_path / "package.json").write_text('{"name": "test"}')

        inferrer = TestCommandInferrer(str(tmp_path), "nodejs", "jest")
        result = inferrer.infer()

        assert result["command"] in ["jest", "npx jest"]

    def test_infer_maven_test_command(self, tmp_path: Path):
        """Test Maven test command inference."""
        (tmp_path / "pom.xml").write_text("<project></project>")

        inferrer = TestCommandInferrer(str(tmp_path), "java", "junit")
        result = inferrer.infer()

        assert result["command"] == "mvn test"

    def test_infer_gradle_test_command(self, tmp_path: Path):
        """Test Gradle test command inference."""
        (tmp_path / "build.gradle").write_text("plugins { id 'java' }")

        inferrer = TestCommandInferrer(str(tmp_path), "java", "junit")
        result = inferrer.infer()

        assert result["command"] in ["gradle test", "./gradlew test"]

    def test_infer_cargo_test_command(self, tmp_path: Path):
        """Test cargo test command inference."""
        (tmp_path / "Cargo.toml").write_text("[package]\n")

        inferrer = TestCommandInferrer(str(tmp_path), "rust", "cargo-test")
        result = inferrer.infer()

        assert result["command"] == "cargo test"


class TestDependencyInstallDetector:
    """Test dependency installation requirement detection."""

    def test_python_needs_install_missing_venv(self, tmp_path: Path):
        """Test Python project needs pip install when venv missing."""
        (tmp_path / "requirements.txt").write_text("pytest\n")

        detector = DependencyInstallDetector(str(tmp_path), "python")
        result = detector.needs_install()

        assert result["needs_install"] is True
        assert result["reason"] == "dependencies_file_exists"

    def test_nodejs_needs_install_missing_node_modules(self, tmp_path: Path):
        """Test Node.js project needs npm install when node_modules missing."""
        (tmp_path / "package.json").write_text('{"dependencies": {"express": "^4.0.0"}}')

        detector = DependencyInstallDetector(str(tmp_path), "nodejs")
        result = detector.needs_install()

        assert result["needs_install"] is True
        assert result["install_command"] == "npm install"

    def test_nodejs_no_install_when_node_modules_exists(self, tmp_path: Path):
        """Test Node.js project doesn't need install when node_modules exists."""
        (tmp_path / "package.json").write_text('{"dependencies": {}}')
        (tmp_path / "node_modules").mkdir()

        detector = DependencyInstallDetector(str(tmp_path), "nodejs")
        result = detector.needs_install()

        assert result["needs_install"] is False

    def test_java_maven_needs_install(self, tmp_path: Path):
        """Test Java Maven project dependency detection."""
        (tmp_path / "pom.xml").write_text("<project><dependencies></dependencies></project>")

        detector = DependencyInstallDetector(str(tmp_path), "java")
        result = detector.needs_install()

        assert result["needs_install"] is True
        assert "mvn" in result["install_command"]

    def test_rust_needs_cargo_build(self, tmp_path: Path):
        """Test Rust project needs cargo build."""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')

        detector = DependencyInstallDetector(str(tmp_path), "rust")
        result = detector.needs_install()

        assert result["needs_install"] is True
        assert result["install_command"] == "cargo build"

    def test_no_dependency_file_no_install(self, tmp_path: Path):
        """Test project without dependency files doesn't need install."""
        detector = DependencyInstallDetector(str(tmp_path), "python")
        result = detector.needs_install()

        assert result["needs_install"] is False


class TestIntegrationScenarios:
    """Integration tests for complete detection workflow."""

    def test_complete_python_pytest_project(self, tmp_path: Path):
        """Test complete detection for a Python pytest project."""
        (tmp_path / "requirements.txt").write_text("pytest>=7.0.0\n")
        (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
        (tmp_path / "tests").mkdir()

        # Detect project type
        proj_detector = ProjectTypeDetector(str(tmp_path))
        proj_result = proj_detector.detect()
        assert proj_result["project_type"] == "python"

        # Detect test framework
        test_detector = TestFrameworkDetector(str(tmp_path), "python")
        test_result = test_detector.detect()
        assert test_result["framework"] == "pytest"

        # Infer test command
        cmd_inferrer = TestCommandInferrer(str(tmp_path), "python", "pytest")
        cmd_result = cmd_inferrer.infer()
        assert cmd_result["command"] == "pytest"

        # Check dependency install
        dep_detector = DependencyInstallDetector(str(tmp_path), "python")
        dep_result = dep_detector.needs_install()
        assert dep_result["needs_install"] is True

    def test_complete_nodejs_jest_project(self, tmp_path: Path):
        """Test complete detection for a Node.js jest project."""
        (tmp_path / "package.json").write_text(
            '{"scripts": {"test": "jest"}, "devDependencies": {"jest": "^29.0.0"}}'
        )

        # Detect project type
        proj_detector = ProjectTypeDetector(str(tmp_path))
        proj_result = proj_detector.detect()
        assert proj_result["project_type"] == "nodejs"

        # Detect test framework
        test_detector = TestFrameworkDetector(str(tmp_path), "nodejs")
        test_result = test_detector.detect()
        assert test_result["framework"] == "jest"

        # Infer test command
        cmd_inferrer = TestCommandInferrer(str(tmp_path), "nodejs", "jest")
        cmd_result = cmd_inferrer.infer()
        assert cmd_result["command"] == "npm test"

        # Check dependency install
        dep_detector = DependencyInstallDetector(str(tmp_path), "nodejs")
        dep_result = dep_detector.needs_install()
        assert dep_result["needs_install"] is True
