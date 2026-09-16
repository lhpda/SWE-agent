"""LocalizationAgent for bug localization.

Implements Task 3.3: Main agent that orchestrates the localization process:
- Parse issue to extract error information
- Execute multiple search strategies
- Aggregate and rank results
- Return LocalizationResult with candidate files
"""

import time
from typing import Any, Dict, List

from swe_agent.agents.localization.parser import IssueParser
from swe_agent.agents.localization.strategy import (
    ErrorMessageStrategy,
    SearchCandidate,
    SearchResultRanker,
    StackTraceStrategy,
    SymbolSearchStrategy,
)
from swe_agent.logging import get_logger
from swe_agent.types import IssueContext, LocalizationResult, RepositoryContext

logger = get_logger(__name__)


class LocalizationAgent:
    """Agent responsible for locating bug-related code in repository.

    Orchestrates the localization process by:
    1. Parsing issue to extract structured information
    2. Executing multiple search strategies (stack trace, error message, symbol)
    3. Aggregating and ranking results
    4. Returning candidates with confidence scores
    """

    def __init__(
        self,
        issue_context: IssueContext,
        repo_context: RepositoryContext,
        stack_trace_strategy=None,
        error_message_strategy=None,
        symbol_search_strategy=None,
    ):
        """Initialize the localization agent.

        Args:
            issue_context: Context information about the issue
            repo_context: Context information about the repository
            stack_trace_strategy: Optional strategy instance (for testing)
            error_message_strategy: Optional strategy instance (for testing)
            symbol_search_strategy: Optional strategy instance (for testing)

        Raises:
            TypeError: If contexts are None
            AttributeError: If contexts are invalid
        """
        if issue_context is None:
            raise TypeError("issue_context cannot be None")
        if repo_context is None:
            raise TypeError("repo_context cannot be None")

        self.issue_context = issue_context
        self.repo_context = repo_context
        self.tool_call_count = 0
        self.start_time = None

        # Initialize parser
        self.parser = IssueParser()

        # Initialize search strategies (allow injection for testing)
        self.stack_trace_strategy = stack_trace_strategy or StackTraceStrategy()
        self.error_message_strategy = error_message_strategy or ErrorMessageStrategy()
        self.symbol_search_strategy = symbol_search_strategy or SymbolSearchStrategy()

        # Initialize ranker
        self.ranker = SearchResultRanker()

        logger.info(
            "localization_agent_initialized",
            issue_id=issue_context.issue_id,
            repo_path=repo_context.path,
        )

    def run(self) -> LocalizationResult:
        """Execute the localization process.

        Returns:
            LocalizationResult with candidate files and metadata

        The process:
        1. Parse issue to extract error information
        2. Execute all search strategies in parallel
        3. Aggregate and rank results
        4. Determine status based on confidence
        5. Return structured result
        """
        self.start_time = time.time()
        logger.info("localization_started", issue_id=self.issue_context.issue_id)

        try:
            # Step 1: Parse issue
            parsed_issue = self._parse_issue()
            logger.debug("issue_parsed", quality=parsed_issue.get("quality"))

            # Step 2: Execute search strategies
            candidates = self._search_with_strategies(parsed_issue)
            logger.info("search_completed", candidate_count=len(candidates))

            # Step 3: Aggregate and rank results
            ranked_candidates = self._aggregate_results(candidates, parsed_issue)
            logger.info("ranking_completed", final_count=len(ranked_candidates))

            # Step 4: Determine status
            status = self._determine_status(ranked_candidates)

            # Step 5: Convert candidates to dict format
            candidate_dicts = [c.to_dict() for c in ranked_candidates]

            # Calculate execution time
            execution_time = time.time() - self.start_time

            # Build search strategy description
            search_strategy = self._build_strategy_description(parsed_issue)

            result = LocalizationResult(
                status=status,
                candidates=candidate_dicts,
                search_strategy=search_strategy,
                execution_time=execution_time,
                tool_calls=self.tool_call_count,
            )

            logger.info(
                "localization_completed",
                status=status,
                candidates=len(candidate_dicts),
                execution_time=execution_time,
            )

            return result

        except Exception as e:
            execution_time = time.time() - self.start_time
            logger.error("localization_failed", error=str(e))

            # Return failed result
            return LocalizationResult(
                status="failed",
                candidates=[],
                search_strategy="error",
                execution_time=execution_time,
                tool_calls=self.tool_call_count,
            )

    def _parse_issue(self) -> Dict[str, Any]:
        """Parse issue context to extract structured information.

        Returns:
            Dictionary with parsed issue data
        """
        self.tool_call_count += 1

        # Use already parsed data if available
        if self.issue_context.parsed:
            return self.issue_context.parsed

        # Otherwise parse the issue body
        parsed_context = self.parser.parse(self.issue_context.body)
        return parsed_context.parsed

    def _search_with_strategies(self, parsed_issue: Dict[str, Any]) -> List[SearchCandidate]:
        """Execute all search strategies to find candidate files.

        Args:
            parsed_issue: Parsed issue data

        Returns:
            List of SearchCandidate objects from all strategies
        """
        all_candidates = []

        try:
            # Strategy 1: Stack Trace Search (highest priority)
            logger.debug("executing_stack_trace_strategy")
            self.tool_call_count += 1
            stack_candidates = self.stack_trace_strategy.search(
                parsed_issue, self.repo_context.path
            )
            all_candidates.extend(stack_candidates)
            logger.debug("stack_trace_completed", count=len(stack_candidates))

        except Exception as e:
            logger.warning("stack_trace_strategy_failed", error=str(e))

        try:
            # Strategy 2: Error Message Search
            logger.debug("executing_error_message_strategy")
            self.tool_call_count += 1
            error_candidates = self.error_message_strategy.search(
                parsed_issue, self.repo_context.path
            )
            all_candidates.extend(error_candidates)
            logger.debug("error_message_completed", count=len(error_candidates))

        except Exception as e:
            logger.warning("error_message_strategy_failed", error=str(e))

        try:
            # Strategy 3: Symbol Search
            logger.debug("executing_symbol_search_strategy")
            self.tool_call_count += 1
            symbol_candidates = self.symbol_search_strategy.search(
                parsed_issue, self.repo_context.path
            )
            all_candidates.extend(symbol_candidates)
            logger.debug("symbol_search_completed", count=len(symbol_candidates))

        except Exception as e:
            logger.warning("symbol_search_strategy_failed", error=str(e))

        return all_candidates

    def _aggregate_results(
        self, candidates: List[SearchCandidate], parsed_issue: Dict[str, Any]
    ) -> List[SearchCandidate]:
        """Aggregate and rank search results.

        Args:
            candidates: List of candidates from all strategies
            parsed_issue: Parsed issue data for context

        Returns:
            Ranked and deduplicated list of candidates
        """
        if not candidates:
            logger.warning("no_candidates_found")
            return []

        self.tool_call_count += 1

        # Use ranker to rank and deduplicate
        ranked = self.ranker.rank(candidates, parsed_issue)

        return ranked

    def _determine_status(self, candidates: List[SearchCandidate]) -> str:
        """Determine localization status based on candidates.

        Args:
            candidates: Ranked list of candidates

        Returns:
            Status string: "success", "partial", or "failed"
        """
        if not candidates:
            return "failed"

        # Check confidence of top candidate
        top_confidence = candidates[0].confidence

        if top_confidence >= 0.7:
            return "success"
        elif top_confidence >= 0.4:
            return "partial"
        else:
            return "partial"

    def _build_strategy_description(self, parsed_issue: Dict[str, Any]) -> str:
        """Build description of search strategies used.

        Args:
            parsed_issue: Parsed issue data

        Returns:
            Human-readable description of strategies
        """
        strategies_used = []

        if parsed_issue.get("stack_traces"):
            strategies_used.append("stack_trace")

        if parsed_issue.get("error_messages"):
            strategies_used.append("error_message")
            strategies_used.append("symbol_search")

        if not strategies_used:
            strategies_used.append("general_search")

        return ", ".join(strategies_used)
