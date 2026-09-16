"""Issue Parser for extracting structured information from GitHub Issues.

Implements Task 3.1: Parse Issue Markdown and extract:
- Error messages
- Stack traces (Python, JavaScript, Java)
- Reproduction steps
- Expected vs Actual behavior
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from src.swe_agent.types import IssueContext


class IssueParser:
    """Parser for extracting structured information from Issue Markdown."""

    def __init__(self):
        """Initialize the parser and store the raw markdown."""
        self._raw_markdown: str = ""
        self._parsed_data: Dict[str, Any] = {}

    def parse(self, issue_markdown: str) -> IssueContext:
        """Parse Issue Markdown and extract structured information.

        Args:
            issue_markdown: Raw Markdown text from GitHub Issue

        Returns:
            IssueContext with parsed components

        Raises:
            ValueError: If input is empty or invalid
            TypeError: If input is None
        """
        if issue_markdown is None:
            raise TypeError("Issue markdown cannot be None")

        if not issue_markdown or not issue_markdown.strip():
            raise ValueError("Issue markdown cannot be empty or blank")

        self._raw_markdown = issue_markdown

        # Extract all components
        error_messages = self.extract_error_messages()
        stack_traces = self.extract_stack_traces()
        reproduction_steps = self.extract_reproduction_steps()
        expected_behavior, actual_behavior = self.extract_expected_actual()

        # Assess quality/confidence for vague issues
        quality, confidence = self._assess_quality(
            error_messages, stack_traces, reproduction_steps
        )

        # Build parsed data dictionary
        self._parsed_data = {
            "error_messages": error_messages,
            "stack_traces": stack_traces,
            "reproduction_steps": reproduction_steps,
            "expected_behavior": expected_behavior,
            "actual_behavior": actual_behavior,
            "quality": quality,
            "confidence": confidence,
        }

        # Create IssueContext
        return IssueContext(
            issue_id="parsed",  # Placeholder, caller should set proper ID
            title="Parsed Issue",  # Placeholder
            body=issue_markdown,
            parsed=self._parsed_data,
            metadata={},
        )

    def extract_error_messages(self) -> List[str]:
        """Extract error messages from the Issue.

        Returns:
            List of error message strings
        """
        errors = []
        text = self._raw_markdown

        # Pattern 1: Standard error prefixes (including generic Error: and Exception:)
        error_patterns = [
            r"(?:^|\n)([A-Z]\w*(?:Error|Exception):\s*.+?)(?:\n|$)",
            r"(?:^|\n)(Error:\s*.+?)(?:\n|$)",  # Generic "Error:"
            r"(?:^|\n)(Exception:\s*.+?)(?:\n|$)",  # Generic "Exception:"
            r"`([A-Z]\w*(?:Error|Exception):\s*[^`]+)`",  # Inline code
            r"`(Error:\s*[^`]+)`",  # Generic Error in backticks
            r"`(Exception:\s*[^`]+)`",  # Generic Exception in backticks
        ]

        for pattern in error_patterns:
            matches = re.finditer(pattern, text, re.MULTILINE)
            for match in matches:
                error_msg = match.group(1).strip()
                if error_msg and error_msg not in errors:
                    errors.append(error_msg)

        # Pattern 2: Error messages in code blocks
        code_blocks = re.findall(r"```[\w]*\n(.*?)```", text, re.DOTALL)
        for block in code_blocks:
            # Look for error patterns in code blocks - more comprehensive
            block_error_patterns = [
                r"([A-Z]\w*(?:Error|Exception):\s*.+?)(?:\n|$)",
                r"^(Error:\s*.+?)(?:\n|$)",
                r"^(Exception:\s*.+?)(?:\n|$)",
            ]
            for pattern in block_error_patterns:
                block_errors = re.findall(pattern, block, re.MULTILINE)
                for err in block_errors:
                    err = err.strip()
                    if err and err not in errors:
                        errors.append(err)

        return errors

    def extract_stack_traces(self) -> List[Dict[str, Any]]:
        """Extract stack traces from the Issue.

        Returns:
            List of dictionaries containing stack trace info with 'language' and content
        """
        traces = []

        # Extract code blocks
        code_blocks = re.findall(
            r"```([\w]*)\n(.*?)```", self._raw_markdown, re.DOTALL
        )

        for lang_hint, block in code_blocks:
            trace_info = self._parse_stack_trace_block(block, lang_hint)
            if trace_info:
                traces.append(trace_info)

        # Also check for stack traces not in code blocks
        if not traces:
            trace_info = self._parse_stack_trace_block(self._raw_markdown, "")
            if trace_info:
                traces.append(trace_info)

        return traces

    def _parse_stack_trace_block(
        self, text: str, lang_hint: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a block of text to detect stack traces.

        Args:
            text: Text block to analyze
            lang_hint: Language hint from code block (if any)

        Returns:
            Dictionary with language and trace details, or None
        """
        # Python stack trace pattern
        python_pattern = r"Traceback \(most recent call last\):|File \"[^\"]+\", line \d+"
        if re.search(python_pattern, text):
            # Extract file references
            files = re.findall(r'File "([^"]+)", line (\d+)', text)
            return {
                "language": "python",
                "files": [{"file": f[0], "line": int(f[1])} for f in files],
                "raw": text.strip()[:500],  # Limit length
            }

        # JavaScript stack trace pattern
        js_pattern = r"at\s+\S+\s+\([^)]+:\d+:\d+\)"
        if re.search(js_pattern, text) or "Error:" in text and ".js:" in text:
            files = re.findall(r"at\s+\S+\s+\(([^:]+):(\d+):(\d+)\)", text)
            return {
                "language": "javascript",
                "files": [{"file": f[0], "line": int(f[1]), "col": int(f[2])} for f in files],
                "raw": text.strip()[:500],
            }

        # Java stack trace pattern
        java_pattern = r"at\s+[\w.$]+\([^)]+\.java:\d+\)"
        if re.search(java_pattern, text):
            files = re.findall(r"at\s+[\w.$]+\(([^)]+\.java):(\d+)\)", text)
            return {
                "language": "java",
                "files": [{"file": f[0], "line": int(f[1])} for f in files],
                "raw": text.strip()[:500],
            }

        return None

    def extract_reproduction_steps(self) -> List[str]:
        """Extract reproduction steps from the Issue.

        Returns:
            List of reproduction step strings
        """
        steps = []
        text = self._raw_markdown

        # Pattern 1: Look for "Steps to Reproduce" sections
        repro_section_patterns = [
            r"##?\s*Steps to Reproduce[:\s]*\n(.*?)(?=\n##|\Z)",
            r"##?\s*To Reproduce[:\s]*\n(.*?)(?=\n##|\Z)",
            r"##?\s*Reproduction[:\s]*\n(.*?)(?=\n##|\Z)",
            r"How to reproduce[:\s]*\n(.*?)(?=\n##|\Z)",
        ]

        section_text = None
        for pattern in repro_section_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                section_text = match.group(1)
                break

        if section_text:
            # Extract numbered/bulleted lists
            list_items = re.findall(
                r"(?:^|\n)\s*(?:\d+\.|-|\*)\s+(.+?)(?=\n\s*(?:\d+\.|-|\*|\n|$))",
                section_text,
                re.DOTALL
            )
            steps.extend([item.strip() for item in list_items if item.strip()])

            # Extract code blocks in reproduction section
            code_blocks = re.findall(r"```[\w]*\n(.*?)```", section_text, re.DOTALL)
            for block in code_blocks:
                if block.strip():
                    steps.append(f"Code: {block.strip()[:200]}")

        # Pattern 2: Look for numbered lists anywhere in the issue
        if not steps:
            numbered_lists = re.findall(
                r"(?:^|\n)\s*\d+\.\s+(.+?)(?=\n\s*\d+\.|\n\n|\Z)",
                text,
                re.DOTALL
            )
            steps.extend([item.strip() for item in numbered_lists[:10] if item.strip()])

        # Pattern 3: Look for code blocks that might be reproduction examples
        if not steps:
            code_blocks = re.findall(
                r"```(python|javascript|js|java|bash|sh)\n(.*?)```",
                text,
                re.DOTALL
            )
            if code_blocks:
                for lang, block in code_blocks[:3]:  # Limit to first 3
                    if len(block.strip()) < 500:  # Only short code blocks
                        steps.append(f"Run {lang} code: {block.strip()[:150]}")

        return steps

    def extract_expected_actual(self) -> Tuple[Optional[str], Optional[str]]:
        """Extract expected and actual behavior from the Issue.

        Returns:
            Tuple of (expected_behavior, actual_behavior), either may be None
        """
        text = self._raw_markdown
        expected = None
        actual = None

        # Pattern 1: Explicit "Expected" and "Actual" sections (including simple colon format)
        expected_patterns = [
            r"##?\s*Expected [Bb]ehavior[:\s]*\n(.*?)(?=\n##|\Z)",
            r"##?\s*Expected[:\s]*\n(.*?)(?=\n##|\Z)",
            r"\*\*Expected behavior:\*\*\s*(.*?)(?=\n\*\*|\n##|\Z)",
            r"(?:^|\n)Expected:\s*(.+?)(?=\n(?:Actual:|##|\Z))",  # Simple "Expected: text"
        ]

        actual_patterns = [
            r"##?\s*Actual [Bb]ehavior[:\s]*\n(.*?)(?=\n##|\Z)",
            r"##?\s*Actual[:\s]*\n(.*?)(?=\n##|\Z)",
            r"\*\*Actual behavior:\*\*\s*(.*?)(?=\n\*\*|\n##|\Z)",
            r"(?:^|\n)Actual:\s*(.+?)(?=\n(?:Expected:|##|\Z))",  # Simple "Actual: text"
        ]

        for pattern in expected_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                expected = match.group(1).strip()[:500]
                break

        for pattern in actual_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                actual = match.group(1).strip()[:500]
                break

        # Pattern 2: "should be X but got Y" pattern
        if not expected or not actual:
            should_but_pattern = r"should be\s+([^,]+),?\s+but\s+(?:got|received|returns?)\s+([^.\n]+)"
            match = re.search(should_but_pattern, text, re.IGNORECASE)
            if match:
                expected = match.group(1).strip()
                actual = match.group(2).strip()

        # Pattern 3: Table format (Expected | Actual)
        if not expected or not actual:
            table_match = re.search(
                r"\|\s*Expected\s*\|\s*Actual\s*\|.*?\n.*?\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|",
                text,
                re.IGNORECASE | re.DOTALL
            )
            if table_match:
                expected = table_match.group(1).strip()
                actual = table_match.group(2).strip()

        return expected, actual

    def _assess_quality(
        self,
        error_messages: List[str],
        stack_traces: List[Dict],
        reproduction_steps: List[str]
    ) -> Tuple[str, float]:
        """Assess the quality and confidence of the parsed Issue.

        Args:
            error_messages: Extracted error messages
            stack_traces: Extracted stack traces
            reproduction_steps: Extracted reproduction steps

        Returns:
            Tuple of (quality_label, confidence_score)
        """
        # Calculate confidence based on presence of technical details
        confidence = 0.0

        if stack_traces:
            confidence += 0.4
        if error_messages:
            confidence += 0.3
        if reproduction_steps:
            confidence += 0.2

        # Check for descriptive content
        if len(self._raw_markdown) > 100:
            confidence += 0.1

        confidence = min(confidence, 1.0)

        # Determine quality label
        if confidence >= 0.7:
            quality = "high"
        elif confidence >= 0.4:
            quality = "medium"
        else:
            quality = "vague"

        return quality, confidence
