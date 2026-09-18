"""Code analysis tools for syntax checking, AST parsing, and project detection.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Implements Task 1.4: Code Analysis Tool Implementation
"""

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from swe_agent.logging import get_logger
from swe_agent.tools.base import Tool, ToolResult

logger = get_logger(__name__)


class SyntaxCheckTool(Tool):
    """Check syntax validity of source code files.

    Supports Python, JavaScript, Java, and Rust using native compilers/interpreters.
    """

    name = "syntax_check"
    description = "Check syntax validity of source code files"
    parameters_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the source file to check",
            },
        },
        "required": ["file_path"],
    }

    # Language detection and command mapping
    LANGUAGE_COMMANDS = {
        ".py": ("python", ["python", "-m", "py_compile"]),
        ".js": ("javascript", ["node", "--check"]),
        ".java": ("java", ["javac", "-Xstdout"]),
        ".rs": ("rust", ["rustc", "--parse-only"]),
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute syntax check.

        Args:
            file_path: Path to source file

        Returns:
            ToolResult with syntax check results
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        file_path = kwargs["file_path"]
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            logger.warning("syntax_check_file_not_found", file_path=file_path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {file_path}",
            )

        # Detect language
        ext = path.suffix.lower()
        if ext not in self.LANGUAGE_COMMANDS:
            logger.warning("syntax_check_unsupported_language", extension=ext)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Language with extension '{ext}' is not supported",
            )

        language, cmd = self.LANGUAGE_COMMANDS[ext]

        # Run syntax check
        try:
            result = subprocess.run(
                cmd + [str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            is_valid = result.returncode == 0
            error_message = result.stderr if not is_valid else ""

            output = {
                "valid": is_valid,
                "language": language,
                "file_path": file_path,
            }

            if not is_valid:
                output["error_message"] = error_message

            logger.debug(
                "syntax_check_completed",
                file_path=file_path,
                language=language,
                valid=is_valid,
            )

            return ToolResult(output=output, truncated=False)

        except subprocess.TimeoutExpired:
            logger.error("syntax_check_timeout", file_path=file_path)
            return ToolResult(
                output=None,
                truncated=False,
                error="Syntax check timed out after 30 seconds",
            )
        except FileNotFoundError:
            logger.error("syntax_check_tool_not_found", language=language, cmd=cmd[0])
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Syntax checker '{cmd[0]}' not found. Please install {language} toolchain.",
            )
        except Exception as e:
            logger.error("syntax_check_error", file_path=file_path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Syntax check failed: {str(e)}",
            )


class ParseASTTool(Tool):
    """Parse source code into Abstract Syntax Tree using tree-sitter.

    Extracts function definitions, class definitions, and AST structure.
    """

    name = "parse_ast"
    description = "Parse source code into AST using tree-sitter"
    parameters_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the source file to parse",
            },
        },
        "required": ["file_path"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute AST parsing.

        Args:
            file_path: Path to source file

        Returns:
            ToolResult with AST structure
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        file_path = kwargs["file_path"]
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            logger.warning("parse_ast_file_not_found", file_path=file_path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {file_path}",
            )

        try:
            # Try to import tree-sitter (optional dependency)
            try:
                import tree_sitter_python
                import tree_sitter_javascript
                from tree_sitter import Language, Parser
            except ImportError:
                # Fallback: use regex-based parsing
                return self._fallback_parse(path)

            # Read file content
            content = path.read_bytes()

            # Detect language and get parser
            ext = path.suffix.lower()
            parser = Parser()

            if ext == ".py":
                language = Language(tree_sitter_python.language())
            elif ext == ".js":
                language = Language(tree_sitter_javascript.language())
            else:
                return self._fallback_parse(path)

            parser.language = language
            tree = parser.parse(content)

            # Extract function and class definitions
            functions = self._extract_functions(tree.root_node, content)
            classes = self._extract_classes(tree.root_node, content)

            # Create a simple tree representation
            tree_repr = self._node_to_string(tree.root_node, content, max_depth=3)

            output = {
                "tree": tree_repr,
                "function_definitions": functions,
                "class_definitions": classes,
                "has_errors": tree.root_node.has_error,
                "file_path": file_path,
            }

            logger.debug(
                "parse_ast_completed",
                file_path=file_path,
                functions=len(functions),
                classes=len(classes),
            )

            return ToolResult(output=output, truncated=False)

        except Exception as e:
            logger.error("parse_ast_error", file_path=file_path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"AST parsing failed: {str(e)}",
            )

    def _fallback_parse(self, path: Path) -> ToolResult:
        """Fallback parsing using regex when tree-sitter is not available."""
        content = path.read_text(encoding="utf-8", errors="ignore")
        ext = path.suffix.lower()

        functions = []
        classes = []

        if ext == ".py":
            # Extract Python functions
            func_pattern = r"^\s*def\s+(\w+)\s*\("
            functions = re.findall(func_pattern, content, re.MULTILINE)

            # Extract Python classes
            class_pattern = r"^\s*class\s+(\w+)"
            classes = re.findall(class_pattern, content, re.MULTILINE)

        elif ext == ".js":
            # Extract JavaScript functions
            func_pattern = r"function\s+(\w+)\s*\(|const\s+(\w+)\s*=\s*\([^)]*\)\s*=>"
            matches = re.findall(func_pattern, content)
            functions = [m[0] or m[1] for m in matches]

            # Extract JavaScript classes
            class_pattern = r"class\s+(\w+)"
            classes = re.findall(class_pattern, content)

        output = {
            "tree": "fallback_parse",
            "function_definitions": functions,
            "class_definitions": classes,
            "has_errors": False,
            "file_path": str(path),
        }

        return ToolResult(output=output, truncated=False)

    def _extract_functions(self, node: Any, content: bytes) -> List[str]:
        """Extract function definitions from AST."""
        functions = []

        if node.type == "function_definition" or node.type == "function_declaration":
            # Get function name
            for child in node.children:
                if child.type == "identifier":
                    name = content[child.start_byte : child.end_byte].decode("utf-8")
                    functions.append(name)
                    break

        for child in node.children:
            functions.extend(self._extract_functions(child, content))

        return functions

    def _extract_classes(self, node: Any, content: bytes) -> List[str]:
        """Extract class definitions from AST."""
        classes = []

        if node.type == "class_definition" or node.type == "class_declaration":
            # Get class name
            for child in node.children:
                if child.type == "identifier":
                    name = content[child.start_byte : child.end_byte].decode("utf-8")
                    classes.append(name)
                    break

        for child in node.children:
            classes.extend(self._extract_classes(child, content))

        return classes

    def _node_to_string(self, node: Any, content: bytes, max_depth: int = 3, depth: int = 0) -> str:
        """Convert AST node to string representation."""
        if depth > max_depth:
            return "..."

        indent = "  " * depth
        node_str = f"{indent}{node.type}"

        # For leaf nodes, include the text
        if len(node.children) == 0:
            text = content[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")
            if len(text) < 50:
                node_str += f": {repr(text)}"

        if depth < max_depth and node.children:
            for child in node.children[:10]:  # Limit children to avoid huge output
                node_str += "\n" + self._node_to_string(child, content, max_depth, depth + 1)

        return node_str


class GetImportsTool(Tool):
    """Extract import statements from source code.

    Supports Python, JavaScript, and Java import/require statements.
    """

    name = "get_imports"
    description = "Extract import statements and dependencies from source code"
    parameters_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the source file",
            },
        },
        "required": ["file_path"],
    }

    # Regex patterns for different languages
    IMPORT_PATTERNS = {
        ".py": [
            r"^\s*import\s+([\w\.]+)",
            r"^\s*from\s+([\w\.]+)\s+import",
        ],
        ".js": [
            r"import\s+.*\s+from\s+['\"]([^'\"]+)['\"]",
            r"import\s+['\"]([^'\"]+)['\"]",
            r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        ],
        ".java": [
            r"^\s*import\s+([\w\.]+);",
            r"^\s*import\s+static\s+([\w\.]+);",
        ],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute import extraction.

        Args:
            file_path: Path to source file

        Returns:
            ToolResult with list of imports
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        file_path = kwargs["file_path"]
        path = Path(file_path)

        # Check file exists
        if not path.exists():
            logger.warning("get_imports_file_not_found", file_path=file_path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {file_path}",
            )

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            ext = path.suffix.lower()

            imports = []

            if ext in self.IMPORT_PATTERNS:
                patterns = self.IMPORT_PATTERNS[ext]
                for pattern in patterns:
                    matches = re.findall(pattern, content, re.MULTILINE)
                    imports.extend(matches)

            # Remove duplicates while preserving order
            seen = set()
            unique_imports = []
            for imp in imports:
                if imp not in seen:
                    seen.add(imp)
                    unique_imports.append(imp)

            output = {
                "imports": unique_imports,
                "file_path": file_path,
                "language": self._detect_language(ext),
            }

            logger.debug(
                "get_imports_completed",
                file_path=file_path,
                count=len(unique_imports),
            )

            return ToolResult(output=output, truncated=False)

        except Exception as e:
            logger.error("get_imports_error", file_path=file_path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Import extraction failed: {str(e)}",
            )

    def _detect_language(self, ext: str) -> str:
        """Detect language from file extension."""
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".java": "java",
        }
        return lang_map.get(ext, "unknown")


class DetectProjectTypeTool(Tool):
    """Detect project type based on characteristic files.

    Identifies Python, Node.js, Java, Rust, and other project types.
    """

    name = "detect_project_type"
    description = "Detect project type based on configuration files"
    parameters_schema = {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Path to the project directory",
            },
        },
        "required": ["directory"],
    }

    # Project type indicators
    PROJECT_INDICATORS = {
        "python": [
            "requirements.txt",
            "setup.py",
            "pyproject.toml",
            "Pipfile",
            "setup.cfg",
            "poetry.lock",
        ],
        "nodejs": [
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "node_modules",
        ],
        "java": [
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "gradlew",
        ],
        "rust": [
            "Cargo.toml",
            "Cargo.lock",
        ],
        "go": [
            "go.mod",
            "go.sum",
        ],
        "ruby": [
            "Gemfile",
            "Gemfile.lock",
        ],
        "php": [
            "composer.json",
            "composer.lock",
        ],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute project type detection.

        Args:
            directory: Path to project directory

        Returns:
            ToolResult with detected project types
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        directory = kwargs["directory"]
        path = Path(directory)

        # Check directory exists
        if not path.exists():
            logger.warning("detect_project_type_dir_not_found", directory=directory)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Directory not found: {directory}",
            )

        if not path.is_dir():
            logger.warning("detect_project_type_not_a_dir", directory=directory)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Path is not a directory: {directory}",
            )

        try:
            detected_types = []
            indicators_found = {}

            # Check for each project type
            for project_type, indicators in self.PROJECT_INDICATORS.items():
                found = []
                for indicator in indicators:
                    indicator_path = path / indicator
                    if indicator_path.exists():
                        found.append(indicator)

                if found:
                    detected_types.append(project_type)
                    indicators_found[project_type] = found

            output = {
                "project_types": detected_types,
                "indicators": indicators_found,
                "directory": directory,
            }

            logger.debug(
                "detect_project_type_completed",
                directory=directory,
                types=detected_types,
            )

            return ToolResult(output=output, truncated=False)

        except Exception as e:
            logger.error("detect_project_type_error", directory=directory, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Project type detection failed: {str(e)}",
            )
