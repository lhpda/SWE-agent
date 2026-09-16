"""Code Search Strategy for bug localization.

Implements Task 3.2: Multiple search strategies for locating bug-related code:
- StackTraceStrategy: Direct file location from stack traces
- ErrorMessageStrategy: Keyword-based search from error messages
- SymbolSearchStrategy: Symbol-based precise location
- SearchResultRanker: Confidence scoring and ranking
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from swe_agent.logging import get_logger
from swe_agent.tools.search import RipgrepSearchTool, SymbolSearchTool

logger = get_logger(__name__)


@dataclass
class SearchCandidate:
    """Represents a candidate file location for bug fix.

    Attributes:
        file_path: Relative path to the file
        confidence: Confidence score (0.0-1.0)
        reason: Explanation for why this file was selected
        relevant_symbols: List of relevant function/class names
        code_snippet: Relevant code snippet from the file
        line_number: Specific line number if available
    """
    file_path: str
    confidence: float
    reason: str
    relevant_symbols: List[str] = field(default_factory=list)
    code_snippet: str = ""
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert candidate to dictionary format.

        Returns:
            Dictionary representation of the candidate
        """
        return {
            "file_path": self.file_path,
            "confidence": self.confidence,
            "reason": self.reason,
            "relevant_symbols": self.relevant_symbols,
            "code_snippet": self.code_snippet,
            "line_number": self.line_number,
        }


class StackTraceStrategy:
    """Search strategy based on stack traces.

    Extracts file paths and line numbers directly from stack traces.
    This is the most reliable strategy when stack traces are available.
    """

    def search(self, parsed_issue: Dict[str, Any], repo_path: str) -> List[SearchCandidate]:
        """Search for candidate files using stack trace information.

        Args:
            parsed_issue: Parsed issue data containing stack_traces
            repo_path: Path to the repository

        Returns:
            List of SearchCandidate objects, ordered by stack depth
        """
        candidates = []
        stack_traces = parsed_issue.get("stack_traces", [])

        if not stack_traces:
            logger.info("stack_trace_strategy_no_traces")
            return []

        for trace_idx, trace in enumerate(stack_traces):
            files = trace.get("files", [])
            language = trace.get("language", "unknown")

            for depth, file_info in enumerate(files):
                file_path = file_info.get("file", "")
                line_number = file_info.get("line")

                if not file_path:
                    continue

                # Confidence decreases with stack depth
                # First frame: 0.9, second: 0.8, etc., minimum 0.5
                base_confidence = 0.9
                depth_penalty = depth * 0.1
                confidence = max(base_confidence - depth_penalty, 0.5)

                # Boost confidence for first stack trace
                if trace_idx == 0:
                    confidence = min(confidence + 0.05, 0.95)

                reason = f"Found in {language} stack trace at depth {depth}"
                if line_number:
                    reason += f", line {line_number}"

                candidate = SearchCandidate(
                    file_path=file_path,
                    confidence=confidence,
                    reason=reason,
                    relevant_symbols=[],
                    code_snippet="",
                    line_number=line_number,
                )

                candidates.append(candidate)
                logger.debug(
                    "stack_trace_candidate",
                    file=file_path,
                    confidence=confidence,
                    depth=depth,
                )

        logger.info(
            "stack_trace_strategy_completed",
            candidates=len(candidates),
        )

        return candidates


class ErrorMessageStrategy:
    """Search strategy based on error messages.

    Extracts keywords (function names, class names, variables) from error
    messages and performs full-text search using ripgrep.
    """

    def __init__(self):
        """Initialize the strategy with search tool."""
        self.search_tool = RipgrepSearchTool()

    def search(self, parsed_issue: Dict[str, Any], repo_path: str) -> List[SearchCandidate]:
        """Search for candidate files using error message keywords.

        Args:
            parsed_issue: Parsed issue data containing error_messages
            repo_path: Path to the repository

        Returns:
            List of SearchCandidate objects, ranked by relevance
        """
        error_messages = parsed_issue.get("error_messages", [])

        if not error_messages:
            logger.info("error_message_strategy_no_errors")
            return []

        # Extract keywords from all error messages
        all_keywords = []
        for error in error_messages:
            keywords = self._extract_keywords(error)
            all_keywords.extend(keywords)

        if not all_keywords:
            logger.info("error_message_strategy_no_keywords")
            return []

        # Remove duplicates while preserving order
        unique_keywords = list(dict.fromkeys(all_keywords))
        logger.debug("extracted_keywords", keywords=unique_keywords)

        # Search for each keyword
        candidates = []
        for keyword in unique_keywords[:5]:  # Limit to top 5 keywords
            keyword_candidates = self._search_keyword(keyword, repo_path)
            candidates.extend(keyword_candidates)

        logger.info(
            "error_message_strategy_completed",
            keywords_searched=len(unique_keywords[:5]),
            candidates=len(candidates),
        )

        return candidates

    def _extract_keywords(self, error_message: str) -> List[str]:
        """Extract searchable keywords from error message.

        Extracts:
        - Function names (snake_case or camelCase)
        - Class names (PascalCase)
        - Attribute names after quotes

        Args:
            error_message: Error message text

        Returns:
            List of extracted keywords
        """
        keywords = []

        # Pattern 1: Quoted identifiers (highest priority - attributes, methods)
        quoted_pattern = r"['\"]([a-zA-Z_][a-zA-Z0-9_]+)['\"]"
        quoted_matches = re.findall(quoted_pattern, error_message)
        keywords.extend(quoted_matches)

        # Pattern 2: Class names (PascalCase)
        class_pattern = r'\b([A-Z][a-zA-Z0-9]+)\b'
        class_matches = re.findall(class_pattern, error_message)
        keywords.extend(class_matches)

        # Pattern 3: Function/method names (snake_case or camelCase with underscores)
        func_pattern = r'\b([a-z_][a-z0-9_]{2,})\b'
        func_matches = re.findall(func_pattern, error_message)
        keywords.extend(func_matches)

        # Filter out common error type names and generic words
        stopwords = {
            'Error', 'Exception', 'Type', 'Value', 'Attribute', 'Index',
            'Key', 'Name', 'Runtime', 'Syntax', 'None', 'True', 'False',
            'object', 'attribute', 'module', 'function', 'method', 'class',
            'list', 'dict', 'int', 'str', 'float', 'bool',
            'the', 'and', 'for', 'not', 'has', 'from', 'import',
            'index', 'out', 'range', 'read', 'property',
            'NoneType', 'AttributeError', 'TypeError', 'ValueError',
            'IndexError', 'KeyError', 'NameError',
        }

        filtered = [k for k in keywords if k not in stopwords and len(k) > 2]

        # Return unique keywords, preserving order (prioritize earlier matches)
        return list(dict.fromkeys(filtered))

    def _search_keyword(self, keyword: str, repo_path: str) -> List[SearchCandidate]:
        """Search for a keyword using ripgrep.

        Args:
            keyword: Keyword to search for
            repo_path: Path to the repository

        Returns:
            List of SearchCandidate objects
        """
        try:
            result = self.search_tool.execute(
                pattern=keyword,
                path=repo_path,
                case_sensitive=True,
            )

            if result.error:
                logger.warning("ripgrep_search_failed", keyword=keyword, error=result.error)
                return []

            if not result.output or result.output == "No matches found":
                return []

            # Parse ripgrep output: "file:line:content"
            candidates = self._parse_ripgrep_output(result.output, keyword)

            return candidates

        except Exception as e:
            logger.error("keyword_search_error", keyword=keyword, error=str(e))
            return []

    def _parse_ripgrep_output(self, output: str, keyword: str) -> List[SearchCandidate]:
        """Parse ripgrep output into candidates.

        Groups matches by file and ranks by occurrence count.

        Args:
            output: Raw ripgrep output
            keyword: The keyword that was searched

        Returns:
            List of SearchCandidate objects
        """
        # Group matches by file
        file_matches: Dict[str, List[tuple]] = {}

        for line in output.strip().split("\n"):
            if not line or line.startswith("["):
                continue

            # Parse "file:line:content"
            parts = line.split(":", 2)
            if len(parts) >= 2:
                file_path = parts[0]
                line_num = parts[1]
                content = parts[2] if len(parts) > 2 else ""

                if file_path not in file_matches:
                    file_matches[file_path] = []

                try:
                    file_matches[file_path].append((int(line_num), content))
                except ValueError:
                    continue

        # Create candidates with confidence based on match count
        candidates = []
        for file_path, matches in file_matches.items():
            match_count = len(matches)

            # Base confidence on number of matches
            # 1 match: 0.5, 2: 0.6, 3+: 0.7, capped at 0.8
            confidence = min(0.4 + (match_count * 0.1), 0.8)

            # Get first match line number and snippet
            first_line, first_content = matches[0]
            snippet = first_content[:100] if first_content else ""

            reason = f"Keyword '{keyword}' found {match_count} time(s)"

            candidate = SearchCandidate(
                file_path=file_path,
                confidence=confidence,
                reason=reason,
                relevant_symbols=[keyword],
                code_snippet=snippet,
                line_number=first_line,
            )

            candidates.append(candidate)

        # Sort by match count (descending)
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        return candidates


class SymbolSearchStrategy:
    """Search strategy based on code symbols.

    Extracts function/class names from error messages and uses symbol search
    (ctags) to locate their definitions precisely.
    """

    def __init__(self):
        """Initialize the strategy with symbol search tool."""
        self.search_tool = SymbolSearchTool()

    def search(self, parsed_issue: Dict[str, Any], repo_path: str) -> List[SearchCandidate]:
        """Search for candidate files using symbol search.

        Args:
            parsed_issue: Parsed issue data containing error_messages
            repo_path: Path to the repository

        Returns:
            List of SearchCandidate objects
        """
        error_messages = parsed_issue.get("error_messages", [])

        if not error_messages:
            logger.info("symbol_search_strategy_no_errors")
            return []

        # Extract symbol names from error messages
        symbols = []
        for error in error_messages:
            extracted = self._extract_symbols(error)
            symbols.extend(extracted)

        if not symbols:
            logger.info("symbol_search_strategy_no_symbols")
            return []

        # Remove duplicates
        unique_symbols = list(dict.fromkeys(symbols))
        logger.debug("extracted_symbols", symbols=unique_symbols)

        # Search for each symbol
        candidates = []
        for symbol in unique_symbols[:5]:  # Limit to top 5 symbols
            symbol_candidates = self._search_symbol(symbol, repo_path)
            candidates.extend(symbol_candidates)

        logger.info(
            "symbol_search_strategy_completed",
            symbols_searched=len(unique_symbols[:5]),
            candidates=len(candidates),
        )

        return candidates

    def _extract_symbols(self, error_message: str) -> List[str]:
        """Extract symbol names (functions, classes) from error message.

        Args:
            error_message: Error message text

        Returns:
            List of symbol names
        """
        symbols = []

        # Pattern 1: Quoted identifiers (highest priority)
        quoted_pattern = r"['\"]([a-zA-Z_][a-zA-Z0-9_]+)['\"]"
        quoted_matches = re.findall(quoted_pattern, error_message)
        symbols.extend(quoted_matches)

        # Pattern 2: Class names (PascalCase)
        class_pattern = r'\b([A-Z][a-zA-Z0-9]+)\b'
        class_matches = re.findall(class_pattern, error_message)
        symbols.extend(class_matches)

        # Pattern 3: Function names (snake_case or lowercase with underscores)
        func_pattern = r'\b([a-z_][a-z0-9_]{2,})\b'
        func_matches = re.findall(func_pattern, error_message)
        symbols.extend(func_matches)

        # Filter common words
        stopwords = {
            'Error', 'Exception', 'Type', 'Value', 'Attribute', 'Index',
            'Key', 'Name', 'Runtime', 'Syntax', 'None', 'True', 'False',
            'NoneType', 'TypeError', 'ValueError', 'AttributeError',
            'IndexError', 'KeyError', 'NameError',
            'object', 'has', 'attribute', 'class', 'throws', 'exception',
            'the', 'and', 'for', 'not', 'from', 'import', 'function',
            'method', 'property', 'module',
        }

        filtered = [s for s in symbols if s not in stopwords and len(s) > 2]

        return list(dict.fromkeys(filtered))

    def _search_symbol(self, symbol_name: str, repo_path: str) -> List[SearchCandidate]:
        """Search for a symbol using ctags.

        Args:
            symbol_name: Symbol name to search for
            repo_path: Path to the repository

        Returns:
            List of SearchCandidate objects
        """
        try:
            result = self.search_tool.execute(
                symbol_name=symbol_name,
                path=repo_path,
                symbol_type="any",
            )

            if result.error:
                logger.warning("symbol_search_failed", symbol=symbol_name, error=result.error)
                return []

            if not result.output or result.output == "No symbols found":
                return []

            # Parse symbol search output
            candidates = self._parse_symbol_output(result.output, symbol_name)

            return candidates

        except Exception as e:
            logger.error("symbol_search_error", symbol=symbol_name, error=str(e))
            return []

    def _parse_symbol_output(self, output: str, symbol_name: str) -> List[SearchCandidate]:
        """Parse symbol search output into candidates.

        Args:
            output: Raw symbol search output
            symbol_name: The symbol that was searched

        Returns:
            List of SearchCandidate objects
        """
        candidates = []

        for line in output.strip().split("\n"):
            if not line or line.startswith("["):
                continue

            # Parse "file:line:kind:symbol"
            parts = line.split(":", 3)
            if len(parts) >= 3:
                file_path = parts[0]
                line_num_str = parts[1]
                kind = parts[2]

                try:
                    line_num = int(line_num_str)
                except ValueError:
                    line_num = None

                # Symbol definitions are highly relevant
                confidence = 0.8
                if kind == "function":
                    confidence = 0.85
                elif kind == "class":
                    confidence = 0.85

                reason = f"Symbol '{symbol_name}' defined as {kind}"

                candidate = SearchCandidate(
                    file_path=file_path,
                    confidence=confidence,
                    reason=reason,
                    relevant_symbols=[symbol_name],
                    code_snippet="",
                    line_number=line_num,
                )

                candidates.append(candidate)

        return candidates


class SearchResultRanker:
    """Ranks and scores search results from multiple strategies.

    Combines results from different strategies and applies additional scoring:
    - Stack trace match bonus
    - Keyword density scoring
    - Test file penalty
    - Deduplication
    """

    def rank(
        self,
        candidates: List[SearchCandidate],
        parsed_issue: Dict[str, Any]
    ) -> List[SearchCandidate]:
        """Rank candidates by applying various scoring factors.

        Args:
            candidates: List of candidates from search strategies
            parsed_issue: Parsed issue data for context

        Returns:
            Ranked list of candidates with adjusted confidence scores
        """
        if not candidates:
            return []

        # Extract context from parsed issue
        stack_files = self._extract_stack_files(parsed_issue)
        error_keywords = self._extract_error_keywords(parsed_issue)

        # Apply scoring adjustments
        scored_candidates = []
        for candidate in candidates:
            adjusted_confidence = candidate.confidence

            # Bonus for stack trace match
            if candidate.file_path in stack_files:
                adjusted_confidence = min(adjusted_confidence + 0.15, 0.95)
                logger.debug("stack_trace_bonus", file=candidate.file_path)

            # Bonus for keyword density
            keyword_boost = self._calculate_keyword_boost(
                candidate, error_keywords
            )
            adjusted_confidence = min(adjusted_confidence + keyword_boost, 0.95)

            # Penalty for test files
            if self._is_test_file(candidate.file_path):
                adjusted_confidence *= 0.7
                logger.debug("test_file_penalty", file=candidate.file_path)

            # Create adjusted candidate
            adjusted_candidate = SearchCandidate(
                file_path=candidate.file_path,
                confidence=adjusted_confidence,
                reason=candidate.reason,
                relevant_symbols=candidate.relevant_symbols,
                code_snippet=candidate.code_snippet,
                line_number=candidate.line_number,
            )

            scored_candidates.append(adjusted_candidate)

        # Deduplicate by file path, keeping highest confidence
        deduplicated = self._deduplicate(scored_candidates)

        # Sort by confidence (descending)
        deduplicated.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(
            "ranking_completed",
            input_candidates=len(candidates),
            output_candidates=len(deduplicated),
        )

        return deduplicated

    def _extract_stack_files(self, parsed_issue: Dict[str, Any]) -> set:
        """Extract file paths from stack traces.

        Args:
            parsed_issue: Parsed issue data

        Returns:
            Set of file paths
        """
        files = set()
        for trace in parsed_issue.get("stack_traces", []):
            for file_info in trace.get("files", []):
                file_path = file_info.get("file")
                if file_path:
                    files.add(file_path)
        return files

    def _extract_error_keywords(self, parsed_issue: Dict[str, Any]) -> List[str]:
        """Extract keywords from error messages.

        Args:
            parsed_issue: Parsed issue data

        Returns:
            List of keywords
        """
        keywords = []
        for error in parsed_issue.get("error_messages", []):
            # Extract identifiers
            pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]{2,})\b'
            matches = re.findall(pattern, error)
            keywords.extend(matches)

        # Filter common words
        stopwords = {
            'Error', 'Exception', 'Type', 'Value', 'Attribute',
            'object', 'attribute', 'None', 'True', 'False',
        }

        filtered = [k for k in keywords if k not in stopwords]
        return list(dict.fromkeys(filtered))

    def _calculate_keyword_boost(
        self,
        candidate: SearchCandidate,
        keywords: List[str]
    ) -> float:
        """Calculate confidence boost based on keyword matches.

        Args:
            candidate: Search candidate
            keywords: List of keywords from error messages

        Returns:
            Confidence boost value (0.0 to 0.15)
        """
        if not keywords:
            return 0.0

        # Count keyword occurrences in code snippet (case-insensitive)
        snippet_lower = candidate.code_snippet.lower()
        total_occurrences = 0

        for keyword in keywords:
            keyword_lower = keyword.lower()
            # Count all occurrences of the keyword in the snippet
            count = snippet_lower.count(keyword_lower)
            total_occurrences += count

        # Boost: 0.03 per occurrence, max 0.15
        boost = min(total_occurrences * 0.03, 0.15)
        return boost

    def _is_test_file(self, file_path: str) -> bool:
        """Check if file is a test file.

        Args:
            file_path: Path to check

        Returns:
            True if test file
        """
        path_lower = file_path.lower()
        test_indicators = ['test_', '_test.', '/tests/', '\\tests\\', 'spec.']
        return any(indicator in path_lower for indicator in test_indicators)

    def _deduplicate(self, candidates: List[SearchCandidate]) -> List[SearchCandidate]:
        """Remove duplicate file paths, keeping highest confidence.

        Args:
            candidates: List of candidates

        Returns:
            Deduplicated list
        """
        seen = {}
        for candidate in candidates:
            file_path = candidate.file_path

            if file_path not in seen or candidate.confidence > seen[file_path].confidence:
                seen[file_path] = candidate

        return list(seen.values())
