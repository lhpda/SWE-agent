"""Offline regressions for the real CLI and persisted pipeline lifecycle."""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from swe_agent.agents.localization.agent import LocalizationAgent
from swe_agent.agents.patch.generator import PatchGenerator
from swe_agent.agents.patch.agent import PatchGeneratorAgent
from swe_agent.agents.validation.agent import ValidationAgent
from swe_agent.orchestrator.pipeline import PipelineOrchestrator
from swe_agent.orchestrator.state_machine import State
from swe_agent.storage import StateStore
from swe_agent.types import IssueContext, LocalizationResult, RepositoryContext


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _python(code, cwd, extra_env=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    for key in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        env.pop(key, None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _contexts(tmp_path):
    (tmp_path / "calculator.py").write_text(
        "def divide(a, b):\n    return a / b\n", encoding="utf-8"
    )
    issue = IssueContext(
        issue_id="runtime-regression",
        title="Division by zero",
        body="Traceback (most recent call last):\n"
        '  File "calculator.py", line 2, in divide\n'
        "    return a / b\nZeroDivisionError: division by zero\n",
        parsed={"files": ["calculator.py"], "relevant_functions": ["divide"]},
        metadata={"test_command": "python -m pytest -q"},
    )
    repository = RepositoryContext(
        path=str(tmp_path),
        git={"branch": "main", "commit": "abc123"},
        project_type="python",
        test_framework="pytest",
        dependencies={},
    )
    return issue, repository


def test_cli_without_config_file_reads_provider_and_model_environment():
    result = _python(
        "from swe_agent.cli import load_config_file\n"
        "config = load_config_file(None)\n"
        "assert config.llm_provider == 'deepseek', config.llm_provider\n"
        "assert config.llm_model == 'deepseek-chat', config.llm_model\n",
        PROJECT_ROOT,
        {"SWE_AGENT_LLM_PROVIDER": "deepseek", "SWE_AGENT_LLM_MODEL": "deepseek-chat"},
    )
    assert result.returncode == 0, result.stderr


def test_patch_diff_formatting_does_not_require_credentials(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    generator = PatchGenerator()
    diff = generator.format_as_unified_diff("value = 1\n", "value = 2\n", filename="calculator.py")
    assert "-value = 1" in diff
    assert "+value = 2" in diff


def test_issue_code_context_does_not_hide_body_stack_trace(tmp_path):
    issue, repository = _contexts(tmp_path)
    result = LocalizationAgent(issue, repository).run()
    assert result.status in {"success", "partial"}
    assert any(
        Path(candidate["file_path"]).name == "calculator.py" for candidate in result.candidates
    )


def test_cli_can_be_imported_outside_project_checkout(tmp_path):
    result = _python("from swe_agent.cli import create_parser\ncreate_parser()", tmp_path)
    assert result.returncode == 0, result.stderr


def test_resume_restores_issue_repository_and_completed_stage(tmp_path):
    issue, repository = _contexts(tmp_path)
    store = StateStore(tmp_path / "state")
    original = PipelineOrchestrator(issue, repository, store, session_id="resume-test")
    original.state_machine.transition(State.LOCALIZING)
    original.state_machine.save_state(store)
    localization = LocalizationResult(
        status="success",
        candidates=[{"file_path": "calculator.py", "confidence": 0.95}],
        search_strategy="stack_trace",
        execution_time=0.01,
        tool_calls=1,
    )
    store.save_stage_result(original.session_id, "localization", localization)
    restored = PipelineOrchestrator.resume(original.session_id, store)
    assert restored.issue == issue
    assert restored.repository == repository
    assert restored.stage_results["localization"] == localization
    assert restored.state_machine.get_current_state() == State.LOCALIZING


def test_status_reads_real_state_store_metadata(tmp_path):
    issue, repository = _contexts(tmp_path)
    store = StateStore(tmp_path / "state")
    pipeline = PipelineOrchestrator(issue, repository, store, session_id="status-test")
    pipeline.state_machine.transition(State.LOCALIZING)
    pipeline.state_machine.save_state(store)
    result = _python(
        "from argparse import Namespace\n"
        "from unittest.mock import patch\n"
        "from swe_agent.storage import StateStore\n"
        "from swe_agent.cli import status_command\n"
        f"store = StateStore({str(store.base_path)!r})\n"
        "with patch('swe_agent.cli.StateStore', return_value=store):\n"
        "    raise SystemExit(status_command(Namespace(run_id='status-test')))\n",
        PROJECT_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "status-test" in result.stdout
    assert "localizing" in result.stdout.lower()


@pytest.mark.parametrize(
    "test_results",
    [
        {"passed": 0, "failed": 1, "total": 1, "failed_tests": ["test_bug"], "exit_code": 1},
        {"passed": 0, "failed": 0, "total": 0, "failed_tests": [], "exit_code": 5},
        {"passed": 1, "failed": 0, "total": 1, "failed_tests": [], "exit_code": 2},
        {
            "passed": 1,
            "failed": 0,
            "total": 1,
            "failed_tests": [],
            "exit_code": 0,
            "timed_out": True,
        },
    ],
    ids=["unchanged-failure", "no-tests", "execution-error", "timeout"],
)
def test_validation_does_not_pass_without_successful_tests(test_results):
    """No new failures is insufficient: the post-patch test run must succeed."""
    agent = ValidationAgent(
        {"patches": [{"id": "candidate", "file": "calculator.py", "content": {}}]},
        sandbox=None,
        repo_context={"path": ".", "test_command": "python -m pytest"},
    )
    agent.applicator.apply_patch = Mock(return_value={"success": True, "applied": True})
    agent.test_runner.run_test_suite = Mock(side_effect=[dict(test_results), dict(test_results)])
    result = agent.run()
    assert result["status"] in {"failed", "error"}, result


def _generated_patch(tmp_path):
    source = tmp_path / "calculator.py"
    source.write_text("def answer():\n    return 41\n", encoding="utf-8")
    replacement = "def answer():\n    return 42\n"
    llm = Mock()
    llm.generate.return_value = replacement
    generator = PatchGenerator(llm_client=llm)
    patch = generator.generate_patch(
        {"file_path": str(source), "context": source.read_text(encoding="utf-8")},
        {"description": "Wrong constant"},
        {"error_type": "AssertionError"},
    )
    return source, replacement, generator, patch


def test_generated_unified_diff_passes_patch_agent_syntax_validation(tmp_path, monkeypatch):
    source, _, generator, patch = _generated_patch(tmp_path)
    monkeypatch.setattr(
        "swe_agent.agents.patch.agent.PatchGenerator", lambda *args, **kwargs: generator
    )
    agent = PatchGeneratorAgent(
        {"candidates": [{"file_path": str(source)}]},
        {"root_cause": {}, "error_details": {}},
        {"path": str(tmp_path)},
    )
    accepted = agent._validate_patches([patch])
    assert len(accepted) == 1, "Valid replacement code must not be parsed as diff syntax"
    assert accepted[0]["patch_id"] == patch["patch_id"]
    assert accepted[0]["validation"]["is_valid"]
    assert "return 41" in source.read_text(encoding="utf-8"), "Validation must not edit source"


def test_validation_consumes_generated_patch_and_preserves_its_id(tmp_path):
    source, replacement, _, patch = _generated_patch(tmp_path)
    agent = ValidationAgent(
        {"patches": [patch], "target_test": "test_answer"},
        sandbox=None,
        repo_context={"path": str(tmp_path), "test_command": "python -m pytest"},
    )
    agent.test_runner.run_test_suite = Mock(
        side_effect=[
            {
                "passed": 0,
                "failed": 1,
                "total": 1,
                "failed_tests": ["test_answer"],
                "exit_code": 1,
                "timed_out": False,
            },
            {
                "passed": 1,
                "failed": 0,
                "total": 1,
                "failed_tests": [],
                "exit_code": 0,
                "timed_out": False,
            },
        ]
    )
    result = agent.run()
    assert result["status"] == "passed", result
    assert result["patch_applied"] is True
    assert result["patch_id"] == patch["patch_id"]
    assert "return 41" in source.read_text(encoding="utf-8"), "Validation must restore the baseline"


def test_cli_exports_git_applicable_lf_patch(tmp_path):
    import json

    source = tmp_path / "calculator.py"
    source.write_text("value = 1\n", encoding="utf-8", newline="")
    diff = PatchGenerator().format_as_unified_diff("value = 1\n", "value = 2\n", "calculator.py")
    issue = tmp_path / "issue.json"
    issue.write_text(
        json.dumps({"repo_path": str(tmp_path), "title": "Wrong value", "body": "Return 2"})
    )
    output = tmp_path / "output"
    result = _python(
        "from types import SimpleNamespace\n"
        "from unittest.mock import patch\n"
        "from swe_agent.cli import run_command\n"
        f"result = SimpleNamespace(status='success', session_id='export', final_patch={{'unified_diff': {diff!r}}})\n"
        "with patch('swe_agent.cli.PipelineOrchestrator') as factory:\n"
        "    factory.return_value.run.return_value = result\n"
        f"    code = run_command(SimpleNamespace(issue_file={str(issue)!r}, output={str(output)!r}, config=None, timeout=None, verbose=False))\n"
        "raise SystemExit(code)",
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    patch_file = output / "final_patch.diff"
    assert patch_file.read_bytes() == diff.encode("utf-8")
    applied = subprocess.run(
        ["git", "apply", "--check", str(patch_file)], cwd=tmp_path, capture_output=True
    )
    assert applied.returncode == 0, applied.stderr
