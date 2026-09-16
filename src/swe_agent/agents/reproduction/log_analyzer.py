"""Error log analyzer for parsing and analyzing test failure logs.

Task 4.2: Error Log Analyzer
Implements parsing of Python, JavaScript, Java stack traces,
error type identification, root cause extraction, and log truncation.
"""

import re
from typing import Dict, List, Optional, Any

from swe_agent.logging import get_logger

logger = get_logger(__name__)


class LogAnalyzer:
    """Analyze error logs and extract structured information.

    Supports parsing stack traces from Python, JavaScript/Node.js, and Java.
    Extracts error types, root cause locations, and handles log truncation.
    """

    # Patterns for different language stack traces
    PYTHON_TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE)
    PYTHON_FILE_LINE = re.compile(r'^\s*File "([^"]+)", line (\d+)', re.MULTILINE)
    PYTHON_ERROR_LINE = re.compile(r"^(\w+(?:Error|Exception|Warning)): (.+)$", re.MULTILINE)

    JS_ERROR_START = re.compile(r"^(\w*Error): (.+)$", re.MULTILINE)
    JS_STACK_LINE = re.compile(r"^\s+at .+\((.+):(\d+):(\d+)\)", re.MULTILINE)
    JS_STACK_LINE_ALT = re.compile(r"^\s+at (.+):(\d+):(\d+)$", re.MULTILINE)

    JAVA_EXCEPTION_START = re.compile(
        r"^(?:Exception in thread \"[^\"]+\" )?(\w+(?:\.\w+)*(?:Exception|Error)): (.+)$",
        re.MULTILINE
    )
    JAVA_STACK_LINE = re.compile(r"^\s+at (.+)\(([^:]+):(\d+)\)", re.MULTILINE)

    # Library/framework path patterns to filter out
    LIBRARY_PATTERNS = [
        re.compile(r"/usr/lib/"),
        re.compile(r"/usr/local/"),
        re.compile(r"site-packages/"),
        re.compile(r"node_modules/"),
        re.compile(r"node:internal/"),
        re.compile(r"java\.base/"),
        re.compile(r"org\.junit\."),
        re.compile(r"<frozen "),
    ]

    def __init__(self, log_content: str = ""):
        """Initialize log analyzer with optional log content.

        Args:
            log_content: Raw log content to analyze
        """
        self.log_content = log_content
        self.parsed_data: Dict[str, Any] = {}

    def parse_log(self, log_content: str) -> None:
        """Parse log content and extract structured information.

        Args:
            log_content: Raw log content to parse
        """
        self.log_content = log_content
        self.parsed_data = {
            "stack_traces": [],
            "error_type": None,
            "root_cause": {"file": None, "line": None},
        }

        logger.debug("log_analyzer_parsing", content_length=len(log_content))

    def extract_stack_traces(self) -> List[str]:
        """Extract all stack traces from the log.

        Returns:
            List of stack trace strings
        """
        if not self.log_content:
            return []

        stack_traces = []

        # Extract Python tracebacks
        python_traces = self._extract_python_stack_traces()
        stack_traces.extend(python_traces)

        # Extract JavaScript/Node.js errors
        js_traces = self._extract_javascript_stack_traces()
        stack_traces.extend(js_traces)

        # Extract Java exceptions
        java_traces = self._extract_java_stack_traces()
        stack_traces.extend(java_traces)

        logger.debug("stack_traces_extracted", count=len(stack_traces))
        return stack_traces

    def _extract_python_stack_traces(self) -> List[str]:
        """Extract Python traceback stack traces."""
        traces = []
        lines = self.log_content.split("\n")

        i = 0
        while i < len(lines):
            if "Traceback (most recent call last):" in lines[i]:
                # Found start of traceback
                trace_lines = [lines[i]]
                i += 1

                # Collect all lines until we hit the error line
                while i < len(lines):
                    line = lines[i]
                    trace_lines.append(line)

                    # Check if this is the final error line
                    if line.strip() and not line.startswith(" ") and "Error" in line:
                        break
                    if line.strip() and not line.startswith(" ") and "Exception" in line:
                        break

                    i += 1

                traces.append("\n".join(trace_lines))
            i += 1

        return traces

    def _extract_javascript_stack_traces(self) -> List[str]:
        """Extract JavaScript/Node.js error stack traces."""
        traces = []
        lines = self.log_content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check for error line (Error:, TypeError:, etc.)
            if re.match(r"^(\w*Error): .+$", line):
                trace_lines = [lines[i]]
                i += 1

                # Collect subsequent "at" lines
                while i < len(lines):
                    if lines[i].strip().startswith("at "):
                        trace_lines.append(lines[i])
                        i += 1
                    else:
                        break

                if len(trace_lines) > 1:  # Has at least error + one stack frame
                    traces.append("\n".join(trace_lines))
                else:
                    i -= len(trace_lines) - 1  # Backtrack if not a real stack
            else:
                i += 1

        return traces

    def _extract_java_stack_traces(self) -> List[str]:
        """Extract Java exception stack traces."""
        traces = []
        lines = self.log_content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check for Java exception line
            java_match = re.match(
                r"^(?:Exception in thread \"[^\"]+\" )?(\w+(?:\.\w+)*(?:Exception|Error)): (.+)$",
                line
            )
            if java_match or (line and "Exception" in line and "at " in self.log_content[self.log_content.find(line):]):
                trace_lines = [lines[i]]
                i += 1

                # Collect subsequent "at" lines
                while i < len(lines):
                    if lines[i].strip().startswith("at "):
                        trace_lines.append(lines[i])
                        i += 1
                    else:
                        break

                if len(trace_lines) > 1:
                    traces.append("\n".join(trace_lines))
            else:
                i += 1

        return traces

    def identify_error_type(self) -> str:
        """Identify the error type from the log.

        Returns:
            Error type string (e.g., "ValueError", "TypeError", "Unknown")
        """
        if not self.log_content:
            return "Unknown"

        # Try Python error patterns
        python_match = self.PYTHON_ERROR_LINE.search(self.log_content)
        if python_match:
            return python_match.group(1)

        # Try JavaScript error patterns
        js_match = self.JS_ERROR_START.search(self.log_content)
        if js_match:
            error_type = js_match.group(1)
            if error_type:  # Not empty
                return error_type

        # Try Java exception patterns
        java_match = self.JAVA_EXCEPTION_START.search(self.log_content)
        if java_match:
            full_type = java_match.group(1)
            # Extract just the class name (last part after dot)
            return full_type.split(".")[-1]

        # Check for AssertionError in pytest output
        if "AssertionError" in self.log_content:
            return "AssertionError"

        return "Unknown"

    def extract_root_cause(self) -> Dict[str, Optional[Any]]:
        """Extract root cause location (file and line number).

        Filters out library/framework code to find the first project file.

        Returns:
            Dict with 'file' and 'line' keys
        """
        if not self.log_content:
            return {"file": None, "line": None}

        # Try to extract from Python traceback
        python_result = self._extract_python_root_cause()
        if python_result["file"]:
            return python_result

        # Try to extract from JavaScript stack
        js_result = self._extract_javascript_root_cause()
        if js_result["file"]:
            return js_result

        # Try to extract from Java stack
        java_result = self._extract_java_root_cause()
        if java_result["file"]:
            return java_result

        return {"file": None, "line": None}

    def _extract_python_root_cause(self) -> Dict[str, Optional[Any]]:
        """Extract root cause from Python traceback."""
        # Find all File lines in the traceback
        matches = self.PYTHON_FILE_LINE.findall(self.log_content)

        if not matches:
            return {"file": None, "line": None}

        # Filter out library code and find first project file
        for file_path, line_num in matches:
            if not self._is_library_path(file_path):
                return {"file": file_path, "line": int(line_num)}

        # If all are library files, return the first one
        first_file, first_line = matches[0]
        return {"file": first_file, "line": int(first_line)}

    def _extract_javascript_root_cause(self) -> Dict[str, Optional[Any]]:
        """Extract root cause from JavaScript stack trace."""
        # Find all "at" lines with file locations
        matches = self.JS_STACK_LINE.findall(self.log_content)

        if not matches:
            # Try alternative format
            matches = self.JS_STACK_LINE_ALT.findall(self.log_content)
            if matches:
                matches = [(m[0], m[1], m[2]) for m in matches]

        if not matches:
            return {"file": None, "line": None}

        # Filter out library code
        for file_path, line_num, _ in matches:
            if not self._is_library_path(file_path):
                return {"file": file_path, "line": int(line_num)}

        # Return first if all are library files
        first_file, first_line, _ = matches[0]
        return {"file": first_file, "line": int(first_line)}

    def _extract_java_root_cause(self) -> Dict[str, Optional[Any]]:
        """Extract root cause from Java stack trace."""
        # Find all "at" lines with file locations
        matches = self.JAVA_STACK_LINE.findall(self.log_content)

        if not matches:
            return {"file": None, "line": None}

        # Filter out library code
        # Matches are (qualified_name, file_path, line_num)
        for qualified_name, file_path, line_num in matches:
            # Check if the qualified name or file path is from a library
            if not self._is_library_path(qualified_name) and not self._is_library_path(file_path):
                return {"file": file_path, "line": int(line_num)}

        # Return first if all are library files
        _, first_file, first_line = matches[0]
        return {"file": first_file, "line": int(first_line)}

    def _is_library_path(self, path: str) -> bool:
        """Check if a path is from a library/framework.

        Args:
            path: File path to check

        Returns:
            True if path is from a library
        """
        for pattern in self.LIBRARY_PATTERNS:
            if pattern.search(path):
                return True
        return False

    def truncate_log(self, max_lines: int = 200) -> str:
        """Truncate log to keep only the last N lines.

        Args:
            max_lines: Maximum number of lines to keep (default 200)

        Returns:
            Truncated log content with marker if truncated
        """
        if not self.log_content:
            return ""

        lines = self.log_content.split("\n")

        if len(lines) <= max_lines:
            return self.log_content

        # Keep last max_lines
        truncated_lines = lines[-max_lines:]
        num_removed = len(lines) - max_lines

        # Add truncation marker
        marker = f"... [Log truncated: {num_removed} lines removed, showing last {max_lines} lines]"

        result = marker + "\n" + "\n".join(truncated_lines)

        logger.debug("log_truncated", original_lines=len(lines), kept_lines=max_lines)
        return result
