"""Project type and test framework detection for reproduction environment setup.

Based on TASKS.md Task 4.1: Project Type & Test Framework Detection
Implements detectors for project type, test framework, test commands, and dependencies.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

from swe_agent.logging import get_logger

logger = get_logger(__name__)


class ProjectTypeDetector:
    """Detect project type based on characteristic files in the directory.

    Supports Python, Node.js, Java, Rust, Go, Ruby, and PHP projects.
    """

    # Project type indicators mapping
    PROJECT_INDICATORS = {
        "python": [
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "Pipfile",
            "setup.cfg",
            "poetry.lock",
        ],
        "nodejs": [
            "package.json",
            "package-lock.json",
            "yarn.lock",
        ],
        "java": [
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
        ],
        "rust": [
            "Cargo.toml",
        ],
        "go": [
            "go.mod",
        ],
        "ruby": [
            "Gemfile",
        ],
        "php": [
            "composer.json",
        ],
    }

    def __init__(self, directory: str):
        """Initialize detector with project directory.

        Args:
            directory: Path to project directory
        """
        self.directory = Path(directory)

    def detect(self) -> Dict[str, Any]:
        """Detect project type by checking for characteristic files.

        Returns:
            Dict with project_type and indicators found
        """
        if not self.directory.exists() or not self.directory.is_dir():
            logger.warning("project_type_detector_invalid_dir", directory=str(self.directory))
            return {
                "project_type": "unknown",
                "indicators": [],
            }

        # Check each project type
        for project_type, indicators in self.PROJECT_INDICATORS.items():
            found_indicators = []
            for indicator in indicators:
                if (self.directory / indicator).exists():
                    found_indicators.append(indicator)

            # Return first match
            if found_indicators:
                logger.debug(
                    "project_type_detected",
                    project_type=project_type,
                    indicators=found_indicators,
                )
                return {
                    "project_type": project_type,
                    "indicators": found_indicators,
                }

        # No matches found
        logger.debug("project_type_unknown", directory=str(self.directory))
        return {
            "project_type": "unknown",
            "indicators": [],
        }


class TestFrameworkDetector:
    """Detect test framework based on project configuration files.

    Supports pytest, unittest, jest, mocha, junit, testng, cargo test, etc.
    """

    def __init__(self, directory: str, project_type: str):
        """Initialize detector with directory and project type.

        Args:
            directory: Path to project directory
            project_type: Detected project type (python, nodejs, java, rust, etc.)
        """
        self.directory = Path(directory)
        self.project_type = project_type

    def detect(self) -> Dict[str, Any]:
        """Detect test framework based on project type.

        Returns:
            Dict with framework name and indicators
        """
        if self.project_type == "python":
            return self._detect_python_framework()
        elif self.project_type == "nodejs":
            return self._detect_nodejs_framework()
        elif self.project_type == "java":
            return self._detect_java_framework()
        elif self.project_type == "rust":
            return self._detect_rust_framework()
        else:
            return {
                "framework": "unknown",
                "indicators": [],
            }

    def _detect_python_framework(self) -> Dict[str, Any]:
        """Detect Python test framework (pytest, unittest, nose, tox)."""
        indicators = []

        # Check for pytest.ini
        if (self.directory / "pytest.ini").exists():
            indicators.append("pytest.ini")
            return {"framework": "pytest", "indicators": indicators}

        # Check for pyproject.toml with pytest config
        pyproject_path = self.directory / "pyproject.toml"
        if pyproject_path.exists():
            content = pyproject_path.read_text(encoding="utf-8", errors="ignore")
            if "tool.pytest" in content:
                indicators.append("pyproject.toml")
                return {"framework": "pytest", "indicators": indicators}

        # Check for pytest in requirements.txt
        requirements_path = self.directory / "requirements.txt"
        if requirements_path.exists():
            content = requirements_path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"^\s*pytest", content, re.MULTILINE):
                indicators.append("requirements.txt")
                return {"framework": "pytest", "indicators": indicators}

        # Check for tox.ini
        if (self.directory / "tox.ini").exists():
            indicators.append("tox.ini")
            return {"framework": "pytest", "indicators": indicators}

        # Check for setup.py with test_suite
        setup_path = self.directory / "setup.py"
        if setup_path.exists():
            content = setup_path.read_text(encoding="utf-8", errors="ignore")
            if "test_suite" in content:
                indicators.append("setup.py")
                return {"framework": "unittest", "indicators": indicators}

        # Default to pytest for Python projects
        return {"framework": "pytest", "indicators": indicators}

    def _detect_nodejs_framework(self) -> Dict[str, Any]:
        """Detect Node.js test framework (jest, mocha, jasmine, ava)."""
        indicators = []

        package_json_path = self.directory / "package.json"
        if not package_json_path.exists():
            return {"framework": "unknown", "indicators": indicators}

        try:
            content = package_json_path.read_text(encoding="utf-8", errors="ignore")
            package_data = json.loads(content)

            # Check devDependencies
            dev_deps = package_data.get("devDependencies", {})
            dependencies = package_data.get("dependencies", {})
            all_deps = {**dev_deps, **dependencies}

            # Priority order: jest > mocha > jasmine > ava
            if "jest" in all_deps:
                indicators.append("package.json")
                return {"framework": "jest", "indicators": indicators}

            if "mocha" in all_deps:
                indicators.append("package.json")
                return {"framework": "mocha", "indicators": indicators}

            if "jasmine" in all_deps:
                indicators.append("package.json")
                return {"framework": "jasmine", "indicators": indicators}

            if "ava" in all_deps:
                indicators.append("package.json")
                return {"framework": "ava", "indicators": indicators}

            # Check for test script
            scripts = package_data.get("scripts", {})
            if "test" in scripts:
                indicators.append("package.json")
                return {"framework": "npm-test", "indicators": indicators}

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("nodejs_framework_detection_error", error=str(e))

        return {"framework": "unknown", "indicators": indicators}

    def _detect_java_framework(self) -> Dict[str, Any]:
        """Detect Java test framework (junit, testng)."""
        indicators = []

        # Check pom.xml for Maven projects
        pom_path = self.directory / "pom.xml"
        if pom_path.exists():
            content = pom_path.read_text(encoding="utf-8", errors="ignore")
            if "junit" in content.lower():
                indicators.append("pom.xml")
                return {"framework": "junit", "indicators": indicators}
            if "testng" in content.lower():
                indicators.append("pom.xml")
                return {"framework": "testng", "indicators": indicators}

        # Check build.gradle for Gradle projects
        for gradle_file in ["build.gradle", "build.gradle.kts"]:
            gradle_path = self.directory / gradle_file
            if gradle_path.exists():
                content = gradle_path.read_text(encoding="utf-8", errors="ignore")
                if "junit" in content.lower():
                    indicators.append(gradle_file)
                    return {"framework": "junit", "indicators": indicators}
                if "testng" in content.lower():
                    indicators.append(gradle_file)
                    return {"framework": "testng", "indicators": indicators}

        # Default to junit for Java projects
        return {"framework": "junit", "indicators": indicators}

    def _detect_rust_framework(self) -> Dict[str, Any]:
        """Detect Rust test framework (always cargo test)."""
        return {"framework": "cargo-test", "indicators": ["Cargo.toml"]}


class TestCommandInferrer:
    """Infer test command from project configuration and detected framework.

    Priority: explicit configuration > common conventions > default commands
    """

    def __init__(self, directory: str, project_type: str, framework: str):
        """Initialize inferrer with directory, project type, and framework.

        Args:
            directory: Path to project directory
            project_type: Detected project type
            framework: Detected test framework
        """
        self.directory = Path(directory)
        self.project_type = project_type
        self.framework = framework

    def infer(self) -> Dict[str, Any]:
        """Infer test command based on project type and framework.

        Returns:
            Dict with command, full_command list, and inferred_options
        """
        if self.project_type == "python":
            return self._infer_python_command()
        elif self.project_type == "nodejs":
            return self._infer_nodejs_command()
        elif self.project_type == "java":
            return self._infer_java_command()
        elif self.project_type == "rust":
            return self._infer_rust_command()
        else:
            return {
                "command": "unknown",
                "full_command": [],
                "inferred_options": [],
            }

    def _infer_python_command(self) -> Dict[str, Any]:
        """Infer Python test command."""
        options = []

        # Check for pytest options in pytest.ini
        pytest_ini = self.directory / "pytest.ini"
        if pytest_ini.exists():
            content = pytest_ini.read_text(encoding="utf-8", errors="ignore")
            if "--cov" in content:
                options.append("--cov")

        # Check for pyproject.toml pytest options
        pyproject = self.directory / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            if "--cov" in content:
                options.append("--cov")

        if self.framework == "pytest":
            return {
                "command": "pytest",
                "full_command": ["pytest"],
                "inferred_options": options,
            }
        elif self.framework == "unittest":
            return {
                "command": "python -m unittest",
                "full_command": ["python", "-m", "unittest"],
                "inferred_options": [],
            }

        # Default
        return {
            "command": "pytest",
            "full_command": ["pytest"],
            "inferred_options": options,
        }

    def _infer_nodejs_command(self) -> Dict[str, Any]:
        """Infer Node.js test command."""
        package_json = self.directory / "package.json"

        # Check for npm test script
        if package_json.exists():
            try:
                content = package_json.read_text(encoding="utf-8", errors="ignore")
                data = json.loads(content)
                scripts = data.get("scripts", {})

                if "test" in scripts:
                    return {
                        "command": "npm test",
                        "full_command": ["npm", "test"],
                        "inferred_options": [],
                    }
            except (json.JSONDecodeError, Exception):
                pass

        # Direct framework commands
        if self.framework == "jest":
            return {
                "command": "npx jest",
                "full_command": ["npx", "jest"],
                "inferred_options": [],
            }
        elif self.framework == "mocha":
            return {
                "command": "npx mocha",
                "full_command": ["npx", "mocha"],
                "inferred_options": [],
            }

        # Default
        return {
            "command": "npm test",
            "full_command": ["npm", "test"],
            "inferred_options": [],
        }

    def _infer_java_command(self) -> Dict[str, Any]:
        """Infer Java test command."""
        # Check for Gradle
        if (self.directory / "build.gradle").exists() or \
           (self.directory / "build.gradle.kts").exists():
            # Check for gradlew wrapper
            if (self.directory / "gradlew").exists():
                return {
                    "command": "./gradlew test",
                    "full_command": ["./gradlew", "test"],
                    "inferred_options": [],
                }
            return {
                "command": "gradle test",
                "full_command": ["gradle", "test"],
                "inferred_options": [],
            }

        # Check for Maven
        if (self.directory / "pom.xml").exists():
            return {
                "command": "mvn test",
                "full_command": ["mvn", "test"],
                "inferred_options": [],
            }

        # Default to Maven
        return {
            "command": "mvn test",
            "full_command": ["mvn", "test"],
            "inferred_options": [],
        }

    def _infer_rust_command(self) -> Dict[str, Any]:
        """Infer Rust test command."""
        return {
            "command": "cargo test",
            "full_command": ["cargo", "test"],
            "inferred_options": [],
        }


class DependencyInstallDetector:
    """Detect if dependency installation is required.

    Checks for dependency files and whether dependencies are already installed.
    """

    def __init__(self, directory: str, project_type: str):
        """Initialize detector with directory and project type.

        Args:
            directory: Path to project directory
            project_type: Detected project type
        """
        self.directory = Path(directory)
        self.project_type = project_type

    def needs_install(self) -> Dict[str, Any]:
        """Check if dependencies need to be installed.

        Returns:
            Dict with needs_install, reason, and install_command
        """
        if self.project_type == "python":
            return self._check_python_install()
        elif self.project_type == "nodejs":
            return self._check_nodejs_install()
        elif self.project_type == "java":
            return self._check_java_install()
        elif self.project_type == "rust":
            return self._check_rust_install()
        else:
            return {
                "needs_install": False,
                "reason": "unknown_project_type",
                "install_command": None,
            }

    def _check_python_install(self) -> Dict[str, Any]:
        """Check if Python dependencies need installation."""
        # Check for dependency files
        dep_files = ["requirements.txt", "pyproject.toml", "Pipfile", "setup.py"]
        has_dep_file = any((self.directory / f).exists() for f in dep_files)

        if not has_dep_file:
            return {
                "needs_install": False,
                "reason": "no_dependency_file",
                "install_command": None,
            }

        # If dependency file exists, assume installation needed
        # (virtual env detection is complex and environment-specific)
        install_cmd = "pip install -r requirements.txt"
        if (self.directory / "pyproject.toml").exists():
            install_cmd = "pip install -e ."
        elif (self.directory / "Pipfile").exists():
            install_cmd = "pipenv install"

        return {
            "needs_install": True,
            "reason": "dependencies_file_exists",
            "install_command": install_cmd,
        }

    def _check_nodejs_install(self) -> Dict[str, Any]:
        """Check if Node.js dependencies need installation."""
        package_json = self.directory / "package.json"

        if not package_json.exists():
            return {
                "needs_install": False,
                "reason": "no_package_json",
                "install_command": None,
            }

        # Check if node_modules exists
        node_modules = self.directory / "node_modules"
        if node_modules.exists() and node_modules.is_dir():
            return {
                "needs_install": False,
                "reason": "node_modules_exists",
                "install_command": None,
            }

        # Determine install command
        install_cmd = "npm install"
        if (self.directory / "yarn.lock").exists():
            install_cmd = "yarn install"
        elif (self.directory / "pnpm-lock.yaml").exists():
            install_cmd = "pnpm install"

        return {
            "needs_install": True,
            "reason": "node_modules_missing",
            "install_command": install_cmd,
        }

    def _check_java_install(self) -> Dict[str, Any]:
        """Check if Java dependencies need installation."""
        # Maven project
        if (self.directory / "pom.xml").exists():
            return {
                "needs_install": True,
                "reason": "maven_project",
                "install_command": "mvn install",
            }

        # Gradle project
        if (self.directory / "build.gradle").exists() or \
           (self.directory / "build.gradle.kts").exists():
            install_cmd = "./gradlew build" if (self.directory / "gradlew").exists() else "gradle build"
            return {
                "needs_install": True,
                "reason": "gradle_project",
                "install_command": install_cmd,
            }

        return {
            "needs_install": False,
            "reason": "no_build_file",
            "install_command": None,
        }

    def _check_rust_install(self) -> Dict[str, Any]:
        """Check if Rust dependencies need installation."""
        if (self.directory / "Cargo.toml").exists():
            return {
                "needs_install": True,
                "reason": "cargo_project",
                "install_command": "cargo build",
            }

        return {
            "needs_install": False,
            "reason": "no_cargo_toml",
            "install_command": None,
        }
