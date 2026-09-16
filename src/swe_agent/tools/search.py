"""Search tools for code analysis.

Based on SYSTEM_DESIGN.md Section 3.6: Tool Layer
Implements Task 1.2: Search Tool Implementation
"""

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from swe_agent.logging import get_logger
from swe_agent.tools.base import Tool, ToolResult

logger = get_logger(__name__)


class RipgrepSearchTool(Tool):
    """Full-text search tool using ripgrep.

    Searches for text patterns in files with support for:
    - Regular expressions
    - File type filtering
    - Case sensitivity control
    - Result truncation at 100 matches
    """

    name = "ripgrep_search"
    description = "Search for text patterns in files using ripgrep"
    parameters_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "Directory or file path to search in",
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File types to include (e.g., ['py', 'js'])",
                "default": [],
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Whether search is case-sensitive",
                "default": True,
            },
        },
        "required": ["pattern", "path"],
    }
    max_results = 100  # From SYSTEM_DESIGN.md Section 5.1

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute ripgrep search.

        Args:
            pattern: Text pattern to search for
            path: Directory or file path to search
            file_types: Optional list of file extensions to filter
            case_sensitive: Whether search is case-sensitive (default True)

        Returns:
            ToolResult with search matches or error
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        pattern = kwargs["pattern"]
        path = kwargs["path"]
        file_types = kwargs.get("file_types", [])
        case_sensitive = kwargs.get("case_sensitive", True)

        # Check if path exists
        if not Path(path).exists():
            logger.warning("search_path_not_found", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Path not found: {path}",
            )

        # Build ripgrep command
        cmd = ["rg", "--line-number", "--no-heading", "--with-filename"]

        if not case_sensitive:
            cmd.append("--ignore-case")

        # Add file type filters
        for file_type in file_types:
            cmd.extend(["--type", file_type])

        # Add max count to limit results (rg will stop after this many matches)
        cmd.extend(["--max-count", str(self.max_results)])

        cmd.extend([pattern, path])

        try:
            logger.debug("executing_ripgrep", command=" ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
            )

            # ripgrep returns exit code 1 when no matches found
            if result.returncode == 1 and result.stdout == "":
                logger.info("ripgrep_no_matches", pattern=pattern, path=path)
                return ToolResult(
                    output="No matches found",
                    truncated=False,
                )

            # Other non-zero exit codes indicate errors
            if result.returncode != 0 and result.returncode != 1:
                error_msg = result.stderr.strip() or f"ripgrep failed with code {result.returncode}"
                logger.warning("ripgrep_error", error=error_msg, code=result.returncode)
                return ToolResult(
                    output=None,
                    truncated=False,
                    error=error_msg,
                )

            output = result.stdout

            # Count actual matches and check if truncated
            lines = output.strip().split("\n") if output.strip() else []
            match_count = len([line for line in lines if line and not line.startswith("[")])

            truncated = match_count >= self.max_results

            if truncated:
                output += f"\n\n[Truncated: showing first {self.max_results} matches]"
                logger.info(
                    "search_results_truncated",
                    pattern=pattern,
                    shown=self.max_results,
                )

            logger.info(
                "ripgrep_search_completed",
                pattern=pattern,
                path=path,
                matches=match_count,
                truncated=truncated,
            )

            return ToolResult(
                output=output,
                truncated=truncated,
                metadata={"match_count": match_count},
            )

        except FileNotFoundError:
            logger.error("ripgrep_not_installed")
            return ToolResult(
                output=None,
                truncated=False,
                error="ripgrep is not installed or not in PATH",
            )
        except subprocess.TimeoutExpired:
            logger.warning("ripgrep_timeout", pattern=pattern, path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error="Search timed out after 30 seconds",
            )
        except Exception as e:
            logger.error("ripgrep_unexpected_error", error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unexpected error: {str(e)}",
            )


class SymbolSearchTool(Tool):
    """Symbol search tool using ctags.

    Searches for code symbols (functions, classes, methods) with support for:
    - Symbol type filtering (function, class, method, etc.)
    - Multiple programming languages
    - Line number reporting
    """

    name = "symbol_search"
    description = "Search for code symbols (functions, classes) using ctags"
    parameters_schema = {
        "type": "object",
        "properties": {
            "symbol_name": {
                "type": "string",
                "description": "Name of symbol to search for",
            },
            "path": {
                "type": "string",
                "description": "Directory or file path to search in",
            },
            "symbol_type": {
                "type": "string",
                "enum": ["function", "class", "method", "variable", "any"],
                "description": "Type of symbol to search for",
                "default": "any",
            },
        },
        "required": ["symbol_name", "path"],
    }
    max_results = 100  # From SYSTEM_DESIGN.md Section 5.1

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute symbol search.

        Args:
            symbol_name: Name of symbol to search for
            path: Directory or file path to search
            symbol_type: Type of symbol (function, class, method, variable, any)

        Returns:
            ToolResult with symbol locations or error
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        symbol_name = kwargs["symbol_name"]
        path = kwargs["path"]
        symbol_type = kwargs.get("symbol_type", "any")

        # Check if path exists
        if not Path(path).exists():
            logger.warning("symbol_search_path_not_found", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Path not found: {path}",
            )

        try:
            # Generate tags file in temp location
            # Use universal-ctags format with additional fields
            cmd = [
                "ctags",
                "--output-format=json",
                "--fields=+n",  # Add line numbers
                "-R",  # Recursive
                path,
            ]

            logger.debug("generating_ctags", command=" ".join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 60 second timeout for large codebases
                cwd=Path(path).parent if Path(path).is_file() else path,
            )

            if result.returncode != 0:
                # ctags might not be installed or path is invalid
                error_msg = result.stderr.strip() or f"ctags failed with code {result.returncode}"
                logger.warning("ctags_error", error=error_msg)
                return ToolResult(
                    output=None,
                    truncated=False,
                    error=error_msg,
                )

            # Parse JSON output
            import json

            matches = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    tag = json.loads(line)

                    # Filter by symbol name (case-sensitive)
                    if tag.get("name") != symbol_name:
                        continue

                    # Filter by symbol type if specified
                    if symbol_type != "any":
                        tag_kind = tag.get("kind", "")
                        if not self._matches_symbol_type(tag_kind, symbol_type):
                            continue

                    # Format output
                    file_path = tag.get("path", "")
                    line_num = tag.get("line", "?")
                    kind = tag.get("kind", "unknown")

                    matches.append(f"{file_path}:{line_num}:{kind}:{symbol_name}")

                    if len(matches) >= self.max_results:
                        break

                except json.JSONDecodeError:
                    continue

            if not matches:
                logger.info("symbol_search_no_matches", symbol=symbol_name, path=path)
                return ToolResult(
                    output="No symbols found",
                    truncated=False,
                )

            output = "\n".join(matches)
            truncated = len(matches) >= self.max_results

            if truncated:
                output += f"\n\n[Truncated: showing first {self.max_results} symbols]"

            logger.info(
                "symbol_search_completed",
                symbol=symbol_name,
                path=path,
                matches=len(matches),
                truncated=truncated,
            )

            return ToolResult(
                output=output,
                truncated=truncated,
                metadata={"match_count": len(matches)},
            )

        except FileNotFoundError:
            logger.error("ctags_not_installed")
            return ToolResult(
                output=None,
                truncated=False,
                error="ctags is not installed or not in PATH",
            )
        except subprocess.TimeoutExpired:
            logger.warning("ctags_timeout", symbol=symbol_name, path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error="Symbol search timed out after 60 seconds",
            )
        except Exception as e:
            logger.error("symbol_search_unexpected_error", error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unexpected error: {str(e)}",
            )

    def _matches_symbol_type(self, tag_kind: str, symbol_type: str) -> bool:
        """Check if ctags kind matches requested symbol type.

        Args:
            tag_kind: Kind from ctags (f, c, m, v, etc.)
            symbol_type: Requested type (function, class, method, variable)

        Returns:
            True if types match
        """
        # Map ctags kinds to symbol types
        kind_mapping = {
            "function": ["f", "function"],
            "class": ["c", "class"],
            "method": ["m", "method", "member"],
            "variable": ["v", "variable"],
        }

        allowed_kinds = kind_mapping.get(symbol_type, [])
        return tag_kind in allowed_kinds


class AstQueryTool(Tool):
    """AST query tool using tree-sitter.

    Queries abstract syntax tree for specific code structures:
    - Function definitions
    - Class definitions
    - Function calls
    - Import statements
    """

    name = "ast_query"
    description = "Query AST for specific code structures using tree-sitter"
    parameters_schema = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": [
                    "function_definition",
                    "class_definition",
                    "function_call",
                    "import_statement",
                ],
                "description": "Type of AST node to query",
            },
            "path": {
                "type": "string",
                "description": "File path to analyze",
            },
            "filter": {
                "type": "string",
                "description": "Optional filter pattern for node names",
                "default": "",
            },
        },
        "required": ["query_type", "path"],
    }
    max_results = 100  # From SYSTEM_DESIGN.md Section 5.1

    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute AST query.

        Args:
            query_type: Type of node to find (function_definition, class_definition, etc.)
            path: File path to analyze
            filter: Optional pattern to filter node names

        Returns:
            ToolResult with matching AST nodes or error
        """
        if not self.validate_parameters(kwargs):
            return ToolResult(
                output=None,
                truncated=False,
                error="Invalid parameters",
            )

        query_type = kwargs["query_type"]
        path = kwargs["path"]
        filter_pattern = kwargs.get("filter", "")

        # Check if file exists
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("ast_query_file_not_found", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"File not found: {path}",
            )

        # Determine language from file extension
        language = self._detect_language(file_path)
        if not language:
            logger.warning("ast_query_unsupported_language", path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unsupported file type: {file_path.suffix}",
            )

        try:
            # Read file content
            content = file_path.read_bytes()

            # Import tree-sitter (lazy import to avoid startup overhead)
            try:
                import tree_sitter_python
                import tree_sitter_javascript
                from tree_sitter import Language, Parser
            except ImportError:
                logger.error("tree_sitter_not_installed")
                return ToolResult(
                    output=None,
                    truncated=False,
                    error="tree-sitter libraries not installed",
                )

            # Get appropriate language parser
            if language == "python":
                ts_language = Language(tree_sitter_python.language())
            elif language == "javascript":
                ts_language = Language(tree_sitter_javascript.language())
            else:
                return ToolResult(
                    output=None,
                    truncated=False,
                    error=f"Language not supported: {language}",
                )

            # Parse the file
            parser = Parser(ts_language)
            tree = parser.parse(content)

            # Query the tree
            matches = self._query_tree(tree.root_node, query_type, filter_pattern, language)

            if not matches:
                logger.info("ast_query_no_matches", query_type=query_type, path=path)
                return ToolResult(
                    output=f"No {query_type} nodes found",
                    truncated=False,
                )

            # Limit results
            truncated = len(matches) > self.max_results
            matches = matches[: self.max_results]

            output = "\n".join(matches)
            if truncated:
                output += f"\n\n[Truncated: showing first {self.max_results} results]"

            logger.info(
                "ast_query_completed",
                query_type=query_type,
                path=path,
                matches=len(matches),
                truncated=truncated,
            )

            return ToolResult(
                output=output,
                truncated=truncated,
                metadata={"match_count": len(matches)},
            )

        except SyntaxError as e:
            logger.warning("ast_query_syntax_error", path=path, error=str(e))
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Syntax error in file: {str(e)}",
            )
        except Exception as e:
            logger.error("ast_query_unexpected_error", error=str(e), path=path)
            return ToolResult(
                output=None,
                truncated=False,
                error=f"Unexpected error: {str(e)}",
            )

    def _detect_language(self, file_path: Path) -> Optional[str]:
        """Detect programming language from file extension.

        Args:
            file_path: Path to file

        Returns:
            Language name or None if unsupported
        """
        ext_mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "javascript",  # TypeScript uses similar syntax
            ".tsx": "javascript",
        }
        return ext_mapping.get(file_path.suffix)

    def _query_tree(
        self, node: Any, query_type: str, filter_pattern: str, language: str
    ) -> List[str]:
        """Recursively query the syntax tree.

        Args:
            node: Current tree-sitter node
            query_type: Type of node to find
            filter_pattern: Optional pattern to filter names
            language: Programming language

        Returns:
            List of matching node descriptions
        """
        matches = []

        # Map query types to node types for each language
        node_type_mapping = {
            "python": {
                "function_definition": "function_definition",
                "class_definition": "class_definition",
                "function_call": "call",
                "import_statement": "import_statement",
            },
            "javascript": {
                "function_definition": ["function_declaration", "arrow_function", "method_definition"],
                "class_definition": "class_declaration",
                "function_call": "call_expression",
                "import_statement": "import_statement",
            },
        }

        target_types = node_type_mapping.get(language, {}).get(query_type)
        if not target_types:
            return matches

        # Ensure target_types is a list
        if isinstance(target_types, str):
            target_types = [target_types]

        # Check if current node matches
        if node.type in target_types:
            node_info = self._extract_node_info(node, query_type, language)
            if node_info:
                # Apply filter if provided
                if not filter_pattern or filter_pattern in node_info:
                    matches.append(node_info)

        # Recursively check children
        for child in node.children:
            matches.extend(self._query_tree(child, query_type, filter_pattern, language))

        return matches

    def _extract_node_info(self, node: Any, query_type: str, language: str) -> Optional[str]:
        """Extract useful information from a node.

        Args:
            node: Tree-sitter node
            query_type: Type of query
            language: Programming language

        Returns:
            Formatted string with node info or None
        """
        try:
            line = node.start_point[0] + 1  # Convert to 1-indexed

            # Extract name based on node type
            name = None
            if query_type in ["function_definition", "class_definition"]:
                # Look for identifier child
                for child in node.children:
                    if child.type == "identifier" or child.type == "property_identifier":
                        name = child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
                        break

            if query_type == "function_call":
                # For function calls, extract the function name
                for child in node.children:
                    if child.type in ["identifier", "attribute", "member_expression"]:
                        name = child.text.decode("utf-8") if isinstance(child.text, bytes) else child.text
                        break

            if query_type == "import_statement":
                # For imports, show the full import text (truncated)
                text = node.text.decode("utf-8") if isinstance(node.text, bytes) else node.text
                name = text[:100]  # Limit import statement length

            if name:
                return f"Line {line}: {query_type} '{name}'"
            else:
                return f"Line {line}: {query_type}"

        except Exception:
            return None
