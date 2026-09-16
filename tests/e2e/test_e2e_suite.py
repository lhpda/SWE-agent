"""
Tests for E2E Test Suite Framework.

Task 8.3: Tests for E2E test suite that:
- Loads test cases from fixtures
- Executes them through the pipeline
- Collects metrics (execution time, success rate)
- Generates test reports
- Validates success rate criteria
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import pytest

from swe_agent.types import (
    IssueContext,
    RepositoryContext,
    PipelineResult,
    ErrorInfo,
)


class TestE2EFrameworkInitialization:
    """Tests for E2E test framework initialization."""

    def test_framework_initialization(self):
        """Test E2E framework can be initialized."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        assert framework is not None
        assert hasattr(framework, 'load_test_cases')
        assert hasattr(framework, 'run_test_case')
        assert hasattr(framework, 'collect_metrics')
        assert hasattr(framework, 'generate_report')

    def test_framework_initialization_with_fixtures_path(self, tmp_path):
        """Test framework can be initialized with custom fixtures path."""
        from tests.e2e.e2e_suite import E2ETestFramework

        fixtures_path = tmp_path / "fixtures"
        fixtures_path.mkdir()

        framework = E2ETestFramework(fixtures_path=fixtures_path)

        assert framework.fixtures_path == fixtures_path


class TestTestCaseLoading:
    """Tests for loading test cases from fixtures."""

    def test_load_test_cases_from_fixtures(self):
        """Test loading all test case JSON files from fixtures directory."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()
        test_cases = framework.load_test_cases()

        assert isinstance(test_cases, list)
        assert len(test_cases) > 0

    def test_load_test_cases_validates_json_structure(self, tmp_path):
        """Test that loaded test cases have required fields."""
        from tests.e2e.e2e_suite import E2ETestFramework

        # Create a valid test case
        fixtures_path = tmp_path / "fixtures" / "issues"
        fixtures_path.mkdir(parents=True)

        test_case = {
            "issue_id": "test-001",
            "title": "Test issue",
            "language": "python",
            "complexity": "simple",
            "body": "Test body",
            "repository": {
                "type": "python",
                "test_framework": "pytest",
                "test_command": "pytest"
            },
            "expected_fix": {
                "file": "test.py",
                "description": "Fix test",
                "validation": "Test passes"
            }
        }

        (fixtures_path / "test_001.json").write_text(json.dumps(test_case))

        framework = E2ETestFramework(fixtures_path=tmp_path / "fixtures")
        test_cases = framework.load_test_cases()

        assert len(test_cases) == 1
        assert test_cases[0]["issue_id"] == "test-001"
        assert "title" in test_cases[0]
        assert "body" in test_cases[0]
        assert "repository" in test_cases[0]

    def test_load_test_cases_filters_by_complexity(self):
        """Test loading test cases filtered by complexity."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        simple_cases = framework.load_test_cases(complexity="simple")
        assert all(tc["complexity"] == "simple" for tc in simple_cases)

        medium_cases = framework.load_test_cases(complexity="medium")
        assert all(tc["complexity"] == "medium" for tc in medium_cases)

    def test_load_test_cases_handles_empty_directory(self, tmp_path):
        """Test loading from empty fixtures directory."""
        from tests.e2e.e2e_suite import E2ETestFramework

        fixtures_path = tmp_path / "empty_fixtures" / "issues"
        fixtures_path.mkdir(parents=True)

        framework = E2ETestFramework(fixtures_path=tmp_path / "empty_fixtures")
        test_cases = framework.load_test_cases()

        assert test_cases == []


class TestTestCaseExecution:
    """Tests for executing individual test cases."""

    @patch("tests.e2e.e2e_suite.PipelineOrchestrator")
    def test_run_test_case_success(self, mock_orchestrator_cls, tmp_path):
        """Test running a single test case successfully."""
        from tests.e2e.e2e_suite import E2ETestFramework

        # Mock successful pipeline execution
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = PipelineResult(
            status="success",
            session_id="test-session",
            issue=IssueContext(
                issue_id="test-001",
                title="Test issue",
                body="Test body",
                parsed={},
                metadata={},
            ),
            repository=RepositoryContext(
                path=str(tmp_path),
                git={"branch": "main", "commit": "test"},
                project_type="python",
                test_framework="pytest",
                dependencies={},
            ),
            final_patch={"id": "patch-1", "diff": "test diff"},
            execution_summary={"execution_time": 10.5, "total_cost": {"prompt_tokens": 1000}},
            audit_log="/tmp/test.log",
            error=None,
        )
        mock_orchestrator_cls.return_value = mock_orchestrator

        framework = E2ETestFramework()

        test_case = {
            "issue_id": "test-001",
            "title": "Test issue",
            "body": "Test body",
            "complexity": "simple",
            "repository": {"type": "python"}
        }

        result = framework.run_test_case(test_case, workspace_path=tmp_path)

        assert result["test_id"] == "test-001"
        assert result["status"] == "success"
        assert result["execution_time"] >= 0
        assert "error" not in result or result["error"] is None

    @patch("tests.e2e.e2e_suite.PipelineOrchestrator")
    def test_run_test_case_failure(self, mock_orchestrator_cls, tmp_path):
        """Test running a test case that fails."""
        from tests.e2e.e2e_suite import E2ETestFramework
        from datetime import datetime, timezone

        # Mock failed pipeline execution
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = PipelineResult(
            status="failed",
            session_id="test-session",
            issue=IssueContext(
                issue_id="test-002",
                title="Test issue",
                body="Test body",
                parsed={},
                metadata={},
            ),
            repository=RepositoryContext(
                path=str(tmp_path),
                git={"branch": "main", "commit": "test"},
                project_type="python",
                test_framework="pytest",
                dependencies={},
            ),
            final_patch=None,
            execution_summary={"execution_time": 5.0, "total_cost": {"prompt_tokens": 500}},
            audit_log="/tmp/test.log",
            error=ErrorInfo(
                type="agent_error",
                message="Failed to localize bug",
                details={"stage": "localization"},
                recoverable=False,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
        mock_orchestrator_cls.return_value = mock_orchestrator

        framework = E2ETestFramework()

        test_case = {
            "issue_id": "test-002",
            "title": "Test issue",
            "body": "Test body",
            "complexity": "medium",
            "repository": {"type": "python"}
        }

        result = framework.run_test_case(test_case, workspace_path=tmp_path)

        assert result["test_id"] == "test-002"
        assert result["status"] == "failed"
        assert result["error"] is not None

    def test_run_test_case_captures_execution_time(self, tmp_path):
        """Test that execution time is captured for each test."""
        from tests.e2e.e2e_suite import E2ETestFramework

        with patch("tests.e2e.e2e_suite.PipelineOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()

            # Simulate some execution time
            def slow_run():
                time.sleep(0.1)
                return PipelineResult(
                    status="success",
                    session_id="test-session",
                    issue=IssueContext(
                        issue_id="test-003",
                        title="Test",
                        body="Test",
                        parsed={},
                        metadata={},
                    ),
                    repository=RepositoryContext(
                        path=str(tmp_path),
                        git={"branch": "main", "commit": "test"},
                        project_type="python",
                        test_framework="pytest",
                        dependencies={},
                    ),
                    final_patch={"id": "patch-1"},
                    execution_summary={"execution_time": 0.1},
                    audit_log="/tmp/test.log",
                )

            mock_orch.run.side_effect = slow_run
            mock_orch_cls.return_value = mock_orch

            framework = E2ETestFramework()
            test_case = {
                "issue_id": "test-003",
                "title": "Test",
                "body": "Test",
                "complexity": "simple",
                "repository": {"type": "python"}
            }

            result = framework.run_test_case(test_case, workspace_path=tmp_path)

            assert result["execution_time"] >= 0.1

    @patch("tests.e2e.e2e_suite.PipelineOrchestrator")
    def test_run_test_case_handles_exceptions(self, mock_orchestrator_cls, tmp_path):
        """Test that exceptions during test execution are captured."""
        from tests.e2e.e2e_suite import E2ETestFramework

        # Mock orchestrator that raises exception
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.side_effect = Exception("Unexpected error")
        mock_orchestrator_cls.return_value = mock_orchestrator

        framework = E2ETestFramework()

        test_case = {
            "issue_id": "test-004",
            "title": "Test",
            "body": "Test",
            "complexity": "simple",
            "repository": {"type": "python"}
        }

        result = framework.run_test_case(test_case, workspace_path=tmp_path)

        assert result["status"] == "error"
        assert "Unexpected error" in result["error"]


class TestMetricsCollection:
    """Tests for collecting metrics from test results."""

    def test_collect_metrics_from_results(self):
        """Test collecting metrics from test execution results."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [
            {
                "test_id": "test-001",
                "complexity": "simple",
                "status": "success",
                "execution_time": 5.0,
            },
            {
                "test_id": "test-002",
                "complexity": "simple",
                "status": "success",
                "execution_time": 6.0,
            },
            {
                "test_id": "test-003",
                "complexity": "simple",
                "status": "failed",
                "execution_time": 3.0,
            },
            {
                "test_id": "test-004",
                "complexity": "medium",
                "status": "success",
                "execution_time": 10.0,
            },
            {
                "test_id": "test-005",
                "complexity": "medium",
                "status": "failed",
                "execution_time": 8.0,
            },
        ]

        metrics = framework.collect_metrics(results)

        assert "total_tests" in metrics
        assert metrics["total_tests"] == 5
        assert "success_count" in metrics
        assert metrics["success_count"] == 3
        assert "failure_count" in metrics
        assert metrics["failure_count"] == 2
        assert "overall_success_rate" in metrics
        assert metrics["overall_success_rate"] == 0.6

    def test_collect_metrics_by_complexity(self):
        """Test collecting metrics grouped by complexity."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [
            {"test_id": "s1", "complexity": "simple", "status": "success", "execution_time": 5.0},
            {"test_id": "s2", "complexity": "simple", "status": "success", "execution_time": 6.0},
            {"test_id": "s3", "complexity": "simple", "status": "failed", "execution_time": 3.0},
            {"test_id": "m1", "complexity": "medium", "status": "success", "execution_time": 10.0},
            {"test_id": "m2", "complexity": "medium", "status": "success", "execution_time": 12.0},
            {"test_id": "m3", "complexity": "medium", "status": "failed", "execution_time": 8.0},
            {"test_id": "m4", "complexity": "medium", "status": "failed", "execution_time": 9.0},
        ]

        metrics = framework.collect_metrics(results)

        assert "by_complexity" in metrics
        assert "simple" in metrics["by_complexity"]
        assert "medium" in metrics["by_complexity"]

        simple_metrics = metrics["by_complexity"]["simple"]
        assert simple_metrics["total"] == 3
        assert simple_metrics["success"] == 2
        assert simple_metrics["success_rate"] == pytest.approx(2/3, 0.01)

        medium_metrics = metrics["by_complexity"]["medium"]
        assert medium_metrics["total"] == 4
        assert medium_metrics["success"] == 2
        assert medium_metrics["success_rate"] == 0.5

    def test_collect_metrics_calculates_avg_execution_time(self):
        """Test metrics include average execution time."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [
            {"test_id": "1", "complexity": "simple", "status": "success", "execution_time": 10.0},
            {"test_id": "2", "complexity": "simple", "status": "success", "execution_time": 20.0},
            {"test_id": "3", "complexity": "simple", "status": "success", "execution_time": 30.0},
        ]

        metrics = framework.collect_metrics(results)

        assert "avg_execution_time" in metrics
        assert metrics["avg_execution_time"] == 20.0


class TestReportGeneration:
    """Tests for generating test reports."""

    def test_generate_json_report(self, tmp_path):
        """Test generating JSON report."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [
            {"test_id": "test-001", "complexity": "simple", "status": "success", "execution_time": 5.0},
            {"test_id": "test-002", "complexity": "simple", "status": "failed", "execution_time": 3.0},
        ]

        metrics = framework.collect_metrics(results)

        report_path = tmp_path / "report.json"
        framework.generate_report(results, metrics, output_path=report_path, format="json")

        assert report_path.exists()

        with open(report_path) as f:
            report = json.load(f)

        assert "results" in report
        assert "metrics" in report
        assert len(report["results"]) == 2

    def test_generate_html_report(self, tmp_path):
        """Test generating HTML report."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [
            {"test_id": "test-001", "complexity": "simple", "status": "success", "execution_time": 5.0},
            {"test_id": "test-002", "complexity": "simple", "status": "failed", "execution_time": 3.0, "error": "Test error"},
        ]

        metrics = framework.collect_metrics(results)

        report_path = tmp_path / "report.html"
        framework.generate_report(results, metrics, output_path=report_path, format="html")

        assert report_path.exists()

        html_content = report_path.read_text(encoding='utf-8')
        assert "<!DOCTYPE html>" in html_content or "<html" in html_content
        assert "test-001" in html_content
        assert "test-002" in html_content

    def test_generate_report_includes_timestamp(self, tmp_path):
        """Test that report includes generation timestamp."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [{"test_id": "test-001", "complexity": "simple", "status": "success", "execution_time": 5.0}]
        metrics = framework.collect_metrics(results)

        report_path = tmp_path / "report.json"
        framework.generate_report(results, metrics, output_path=report_path, format="json")

        with open(report_path) as f:
            report = json.load(f)

        assert "timestamp" in report


class TestE2ESuiteIntegration:
    """Integration tests for full E2E suite execution."""

    @patch("tests.e2e.e2e_suite.PipelineOrchestrator")
    def test_run_all_simple_tests(self, mock_orchestrator_cls, tmp_path):
        """Test running all simple test cases."""
        from tests.e2e.e2e_suite import E2ETestFramework

        # Mock successful execution
        mock_orchestrator = MagicMock()
        mock_orchestrator.run.return_value = PipelineResult(
            status="success",
            session_id="test-session",
            issue=IssueContext(
                issue_id="test",
                title="Test",
                body="Test",
                parsed={},
                metadata={},
            ),
            repository=RepositoryContext(
                path=str(tmp_path),
                git={"branch": "main", "commit": "test"},
                project_type="python",
                test_framework="pytest",
                dependencies={},
            ),
            final_patch={"id": "patch-1"},
            execution_summary={"execution_time": 5.0},
            audit_log="/tmp/test.log",
        )
        mock_orchestrator_cls.return_value = mock_orchestrator

        framework = E2ETestFramework()
        simple_tests = framework.load_test_cases(complexity="simple")

        results = []
        for test_case in simple_tests:
            result = framework.run_test_case(test_case, workspace_path=tmp_path)
            results.append(result)

        assert len(results) > 0
        assert all("execution_time" in r for r in results)

    def test_full_suite_execution_workflow(self, tmp_path):
        """Test complete workflow: load -> execute -> collect -> report."""
        from tests.e2e.e2e_suite import E2ETestFramework

        with patch("tests.e2e.e2e_suite.PipelineOrchestrator") as mock_orch_cls:
            mock_orch = MagicMock()
            mock_orch.run.return_value = PipelineResult(
                status="success",
                session_id="test-session",
                issue=IssueContext(
                    issue_id="test",
                    title="Test",
                    body="Test",
                    parsed={},
                    metadata={},
                ),
                repository=RepositoryContext(
                    path=str(tmp_path),
                    git={"branch": "main", "commit": "test"},
                    project_type="python",
                    test_framework="pytest",
                    dependencies={},
                ),
                final_patch={"id": "patch-1"},
                execution_summary={"execution_time": 5.0},
                audit_log="/tmp/test.log",
            )
            mock_orch_cls.return_value = mock_orch

            framework = E2ETestFramework()

            # Load test cases
            test_cases = framework.load_test_cases(complexity="simple")

            # Execute tests
            results = []
            for test_case in test_cases[:2]:  # Run first 2 for speed
                result = framework.run_test_case(test_case, workspace_path=tmp_path)
                results.append(result)

            # Collect metrics
            metrics = framework.collect_metrics(results)

            # Generate report
            report_path = tmp_path / "e2e_report.json"
            framework.generate_report(results, metrics, output_path=report_path, format="json")

            assert report_path.exists()


class TestSuccessCriteria:
    """Tests for validating success criteria."""

    def test_validate_simple_bugs_success_rate(self):
        """Test validation of simple bugs success rate >= 80%."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        # Create results with >=80% success rate (4 out of 5 = 80%)
        results = [
            {"test_id": "s1", "complexity": "simple", "status": "success", "execution_time": 5.0},
            {"test_id": "s2", "complexity": "simple", "status": "success", "execution_time": 5.0},
            {"test_id": "s3", "complexity": "simple", "status": "success", "execution_time": 5.0},
            {"test_id": "s4", "complexity": "simple", "status": "success", "execution_time": 5.0},
            {"test_id": "s5", "complexity": "simple", "status": "failed", "execution_time": 5.0},
        ]

        metrics = framework.collect_metrics(results)
        criteria_met = framework.validate_success_criteria(metrics)

        assert criteria_met["simple_bugs"]["met"] is True

    def test_validate_medium_bugs_success_rate(self):
        """Test validation of medium bugs success rate > 60%."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        # Create results with >60% success rate
        results = [
            {"test_id": "m1", "complexity": "medium", "status": "success", "execution_time": 10.0},
            {"test_id": "m2", "complexity": "medium", "status": "success", "execution_time": 10.0},
            {"test_id": "m3", "complexity": "medium", "status": "success", "execution_time": 10.0},
            {"test_id": "m4", "complexity": "medium", "status": "failed", "execution_time": 10.0},
        ]

        metrics = framework.collect_metrics(results)
        criteria_met = framework.validate_success_criteria(metrics)

        assert criteria_met["medium_bugs"]["met"] is True

    def test_validate_complex_bugs_at_least_one_success(self):
        """Test validation of complex bugs having at least 1 success."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [
            {"test_id": "c1", "complexity": "complex", "status": "success", "execution_time": 20.0},
            {"test_id": "c2", "complexity": "complex", "status": "failed", "execution_time": 15.0},
        ]

        metrics = framework.collect_metrics(results)
        criteria_met = framework.validate_success_criteria(metrics)

        assert criteria_met["complex_bugs"]["met"] is True

    def test_validate_negative_case_fails_correctly(self):
        """Test validation that negative cases fail as expected."""
        from tests.e2e.e2e_suite import E2ETestFramework

        framework = E2ETestFramework()

        results = [
            {"test_id": "neg1", "complexity": "negative", "status": "failed", "execution_time": 5.0},
        ]

        metrics = framework.collect_metrics(results)
        criteria_met = framework.validate_success_criteria(metrics)

        assert criteria_met["negative_cases"]["met"] is True
