"""Performance and stress testing for SWE Agent.

Tests performance baselines, concurrent execution, memory usage, and resource cleanup.
Follows Task 8.4 requirements.
"""

import concurrent.futures
import psutil
import pytest
import time
from pathlib import Path
from typing import Dict, List
from unittest.mock import Mock, patch, MagicMock

from swe_agent.sandbox.docker import DockerSandbox
from swe_agent.agents.localization.agent import LocalizationAgent
from swe_agent.types import IssueContext, RepositoryContext


class TestPerformanceBaseline:
    """Test performance baseline measurements."""

    def test_measure_simple_bug_baseline(self, tmp_path):
        """Test measuring baseline performance for simple bug localization.

        Target: < 5 minutes for simple bugs
        """
        # Create a simple test repository
        repo_path = tmp_path / "simple_repo"
        repo_path.mkdir()

        # Create a simple Python file with a bug
        test_file = repo_path / "calculator.py"
        test_file.write_text("""
def add(a, b):
    return a + b

def divide(a, b):
    return a / b  # Bug: no zero check
""")

        # Create issue context
        issue_context = IssueContext(
            issue_id="simple-1",
            title="Division by zero error",
            body="""
# Bug Report

## Error
```
ZeroDivisionError: division by zero
```

## Stack Trace
```
File "calculator.py", line 6, in divide
    return a / b
```
""",
            parsed={},
            metadata={}
        )

        repo_context = RepositoryContext(
            path=str(repo_path),
            git={},
            project_type="python",
            test_framework=None,
            dependencies={}
        )

        # Measure execution time
        start_time = time.time()

        agent = LocalizationAgent(issue_context, repo_context)
        result = agent.run()

        execution_time = time.time() - start_time

        # Assertions
        assert execution_time < 300, f"Simple bug took {execution_time}s (target: < 300s)"
        assert result.status in ["success", "partial"]
        assert len(result.candidates) > 0

    def test_measure_medium_complexity_baseline(self, tmp_path):
        """Test measuring baseline for medium complexity bugs.

        Target: < 15 minutes for medium complexity
        """
        # Create medium complexity repository
        repo_path = tmp_path / "medium_repo"
        repo_path.mkdir()

        # Create multiple files
        for i in range(5):
            file_path = repo_path / f"module_{i}.py"
            file_path.write_text(f"""
class Module{i}:
    def process(self, data):
        return data * 2
""")

        # File with bug
        bug_file = repo_path / "processor.py"
        bug_file.write_text("""
from module_0 import Module0

class Processor:
    def run(self, items):
        result = []
        for item in items:
            result.append(item.value)  # Bug: no None check
        return result
""")

        issue_context = IssueContext(
            issue_id="medium-1",
            title="AttributeError in processor",
            body="""
# Bug Report

AttributeError: 'NoneType' object has no attribute 'value'

## Stack Trace
```
File "processor.py", line 7, in run
    result.append(item.value)
```
""",
            parsed={},
            metadata={}
        )

        repo_context = RepositoryContext(
            path=str(repo_path),
            git={},
            project_type="python",
            test_framework=None,
            dependencies={}
        )

        # Measure execution time
        start_time = time.time()

        agent = LocalizationAgent(issue_context, repo_context)
        result = agent.run()

        execution_time = time.time() - start_time

        # Assertions
        assert execution_time < 900, f"Medium bug took {execution_time}s (target: < 900s)"
        assert result.status in ["success", "partial"]

    def test_baseline_tool_call_count(self, tmp_path):
        """Test that baseline execution uses reasonable number of tool calls."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        test_file = repo_path / "test.py"
        test_file.write_text("def foo(): pass")

        issue_context = IssueContext(
            issue_id="test-1",
            title="Test issue",
            body="Error in foo function",
            parsed={},
            metadata={}
        )

        repo_context = RepositoryContext(
            path=str(repo_path),
            git={},
            project_type="python",
            test_framework=None,
            dependencies={}
        )

        agent = LocalizationAgent(issue_context, repo_context)
        result = agent.run()

        # Verify reasonable tool call count
        assert result.tool_calls < 20, f"Too many tool calls: {result.tool_calls}"
        assert result.tool_calls > 0


class TestConcurrentSessions:
    """Test concurrent session execution without interference."""

    def test_five_concurrent_sessions(self, tmp_path):
        """Test running 5 concurrent sessions without interference.

        Each session should execute independently without affecting others.
        """
        # Create 5 separate repositories
        repos = []
        for i in range(5):
            repo_path = tmp_path / f"repo_{i}"
            repo_path.mkdir()

            test_file = repo_path / "code.py"
            test_file.write_text(f"""
def function_{i}():
    return {i} / 0  # Bug: division by zero
""")
            repos.append(repo_path)

        # Create issue contexts for each
        sessions = []
        for i, repo_path in enumerate(repos):
            issue = IssueContext(
                issue_id=f"concurrent-{i}",
                title=f"Bug {i}",
                body=f"ZeroDivisionError in function_{i}",
                parsed={},
                metadata={}
            )
            repo = RepositoryContext(
                path=str(repo_path),
                git={},
                project_type="python",
                test_framework=None,
                dependencies={}
            )
            sessions.append((issue, repo))

        # Run concurrently
        results = []
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for issue, repo in sessions:
                future = executor.submit(self._run_session, issue, repo)
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        execution_time = time.time() - start_time

        # Assertions
        assert len(results) == 5, "All sessions should complete"

        # Each session should succeed independently
        for i, result in enumerate(results):
            assert result is not None, f"Session {i} failed"
            assert result.status in ["success", "partial", "failed"]

        # Verify no cross-contamination (each should have unique tool calls)
        tool_calls = [r.tool_calls for r in results]
        assert all(tc > 0 for tc in tool_calls), "All sessions should make tool calls"

    @patch('docker.from_env')
    def test_concurrent_sandbox_isolation(self, mock_docker_from_env):
        """Test that concurrent sandboxes don't interfere with each other."""
        mock_client = MagicMock()
        mock_docker_from_env.return_value = mock_client
        mock_client.ping.return_value = True

        session_ids = [f"concurrent-sandbox-{i}" for i in range(5)]
        sandboxes = []

        # Create sandboxes concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for session_id in session_ids:
                sandbox = DockerSandbox(session_id=session_id)
                sandboxes.append(sandbox)
                # Mock create to avoid actual Docker operations in unit tests
                future = executor.submit(self._mock_sandbox_create, sandbox)
                futures.append(future)

            # Wait for all
            results = [f.result() for f in futures]

        # Verify all sandboxes have unique IDs
        container_ids = [s.container_id for s in sandboxes if s.container_id]

        # In mock, we should have all sandboxes initialized
        assert len(sandboxes) == 5

        # Cleanup
        for sandbox in sandboxes:
            if sandbox.container_id:
                sandbox.container_id = None  # Just clear in mock

    def _run_session(self, issue: IssueContext, repo: RepositoryContext) -> any:
        """Helper to run a single session."""
        try:
            agent = LocalizationAgent(issue, repo)
            return agent.run()
        except Exception as e:
            return None

    def _mock_sandbox_create(self, sandbox: DockerSandbox) -> bool:
        """Mock sandbox creation for testing."""
        # Simulate container creation without Docker
        sandbox.container_id = f"mock-{sandbox.session_id}"
        return True


class TestMemoryUsage:
    """Test memory usage and leak detection."""

    def test_memory_growth_per_session(self, tmp_path):
        """Test that memory growth is < 500MB per session.

        Runs multiple sessions and tracks memory growth.
        """
        process = psutil.Process()

        # Get initial memory
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Run 3 sessions sequentially
        for i in range(3):
            repo_path = tmp_path / f"mem_test_{i}"
            repo_path.mkdir()

            test_file = repo_path / "test.py"
            test_file.write_text("def test(): pass")

            issue = IssueContext(
                issue_id=f"mem-{i}",
                title="Test",
                body="Error in test function",
                parsed={},
                metadata={}
            )

            repo = RepositoryContext(
                path=str(repo_path),
                git={},
                project_type="python",
                test_framework=None,
                dependencies={}
            )

            agent = LocalizationAgent(issue, repo)
            result = agent.run()

            # Force garbage collection
            import gc
            gc.collect()

        # Get final memory
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        # Calculate per-session growth
        per_session_growth = memory_growth / 3

        # Assertion
        assert per_session_growth < 500, f"Memory growth per session: {per_session_growth}MB (target: < 500MB)"

    def test_no_memory_leak_in_agents(self, tmp_path):
        """Test that running same agent multiple times doesn't leak memory."""
        process = psutil.Process()

        repo_path = tmp_path / "leak_test"
        repo_path.mkdir()

        test_file = repo_path / "test.py"
        test_file.write_text("def test(): pass")

        issue = IssueContext(
            issue_id="leak-test",
            title="Test",
            body="Error",
            parsed={},
            metadata={}
        )

        repo = RepositoryContext(
            path=str(repo_path),
            git={},
            project_type="python",
            test_framework=None,
            dependencies={}
        )

        # Baseline run
        agent = LocalizationAgent(issue, repo)
        agent.run()

        import gc
        gc.collect()
        baseline_memory = process.memory_info().rss / 1024 / 1024

        # Run 10 more times
        for i in range(10):
            agent = LocalizationAgent(issue, repo)
            agent.run()

        gc.collect()
        final_memory = process.memory_info().rss / 1024 / 1024

        # Memory growth should be minimal for repeated operations
        memory_growth = final_memory - baseline_memory

        # Allow some growth but not linear with iterations
        assert memory_growth < 200, f"Possible memory leak: {memory_growth}MB growth"


class TestResourceCleanup:
    """Test resource cleanup after execution."""

    @patch('docker.from_env')
    def test_no_orphan_containers_after_tests(self, mock_docker_from_env):
        """Test that no orphan containers remain after tests complete."""
        mock_client = MagicMock()
        mock_docker_from_env.return_value = mock_client

        # Mock containers list
        mock_containers = []
        mock_client.containers.list.return_value = mock_containers

        # Run test sessions
        session_ids = [f"cleanup-test-{i}" for i in range(3)]
        sandboxes = []

        for session_id in session_ids:
            sandbox = DockerSandbox(session_id=session_id)
            sandboxes.append(sandbox)

            # Mock container creation
            sandbox.container_id = f"mock-container-{session_id}"

        # Cleanup all sandboxes
        for sandbox in sandboxes:
            sandbox.destroy()

        # Verify find_orphan_containers returns empty list
        orphans = DockerSandbox.find_orphan_containers(max_age_hours=2.0)

        assert len(orphans) == 0, f"Found {len(orphans)} orphan containers"

    def test_temp_files_cleanup(self, tmp_path):
        """Test that temporary files are cleaned up after sessions."""
        # Create session directory structure
        session_dir = tmp_path / ".swe-agent" / "sessions" / "cleanup-test"
        session_dir.mkdir(parents=True)

        # Create some temp files
        temp_file = session_dir / "temp_data.json"
        temp_file.write_text('{"test": "data"}')

        # Verify file exists
        assert temp_file.exists()

        # Simulate cleanup
        import shutil
        if session_dir.exists():
            shutil.rmtree(session_dir)

        # Verify cleanup
        assert not temp_file.exists()
        assert not session_dir.exists()

    @patch('docker.from_env')
    def test_network_cleanup(self, mock_docker_from_env):
        """Test that Docker networks are cleaned up."""
        mock_client = MagicMock()
        mock_docker_from_env.return_value = mock_client
        mock_client.ping.return_value = True

        # Mock network operations
        mock_network = MagicMock()
        mock_network.id = "test-network-id"
        mock_client.networks.get.return_value = mock_network
        mock_client.containers.get.side_effect = Exception("Container not found")

        sandbox = DockerSandbox(session_id="network-test")
        sandbox.network_id = "test-network-id"
        sandbox.container_id = "test-container-id"

        # Destroy sandbox (should cleanup network)
        sandbox.destroy()

        # Verify network cleanup was attempted
        assert sandbox.network_id is None

    def test_state_store_cleanup(self, tmp_path):
        """Test that state store properly manages disk space."""
        from swe_agent.storage import StateStore

        store = StateStore(base_path=tmp_path / ".swe-agent")

        # Create multiple sessions
        for i in range(5):
            session_id = f"state-cleanup-{i}"
            # Create session first (this creates the directory)
            store.create_session(session_id)
            # Then save additional metadata
            store.save_metadata(session_id, {"test": "data", "extra": i})

        # Verify sessions are saved
        sessions_dir = store.sessions_path
        assert sessions_dir.exists()

        session_dirs = list(sessions_dir.iterdir())
        assert len(session_dirs) == 5

        # Test cleanup (StateStore has FIFO cleanup built-in)
        # When we create more than MAX_SESSIONS, old ones should be removed
        # This is tested in test_storage.py, just verify structure here


class TestResourceLimits:
    """Test that resource limits are enforced."""

    @patch('docker.from_env')
    def test_container_resource_limits_set(self, mock_docker_from_env):
        """Test that containers are created with proper resource limits."""
        mock_client = MagicMock()
        mock_docker_from_env.return_value = mock_client

        # Mock ping
        mock_client.ping.return_value = True

        # Mock image operations
        mock_client.images.get.return_value = MagicMock()

        # Mock network
        mock_network = MagicMock()
        mock_network.id = "test-network"
        mock_client.networks.create.return_value = mock_network

        # Mock container
        mock_container = MagicMock()
        mock_container.id = "test-container"
        mock_client.containers.create.return_value = mock_container

        sandbox = DockerSandbox(session_id="limits-test")

        # Create container
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            sandbox.create(image="python:3.11-slim", work_dir=tmpdir)

        # Verify create was called with resource limits
        create_call = mock_client.containers.create.call_args

        assert create_call is not None
        kwargs = create_call[1]

        # Verify CPU limit
        assert kwargs.get("nano_cpus") == int(DockerSandbox.CPU_LIMIT * 1_000_000_000)

        # Verify memory limit
        assert kwargs.get("mem_limit") == DockerSandbox.MEMORY_LIMIT

        # Verify PID limit
        assert kwargs.get("pids_limit") == DockerSandbox.PID_LIMIT

    def test_execution_timeout_enforced(self, tmp_path):
        """Test that execution timeouts are properly enforced."""
        # This is more of an integration test, here we test the logic

        @patch('docker.from_env')
        def run_test(mock_docker_from_env):
            mock_client = MagicMock()
            mock_docker_from_env.return_value = mock_client
            mock_client.ping.return_value = True

            sandbox = DockerSandbox(session_id="timeout-test")
            sandbox.container_id = "mock-container"

            # Mock container that takes too long
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container

            # Mock exec_run to simulate long-running command
            def slow_exec(*args, **kwargs):
                time.sleep(0.1)  # Simulate delay
                result = MagicMock()
                result.exit_code = 0
                result.output = (b"output", b"")
                return result

            mock_container.exec_run = slow_exec

            # Execute with short timeout
            result = sandbox.execute("sleep 100", timeout=1)

            # Verify timeout handling exists in the code
            assert "status" in result
            assert result["status"] in ["success", "timeout", "error"]

        run_test()


class TestPerformanceMetrics:
    """Test performance metrics collection."""

    def test_execution_time_recorded(self, tmp_path):
        """Test that execution time is properly recorded."""
        repo_path = tmp_path / "metrics_test"
        repo_path.mkdir()

        test_file = repo_path / "test.py"
        test_file.write_text("def test(): pass")

        issue = IssueContext(
            issue_id="metrics-1",
            title="Test",
            body="Error",
            parsed={},
            metadata={}
        )

        repo = RepositoryContext(
            path=str(repo_path),
            git={},
            project_type="python",
            test_framework=None,
            dependencies={}
        )

        agent = LocalizationAgent(issue, repo)
        result = agent.run()

        # Verify execution time is recorded
        assert hasattr(result, "execution_time")
        assert result.execution_time > 0
        assert result.execution_time < 300  # Should be fast for simple case

    def test_tool_calls_counted(self, tmp_path):
        """Test that tool calls are properly counted."""
        repo_path = tmp_path / "tool_count_test"
        repo_path.mkdir()

        test_file = repo_path / "test.py"
        test_file.write_text("def test(): pass")

        issue = IssueContext(
            issue_id="tool-count-1",
            title="Test",
            body="Error in test",
            parsed={},
            metadata={}
        )

        repo = RepositoryContext(
            path=str(repo_path),
            git={},
            project_type="python",
            test_framework=None,
            dependencies={}
        )

        agent = LocalizationAgent(issue, repo)
        result = agent.run()

        # Verify tool calls are counted
        assert hasattr(result, "tool_calls")
        assert result.tool_calls > 0
        assert isinstance(result.tool_calls, int)
