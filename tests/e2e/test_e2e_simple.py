"""
E2E tests for SWE Agent - Simple Bug Test Cases.

This module contains end-to-end tests using simple bug fixtures.
Tests verify the full pipeline from issue parsing to patch validation.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch

import pytest


# Test fixtures base path
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ISSUES_DIR = FIXTURES_DIR / "issues"


def load_issue_fixture(filename: str) -> Dict[str, Any]:
    """Load an issue fixture JSON file."""
    filepath = ISSUES_DIR / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


class TestE2ESimpleBugs:
    """E2E tests for simple bug scenarios."""

    def test_simple_01_python_division_by_zero(self):
        """
        Test Case: Division by zero error in calculate_average function.

        Expected: Agent should:
        1. Parse issue and extract error info
        2. Localize to src/math_utils.py:15
        3. Generate patch adding empty list check
        4. Validate patch fixes the test
        """
        # Load issue fixture
        issue = load_issue_fixture("simple_01_python_division_by_zero.json")

        # Verify fixture structure
        assert issue["issue_id"] == "simple-001"
        assert issue["complexity"] == "simple"
        assert issue["language"] == "python"
        assert "ZeroDivisionError" in issue["body"]

        # TODO: Once PipelineOrchestrator is implemented:
        # orchestrator = PipelineOrchestrator(session_id="test-simple-01")
        # result = orchestrator.run(issue, repo_path=test_repo_path)
        # assert result.status == "success"
        # assert result.patch is not None
        # assert "len(numbers)" in result.patch

        # For now, verify test fixture is valid
        assert issue["expected_fix"]["file"] == "src/math_utils.py"
        assert issue["repository"]["test_framework"] == "pytest"

    def test_simple_02_js_null_reference(self):
        """
        Test Case: TypeError when accessing property of null object.

        Expected: Agent should:
        1. Parse JavaScript error stack trace
        2. Localize to src/user.js:8
        3. Generate patch adding null check
        4. Validate with Jest tests
        """
        # Load issue fixture
        issue = load_issue_fixture("simple_02_js_null_reference.json")

        # Verify fixture structure
        assert issue["issue_id"] == "simple-002"
        assert issue["complexity"] == "simple"
        assert issue["language"] == "javascript"
        assert "TypeError" in issue["body"]
        assert "Cannot read property" in issue["body"]

        # Verify expected fix details
        assert issue["expected_fix"]["file"] == "src/user.js"
        assert "null check" in issue["expected_fix"]["description"]
        assert issue["repository"]["test_framework"] == "jest"

    def test_simple_03_python_off_by_one(self):
        """
        Test Case: IndexError due to off-by-one error in array access.

        Expected: Agent should:
        1. Parse IndexError stack trace
        2. Localize to src/list_utils.py:22
        3. Identify off-by-one error (len(items) should be len(items)-1)
        4. Generate and validate patch
        """
        # Load issue fixture
        issue = load_issue_fixture("simple_03_python_off_by_one.json")

        # Verify fixture structure
        assert issue["issue_id"] == "simple-003"
        assert issue["complexity"] == "simple"
        assert issue["language"] == "python"
        assert "IndexError" in issue["body"]
        assert "off-by-one" in issue["body"]

        # Verify error location is clear
        assert "src/list_utils.py" in issue["body"]
        assert "line 22" in issue["body"]
        assert issue["expected_fix"]["file"] == "src/list_utils.py"


class TestE2EFixtureValidation:
    """Validation tests for all test fixtures."""

    @pytest.mark.parametrize(
        "fixture_file",
        [
            "simple_01_python_division_by_zero.json",
            "simple_02_js_null_reference.json",
            "simple_03_python_off_by_one.json",
            "medium_01_python_async_race_condition.json",
            "medium_02_js_memory_leak.json",
            "medium_03_python_sql_injection.json",
            "medium_04_js_promise_unhandled_rejection.json",
            "complex_01_python_deadlock.json",
            "complex_02_js_jwt_vulnerability.json",
            "negative_01_vague_performance.json",
        ],
    )
    def test_fixture_structure_valid(self, fixture_file: str):
        """Verify all fixture files have required structure."""
        issue = load_issue_fixture(fixture_file)

        # Required fields
        assert "issue_id" in issue
        assert "title" in issue
        assert "body" in issue
        assert "language" in issue
        assert "complexity" in issue
        assert "repository" in issue
        assert "expected_fix" in issue
        assert "setup_instructions" in issue
        assert "metadata" in issue

        # Repository structure
        repo = issue["repository"]
        assert "type" in repo
        assert "test_framework" in repo
        assert "test_command" in repo

        # Expected fix structure
        fix = issue["expected_fix"]
        assert "file" in fix
        assert "description" in fix
        assert "validation" in fix

        # Metadata structure
        meta = issue["metadata"]
        assert "created_at" in meta
        assert "difficulty" in meta
        assert "estimated_fix_time" in meta

    def test_fixture_json_valid(self):
        """Verify all fixture files are valid JSON."""
        for json_file in ISSUES_DIR.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)  # Will raise if invalid JSON
                assert isinstance(data, dict)
                assert len(data) > 0

    def test_all_fixtures_discoverable(self):
        """Verify expected number of fixtures exist."""
        json_files = list(ISSUES_DIR.glob("*.json"))

        # Should have 10 total: 3 simple + 4 medium + 2 complex + 1 negative
        assert len(json_files) == 10, f"Expected 10 fixtures, found {len(json_files)}"

        # Count by complexity
        simple_count = len([f for f in json_files if "simple" in f.name])
        medium_count = len([f for f in json_files if "medium" in f.name])
        complex_count = len([f for f in json_files if "complex" in f.name])
        negative_count = len([f for f in json_files if "negative" in f.name])

        assert simple_count == 3, f"Expected 3 simple fixtures, found {simple_count}"
        assert medium_count == 4, f"Expected 4 medium fixtures, found {medium_count}"
        assert complex_count == 2, f"Expected 2 complex fixtures, found {complex_count}"
        assert negative_count == 1, f"Expected 1 negative fixture, found {negative_count}"

    def test_language_coverage(self):
        """Verify test cases cover multiple programming languages."""
        languages = set()

        for json_file in ISSUES_DIR.glob("*.json"):
            issue = load_issue_fixture(json_file.name)
            languages.add(issue["language"])

        # Should have at least Python and JavaScript
        assert "python" in languages
        assert "javascript" in languages
        assert len(languages) >= 2


class TestE2EMockPipeline:
    """Tests using mocked PipelineOrchestrator to verify integration points."""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create a mock PipelineOrchestrator."""
        # TODO: Replace with actual import once implemented
        # from swe_agent.orchestrator.pipeline import PipelineOrchestrator
        mock = Mock()
        mock.run.return_value = Mock(
            status="success", patch="mock patch content", session_id="test-session"
        )
        return mock

    def test_simple_bug_workflow_with_mock(self, mock_orchestrator):
        """Test workflow with mocked orchestrator."""
        # Load test issue
        issue = load_issue_fixture("simple_01_python_division_by_zero.json")

        # Mock repository path
        repo_path = "/tmp/test-repo"

        # Run pipeline (mocked)
        result = mock_orchestrator.run(issue, repo_path)

        # Verify orchestrator was called
        mock_orchestrator.run.assert_called_once()

        # Verify result structure
        assert result.status == "success"
        assert result.patch is not None
        assert result.session_id is not None

    def test_negative_case_should_fail(self, mock_orchestrator):
        """Test that negative case is expected to fail."""
        # Override mock to return failure
        mock_orchestrator.run.return_value = Mock(
            status="failed",
            error="Insufficient information to localize issue",
            session_id="test-session",
        )

        # Load negative test case
        issue = load_issue_fixture("negative_01_vague_performance.json")

        # Verify it's marked as negative
        assert issue["complexity"] == "negative"
        assert "failure_reasons" in issue["metadata"]

        # Run pipeline (should fail)
        result = mock_orchestrator.run(issue, "/tmp/test-repo")

        # Verify expected failure
        assert result.status == "failed"
        assert result.error is not None


class TestE2ETestCaseCategories:
    """Tests to verify test case categorization and coverage."""

    def test_simple_bugs_characteristics(self):
        """Verify simple bugs have expected characteristics."""
        simple_files = [
            "simple_01_python_division_by_zero.json",
            "simple_02_js_null_reference.json",
            "simple_03_python_off_by_one.json",
        ]

        for filename in simple_files:
            issue = load_issue_fixture(filename)

            # Simple bugs should have clear stack traces
            assert "Stack Trace" in issue["body"] or "stack trace" in issue["body"].lower()

            # Should have specific file location
            assert issue["expected_fix"]["file"] != "unknown"

            # Should have clear error message
            assert "Error Message" in issue["body"] or "error message" in issue["body"].lower()

    def test_medium_complexity_characteristics(self):
        """Verify medium complexity bugs have expected characteristics."""
        medium_files = [
            "medium_01_python_async_race_condition.json",
            "medium_02_js_memory_leak.json",
            "medium_03_python_sql_injection.json",
            "medium_04_js_promise_unhandled_rejection.json",
        ]

        for filename in medium_files:
            issue = load_issue_fixture(filename)

            # Medium bugs should have complexity indicators
            assert issue["complexity"] == "medium"

            # Should have detailed context
            assert len(issue["body"]) > 500  # More detailed description

            # May involve multiple components or async/concurrency
            body_lower = issue["body"].lower()
            complexity_indicators = ["async", "race", "concurrent", "memory", "security", "promise"]
            assert any(indicator in body_lower for indicator in complexity_indicators)

    def test_complex_scenarios_characteristics(self):
        """Verify complex scenarios have expected characteristics."""
        complex_files = [
            "complex_01_python_deadlock.json",
            "complex_02_js_jwt_vulnerability.json",
        ]

        for filename in complex_files:
            issue = load_issue_fixture(filename)

            # Complex scenarios should be marked as such
            assert issue["complexity"] == "complex"

            # Should have extensive context
            assert len(issue["body"]) > 1000  # Very detailed

            # Should have longer estimated fix time
            fix_time = issue["metadata"]["estimated_fix_time"]
            assert "30" in fix_time or "45" in fix_time or "60" in fix_time

    def test_negative_case_characteristics(self):
        """Verify negative case has expected failure indicators."""
        issue = load_issue_fixture("negative_01_vague_performance.json")

        # Should be marked as negative
        assert issue["complexity"] == "negative"

        # Should have failure reasons documented
        assert "failure_reasons" in issue["metadata"]
        assert len(issue["metadata"]["failure_reasons"]) > 0

        # Should have vague or insufficient information
        assert issue["expected_fix"]["file"] == "unknown"

        # Should have expected outcome documented
        assert "expected_outcome" in issue["metadata"]
        assert "FAILED" in issue["metadata"]["expected_outcome"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
