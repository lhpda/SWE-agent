"""Real Docker pipeline; only the remote model response is replaced."""

from pathlib import Path
import shutil
from unittest.mock import patch

from swe_agent.agents.patch.generator import PatchGenerator
from swe_agent.config import Config
from swe_agent.orchestrator.pipeline import PipelineOrchestrator
from swe_agent.storage import StateStore
from swe_agent.types import IssueContext, RepositoryContext


def test_real_docker_pipeline_repairs_bug_and_preserves_checkout(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples" / "average"
    repo = tmp_path / "project"
    shutil.copytree(source, repo)
    original = (repo / "calculator.py").read_bytes()
    issue = IssueContext(
        issue_id="docker-e2e",
        title="Empty list average",
        body="Return zero for an empty list.",
        parsed={"files": ["calculator.py"]},
        metadata={},
    )
    repository = RepositoryContext(
        path=str(repo), git={}, project_type="python", test_framework="pytest", dependencies={}
    )
    store = StateStore(tmp_path / "state")
    pipeline = PipelineOrchestrator(issue, repository, store, config=Config())
    code = "def calculate_average(values):\n    if not values:\n        return 0\n    return sum(values) / len(values)\n"
    with patch.object(
        PatchGenerator, "_call_llm_multiple", return_value=[{"code": code, "confidence": 0.9}]
    ):
        result = pipeline.run()
    assert result.status == "success", result.error
    assert pipeline.stage_results["reproduction"].status == "reproduced"
    assert pipeline.stage_results["validation"].test_results["passed"] == 3
    assert pipeline.stage_results["validation"].test_results["failed"] == 0
    assert "+    if not values:" in result.final_patch["unified_diff"]
    assert (repo / "calculator.py").read_bytes() == original
    assert pipeline.sandbox is None
    restored = PipelineOrchestrator.resume(pipeline.session_id, store)
    assert restored.run().status == "success"
    assert store.load_state(pipeline.session_id).status == "success"
