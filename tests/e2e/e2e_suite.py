"""
E2E Test Suite Framework for SWE Agent.

Task 8.3: E2E test framework that:
- Loads test cases from fixtures
- Executes them through the full pipeline using PipelineOrchestrator
- Collects success rate and performance metrics
- Generates HTML and JSON test reports
- Validates success criteria
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from swe_agent.logging import get_logger
from swe_agent.types import IssueContext, RepositoryContext, PipelineResult

logger = get_logger(__name__)

# Try to import PipelineOrchestrator, will be None if not yet implemented
try:
    from swe_agent.orchestrator.pipeline import PipelineOrchestrator
except ImportError:
    logger.warning("PipelineOrchestrator not yet implemented, E2E tests will use mock")
    PipelineOrchestrator = None


class E2ETestFramework:
    """Framework for running E2E tests on the SWE Agent pipeline.

    Example:
        >>> framework = E2ETestFramework()
        >>> test_cases = framework.load_test_cases(complexity="simple")
        >>> results = [framework.run_test_case(tc, workspace) for tc in test_cases]
        >>> metrics = framework.collect_metrics(results)
        >>> framework.generate_report(results, metrics, "report.html", "html")
    """

    def __init__(self, fixtures_path: Optional[Path] = None):
        """Initialize E2E test framework.

        Args:
            fixtures_path: Path to fixtures directory. Defaults to tests/fixtures.
        """
        if fixtures_path is None:
            # Default to tests/fixtures relative to this file
            self.fixtures_path = Path(__file__).parent.parent / "fixtures"
        else:
            self.fixtures_path = Path(fixtures_path)

        logger.info("e2e_framework_initialized", fixtures_path=str(self.fixtures_path))

    def load_test_cases(self, complexity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load test cases from fixtures directory.

        Args:
            complexity: Optional filter by complexity (simple, medium, complex, negative)

        Returns:
            List of test case dictionaries
        """
        issues_path = self.fixtures_path / "issues"

        if not issues_path.exists():
            logger.warning("fixtures_directory_not_found", path=str(issues_path))
            return []

        test_cases = []

        for json_file in issues_path.glob("*.json"):
            try:
                with open(json_file) as f:
                    test_case = json.load(f)

                # Filter by complexity if specified
                if complexity is None or test_case.get("complexity") == complexity:
                    test_cases.append(test_case)
                    logger.debug("test_case_loaded", issue_id=test_case.get("issue_id"))

            except (json.JSONDecodeError, KeyError) as e:
                logger.error("failed_to_load_test_case", file=str(json_file), error=str(e))
                continue

        logger.info("test_cases_loaded", total=len(test_cases), complexity=complexity)
        return test_cases

    def run_test_case(
        self,
        test_case: Dict[str, Any],
        workspace_path: Path,
        timeout: int = 600
    ) -> Dict[str, Any]:
        """Execute a single test case through the pipeline.

        Args:
            test_case: Test case dictionary from fixtures
            workspace_path: Path to workspace for test execution
            timeout: Timeout in seconds (default 600 = 10 minutes)

        Returns:
            Result dictionary with status, execution_time, and error (if any)
        """
        test_id = test_case.get("issue_id", "unknown")
        logger.info("running_test_case", test_id=test_id)

        start_time = time.time()

        result = {
            "test_id": test_id,
            "complexity": test_case.get("complexity", "unknown"),
            "title": test_case.get("title", ""),
            "status": "unknown",
            "execution_time": 0.0,
            "error": None,
        }

        try:
            # Check if PipelineOrchestrator is available
            if PipelineOrchestrator is None:
                raise ImportError("PipelineOrchestrator not yet implemented")

            # Create issue context from test case
            issue_context = IssueContext(
                issue_id=test_case["issue_id"],
                title=test_case["title"],
                body=test_case["body"],
                parsed={},  # Will be parsed by agents
                metadata=test_case.get("metadata", {}),
            )

            # Create repository context from test case
            repo_info = test_case.get("repository", {})
            repo_context = RepositoryContext(
                path=str(workspace_path),
                git={"branch": "main", "commit": "test"},
                project_type=repo_info.get("type", "unknown"),
                test_framework=repo_info.get("test_framework"),
                dependencies={},
            )

            # Create state store (mock for now)
            from unittest.mock import MagicMock
            mock_store = MagicMock()
            mock_store.create_session.return_value = workspace_path / "session"

            # Create and run orchestrator
            orchestrator = PipelineOrchestrator(
                issue=issue_context,
                repository=repo_context,
                state_store=mock_store,
                global_timeout=timeout,
            )

            pipeline_result = orchestrator.run()

            # Extract result information
            result["status"] = pipeline_result.status
            result["execution_time"] = time.time() - start_time

            if pipeline_result.error:
                result["error"] = f"{pipeline_result.error.type}: {pipeline_result.error.message}"

            if pipeline_result.final_patch:
                result["patch_id"] = pipeline_result.final_patch.get("id")

            logger.info(
                "test_case_completed",
                test_id=test_id,
                status=result["status"],
                execution_time=result["execution_time"],
            )

        except ImportError as e:
            # PipelineOrchestrator not implemented yet
            result["status"] = "skipped"
            result["error"] = f"PipelineOrchestrator not implemented: {str(e)}"
            result["execution_time"] = time.time() - start_time
            logger.warning("test_case_skipped", test_id=test_id, reason=str(e))

        except Exception as e:
            # Unexpected error during execution
            result["status"] = "error"
            result["error"] = str(e)
            result["execution_time"] = time.time() - start_time
            logger.error(
                "test_case_error",
                test_id=test_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        return result

    def collect_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Collect and aggregate metrics from test results.

        Args:
            results: List of test execution results

        Returns:
            Dictionary of aggregated metrics
        """
        if not results:
            return {
                "total_tests": 0,
                "success_count": 0,
                "failure_count": 0,
                "error_count": 0,
                "overall_success_rate": 0.0,
                "avg_execution_time": 0.0,
                "by_complexity": {},
            }

        total_tests = len(results)
        success_count = sum(1 for r in results if r["status"] == "success")
        failure_count = sum(1 for r in results if r["status"] == "failed")
        error_count = sum(1 for r in results if r["status"] == "error")
        skipped_count = sum(1 for r in results if r["status"] == "skipped")

        overall_success_rate = success_count / total_tests if total_tests > 0 else 0.0

        total_execution_time = sum(r["execution_time"] for r in results)
        avg_execution_time = total_execution_time / total_tests if total_tests > 0 else 0.0

        # Group by complexity
        by_complexity = {}
        for result in results:
            complexity = result.get("complexity", "unknown")

            if complexity not in by_complexity:
                by_complexity[complexity] = {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                    "error": 0,
                    "skipped": 0,
                    "success_rate": 0.0,
                    "avg_execution_time": 0.0,
                    "total_execution_time": 0.0,
                }

            by_complexity[complexity]["total"] += 1
            by_complexity[complexity]["total_execution_time"] += result["execution_time"]

            if result["status"] == "success":
                by_complexity[complexity]["success"] += 1
            elif result["status"] == "failed":
                by_complexity[complexity]["failed"] += 1
            elif result["status"] == "error":
                by_complexity[complexity]["error"] += 1
            elif result["status"] == "skipped":
                by_complexity[complexity]["skipped"] += 1

        # Calculate success rates and averages per complexity
        for complexity, stats in by_complexity.items():
            if stats["total"] > 0:
                stats["success_rate"] = stats["success"] / stats["total"]
                stats["avg_execution_time"] = stats["total_execution_time"] / stats["total"]

        metrics = {
            "total_tests": total_tests,
            "success_count": success_count,
            "failure_count": failure_count,
            "error_count": error_count,
            "skipped_count": skipped_count,
            "overall_success_rate": overall_success_rate,
            "avg_execution_time": avg_execution_time,
            "total_execution_time": total_execution_time,
            "by_complexity": by_complexity,
        }

        logger.info("metrics_collected", metrics=metrics)
        return metrics

    def validate_success_criteria(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that success criteria are met.

        Success criteria:
        - Simple bugs: success rate > 80%
        - Medium bugs: success rate > 60%
        - Complex bugs: at least 1 success
        - Negative cases: correctly fails

        Args:
            metrics: Metrics dictionary from collect_metrics()

        Returns:
            Dictionary of criteria validation results
        """
        by_complexity = metrics.get("by_complexity", {})

        criteria = {
            "simple_bugs": {
                "threshold": 0.8,
                "actual": by_complexity.get("simple", {}).get("success_rate", 0.0),
                "met": False,
            },
            "medium_bugs": {
                "threshold": 0.6,
                "actual": by_complexity.get("medium", {}).get("success_rate", 0.0),
                "met": False,
            },
            "complex_bugs": {
                "threshold": "at least 1 success",
                "actual": by_complexity.get("complex", {}).get("success", 0),
                "met": False,
            },
            "negative_cases": {
                "threshold": "correctly fails",
                "actual": by_complexity.get("negative", {}).get("failed", 0),
                "met": False,
            },
        }

        # Validate simple bugs
        if "simple" in by_complexity:
            criteria["simple_bugs"]["met"] = (
                by_complexity["simple"]["success_rate"] >= 0.8
            )

        # Validate medium bugs
        if "medium" in by_complexity:
            criteria["medium_bugs"]["met"] = (
                by_complexity["medium"]["success_rate"] >= 0.6
            )

        # Validate complex bugs
        if "complex" in by_complexity:
            criteria["complex_bugs"]["met"] = (
                by_complexity["complex"]["success"] >= 1
            )

        # Validate negative cases
        if "negative" in by_complexity:
            criteria["negative_cases"]["met"] = (
                by_complexity["negative"]["failed"] >= 1
            )

        logger.info("success_criteria_validated", criteria=criteria)
        return criteria

    def generate_report(
        self,
        results: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        output_path: Path,
        format: str = "html",
    ) -> None:
        """Generate test report in HTML or JSON format.

        Args:
            results: List of test execution results
            metrics: Aggregated metrics
            output_path: Path to save report
            format: Report format ("html" or "json")
        """
        output_path = Path(output_path)
        timestamp = datetime.now(timezone.utc).isoformat()

        if format == "json":
            self._generate_json_report(results, metrics, output_path, timestamp)
        elif format == "html":
            self._generate_html_report(results, metrics, output_path, timestamp)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info("report_generated", path=str(output_path), format=format)

    def _generate_json_report(
        self,
        results: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        output_path: Path,
        timestamp: str,
    ) -> None:
        """Generate JSON report."""
        report = {
            "timestamp": timestamp,
            "metrics": metrics,
            "results": results,
            "success_criteria": self.validate_success_criteria(metrics),
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    def _generate_html_report(
        self,
        results: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        output_path: Path,
        timestamp: str,
    ) -> None:
        """Generate HTML report."""
        criteria = self.validate_success_criteria(metrics)

        # Build HTML content
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SWE Agent E2E Test Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .summary {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .metric-card {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric-value {{
            font-size: 2em;
            font-weight: bold;
            color: #007bff;
        }}
        .metric-label {{
            color: #666;
            font-size: 0.9em;
        }}
        table {{
            width: 100%;
            background: white;
            border-collapse: collapse;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th {{
            background: #007bff;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .status-success {{
            color: #28a745;
            font-weight: bold;
        }}
        .status-failed {{
            color: #dc3545;
            font-weight: bold;
        }}
        .status-error {{
            color: #ffc107;
            font-weight: bold;
        }}
        .status-skipped {{
            color: #6c757d;
            font-weight: bold;
        }}
        .criteria {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-top: 20px;
        }}
        .criteria-item {{
            padding: 10px;
            margin: 10px 0;
            border-left: 4px solid #ddd;
            background: #f8f9fa;
        }}
        .criteria-met {{
            border-left-color: #28a745;
        }}
        .criteria-not-met {{
            border-left-color: #dc3545;
        }}
        .timestamp {{
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <h1>SWE Agent E2E Test Report</h1>
    <p class="timestamp">Generated: {timestamp}</p>

    <div class="summary">
        <h2>Summary</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value">{metrics['total_tests']}</div>
                <div class="metric-label">Total Tests</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics['success_count']}</div>
                <div class="metric-label">Successes</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics['failure_count']}</div>
                <div class="metric-label">Failures</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics['overall_success_rate']:.1%}</div>
                <div class="metric-label">Success Rate</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics['avg_execution_time']:.1f}s</div>
                <div class="metric-label">Avg Execution Time</div>
            </div>
        </div>
    </div>

    <div class="summary">
        <h2>By Complexity</h2>
        <table>
            <thead>
                <tr>
                    <th>Complexity</th>
                    <th>Total</th>
                    <th>Success</th>
                    <th>Failed</th>
                    <th>Success Rate</th>
                    <th>Avg Time</th>
                </tr>
            </thead>
            <tbody>
"""

        # Add complexity breakdown
        for complexity, stats in metrics.get("by_complexity", {}).items():
            html_content += f"""
                <tr>
                    <td><strong>{complexity.capitalize()}</strong></td>
                    <td>{stats['total']}</td>
                    <td class="status-success">{stats['success']}</td>
                    <td class="status-failed">{stats['failed']}</td>
                    <td>{stats['success_rate']:.1%}</td>
                    <td>{stats['avg_execution_time']:.1f}s</td>
                </tr>
"""

        html_content += """
            </tbody>
        </table>
    </div>

    <div class="criteria">
        <h2>Success Criteria</h2>
"""

        # Add criteria validation
        for name, criterion in criteria.items():
            met_class = "criteria-met" if criterion["met"] else "criteria-not-met"
            status = "✓ Met" if criterion["met"] else "✗ Not Met"

            html_content += f"""
        <div class="criteria-item {met_class}">
            <strong>{name.replace('_', ' ').title()}:</strong>
            Threshold: {criterion['threshold']}, Actual: {criterion['actual']}
            <span style="float: right;">{status}</span>
        </div>
"""

        html_content += """
    </div>

    <div class="summary">
        <h2>Test Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Test ID</th>
                    <th>Title</th>
                    <th>Complexity</th>
                    <th>Status</th>
                    <th>Execution Time</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
"""

        # Add individual test results
        for result in results:
            status_class = f"status-{result['status']}"
            error_text = result.get('error', '')[:100] if result.get('error') else '-'

            html_content += f"""
                <tr>
                    <td>{result['test_id']}</td>
                    <td>{result.get('title', '')[:50]}</td>
                    <td>{result['complexity']}</td>
                    <td class="{status_class}">{result['status'].upper()}</td>
                    <td>{result['execution_time']:.2f}s</td>
                    <td style="font-size: 0.85em; color: #666;">{error_text}</td>
                </tr>
"""

        html_content += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding='utf-8')


def run_e2e_suite(
    workspace_path: Path,
    output_dir: Path,
    complexity_filter: Optional[str] = None,
    generate_html: bool = True,
    generate_json: bool = True,
) -> Dict[str, Any]:
    """Run the complete E2E test suite.

    Args:
        workspace_path: Path to workspace for test execution
        output_dir: Directory to save reports
        complexity_filter: Optional filter for test complexity
        generate_html: Whether to generate HTML report
        generate_json: Whether to generate JSON report

    Returns:
        Metrics dictionary
    """
    logger.info("starting_e2e_suite", workspace=str(workspace_path))

    framework = E2ETestFramework()

    # Load test cases
    test_cases = framework.load_test_cases(complexity=complexity_filter)

    if not test_cases:
        logger.warning("no_test_cases_found")
        return {"total_tests": 0}

    # Execute tests
    results = []
    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"running_test_{i}_of_{len(test_cases)}", test_id=test_case["issue_id"])
        result = framework.run_test_case(test_case, workspace_path)
        results.append(result)

    # Collect metrics
    metrics = framework.collect_metrics(results)

    # Generate reports
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if generate_json:
        json_path = output_dir / "e2e_report.json"
        framework.generate_report(results, metrics, json_path, format="json")
        logger.info("json_report_generated", path=str(json_path))

    if generate_html:
        html_path = output_dir / "e2e_report.html"
        framework.generate_report(results, metrics, html_path, format="html")
        logger.info("html_report_generated", path=str(html_path))

    # Validate success criteria
    criteria = framework.validate_success_criteria(metrics)
    all_met = all(c["met"] for c in criteria.values() if isinstance(c, dict))

    logger.info(
        "e2e_suite_completed",
        total_tests=metrics["total_tests"],
        success_rate=metrics["overall_success_rate"],
        criteria_met=all_met,
    )

    return metrics
