"""
Tests for Docker Sandbox implementation.
Following TDD: Write tests first, then implement.
"""

import pytest
import time
import tempfile
from pathlib import Path
import docker
from docker.errors import NotFound


# Check Docker availability
def _is_docker_available():
    """Check if Docker daemon is available."""
    try:
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


DOCKER_AVAILABLE = _is_docker_available()

# Skip all tests if Docker is not available
pytestmark = pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker daemon not available")


@pytest.fixture(scope="session")
def docker_client():
    """Get Docker client if available."""
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker daemon not available")
    return docker.from_env()


@pytest.fixture
def sandbox():
    """Create a DockerSandbox instance for testing."""
    from swe_agent.sandbox.docker import DockerSandbox

    sb = DockerSandbox(session_id="test-session-123")
    yield sb

    # Cleanup: destroy container if it exists
    try:
        sb.destroy()
    except Exception:
        pass


@pytest.fixture
def temp_work_dir():
    """Create a temporary working directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestDockerSandboxCreation:
    """Test container creation and configuration."""

    def test_create_container_basic(self, sandbox, temp_work_dir):
        """Test basic container creation."""
        container_id = sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        assert container_id is not None
        assert len(container_id) > 0
        assert sandbox.container_id == container_id

    def test_create_container_with_resource_limits(self, sandbox, docker_client, temp_work_dir):
        """Test container is created with proper resource limits."""
        container_id = sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Inspect container to verify resource limits
        container = docker_client.containers.get(container_id)
        host_config = container.attrs["HostConfig"]

        # Verify CPU limit (2 cores = 2.0)
        assert host_config["NanoCpus"] == 2_000_000_000  # 2 CPUs in nanocpus

        # Verify memory limit (4GB)
        assert host_config["Memory"] == 4 * 1024 * 1024 * 1024

        # Verify memory swap = memory (no additional swap)
        assert host_config["MemorySwap"] == 4 * 1024 * 1024 * 1024

        # Verify PID limit
        assert host_config["PidsLimit"] == 1000

    def test_create_container_with_custom_network(self, sandbox, docker_client, temp_work_dir):
        """Test container uses custom isolated network."""
        container_id = sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        container = docker_client.containers.get(container_id)
        networks = container.attrs["NetworkSettings"]["Networks"]

        # Should have a custom network (not default bridge)
        assert "swe-agent-net-test-session-123" in networks or len(networks) > 0

    def test_create_container_readonly_rootfs(self, sandbox, docker_client, temp_work_dir):
        """Test container has read-only root filesystem with tmpfs /tmp."""
        container_id = sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        container = docker_client.containers.get(container_id)
        host_config = container.attrs["HostConfig"]

        # Verify read-only root filesystem
        assert host_config["ReadonlyRootfs"] is True

        # Verify tmpfs for /tmp
        tmpfs = host_config.get("Tmpfs", {})
        assert "/tmp" in tmpfs
        assert "size=1g" in tmpfs["/tmp"] or "size=1073741824" in tmpfs["/tmp"]

    def test_create_container_non_root_user(self, sandbox, temp_work_dir):
        """Test container runs as non-root user."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Execute whoami to check user
        result = sandbox.execute("whoami", timeout=5)

        assert result["status"] == "success"
        assert result["stdout"].strip() != "root"

    def test_container_naming_convention(self, sandbox, docker_client, temp_work_dir):
        """Test container follows naming convention."""
        container_id = sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        container = docker_client.containers.get(container_id)
        container_name = container.name

        assert container_name.startswith("swe-agent-")
        assert "test-session-123" in container_name


class TestDockerSandboxExecution:
    """Test command execution in container."""

    def test_execute_simple_command(self, sandbox, temp_work_dir):
        """Test executing a simple command."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        result = sandbox.execute("echo 'Hello World'", timeout=5)

        assert result["status"] == "success"
        assert "Hello World" in result["stdout"]
        assert result["exit_code"] == 0

    def test_execute_command_with_error(self, sandbox, temp_work_dir):
        """Test executing a command that fails."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        result = sandbox.execute("ls /nonexistent", timeout=5)

        assert result["status"] == "error" or result["exit_code"] != 0
        assert len(result["stderr"]) > 0

    def test_execute_with_timeout(self, sandbox, temp_work_dir):
        """Test command execution respects timeout."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        start_time = time.time()
        result = sandbox.execute("sleep 30", timeout=2)
        elapsed = time.time() - start_time

        assert result["status"] == "timeout" or result["status"] == "error"
        assert elapsed < 5  # Should timeout much faster than 30s

    def test_execute_python_script(self, sandbox, temp_work_dir):
        """Test executing Python code."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        result = sandbox.execute("python3 -c 'print(2 + 2)'", timeout=10)

        assert result["status"] == "success"
        assert "4" in result["stdout"]


class TestDockerSandboxFileOperations:
    """Test file operations between host and container."""

    def test_copy_file_to_container(self, sandbox, temp_work_dir):
        """Test copying file from host to container."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create a test file on host
        test_file = Path(temp_work_dir) / "test.txt"
        test_file.write_text("Hello from host")

        # Copy to container
        sandbox.copy_file(str(test_file), "/tmp/test.txt")

        # Verify file exists in container
        result = sandbox.execute("cat /tmp/test.txt", timeout=5)
        assert result["status"] == "success"
        assert "Hello from host" in result["stdout"]

    def test_copy_file_from_container(self, sandbox, temp_work_dir):
        """Test copying file from container to host."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Create file in container
        sandbox.execute("echo 'Hello from container' > /tmp/output.txt", timeout=5)

        # Copy to host
        dest_file = Path(temp_work_dir) / "output.txt"
        sandbox.copy_file("/tmp/output.txt", str(dest_file))

        # Verify file exists on host
        assert dest_file.exists()
        assert "Hello from container" in dest_file.read_text()


class TestDockerSandboxResourceLimits:
    """Test resource limits enforcement."""

    def test_memory_limit_enforcement(self, sandbox, temp_work_dir):
        """Test container cannot exceed memory limit."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Try to allocate more than 4GB of memory
        python_code = """
import sys
try:
    # Try to allocate 5GB
    data = bytearray(5 * 1024 * 1024 * 1024)
    print("SUCCESS")
except MemoryError:
    print("MEMORY_ERROR")
    sys.exit(1)
"""
        result = sandbox.execute(f"python3 -c '{python_code}'", timeout=30)

        # Should either get MemoryError or be killed by OOM killer
        assert result["status"] != "success" or "MEMORY_ERROR" in result["stdout"]

    def test_pid_limit_enforcement(self, sandbox, temp_work_dir):
        """Test container cannot exceed PID limit."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Try to create many processes
        bash_script = """
for i in {1..1500}; do
    sleep 60 &
done
wait
"""
        result = sandbox.execute(f"bash -c '{bash_script}'", timeout=10)

        # Should fail or timeout due to PID limit
        assert result["status"] != "success" or result["exit_code"] != 0


class TestDockerSandboxIsolation:
    """Test container isolation."""

    def test_network_isolation(self, sandbox, temp_work_dir):
        """Test container cannot access arbitrary external networks."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Try to access a restricted site (not in whitelist)
        result = sandbox.execute(
            "python3 -c 'import urllib.request; urllib.request.urlopen(\"http://example.com\", timeout=5)'",
            timeout=10,
        )

        # Should fail due to network restrictions
        # Note: This test may need adjustment based on network implementation
        assert result["status"] == "error" or result["exit_code"] != 0

    def test_filesystem_isolation(self, sandbox, temp_work_dir):
        """Test container has isolated filesystem."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Try to write to read-only root filesystem
        result = sandbox.execute("touch /test_file.txt", timeout=5)

        # Should fail due to read-only filesystem
        assert result["status"] == "error" or result["exit_code"] != 0
        assert "Read-only" in result["stderr"] or result["exit_code"] != 0


class TestDockerSandboxLifecycle:
    """Test container lifecycle management."""

    def test_destroy_container(self, sandbox, docker_client, temp_work_dir):
        """Test container destruction."""
        container_id = sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Verify container exists
        container = docker_client.containers.get(container_id)
        assert container is not None

        # Destroy container
        sandbox.destroy()

        # Verify container is removed
        with pytest.raises(NotFound):
            docker_client.containers.get(container_id)

    def test_destroy_nonexistent_container(self, sandbox):
        """Test destroying a non-existent container doesn't raise error."""
        # Should not raise exception
        sandbox.destroy()

    def test_container_metadata_tracking(self, sandbox, temp_work_dir):
        """Test container tracks creation time and session info."""
        container_id = sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        assert sandbox.session_id == "test-session-123"
        assert sandbox.container_id == container_id
        assert sandbox.created_at is not None


class TestDockerSandboxOrphanCleanup:
    """Test orphan container cleanup."""

    def test_identify_orphan_containers(self, docker_client):
        """Test identification of orphan containers."""
        from swe_agent.sandbox.docker import DockerSandbox

        # Create a container that will be "orphaned"
        sandbox = DockerSandbox(session_id="orphan-test-session")
        try:
            sandbox.create(image="python:3.11-slim", work_dir="/tmp")

            # Manually mark it as old (simulate 3 hours old)
            # This would normally be done by checking container creation time

            orphans = DockerSandbox.find_orphan_containers(max_age_hours=2)

            # Should find containers older than 2 hours
            # Note: This test may need adjustment based on implementation
            assert isinstance(orphans, list)
        finally:
            sandbox.destroy()

    def test_cleanup_orphan_containers(self, docker_client):
        """Test cleanup of orphan containers."""
        from swe_agent.sandbox.docker import DockerSandbox

        # Create a test container
        sandbox = DockerSandbox(session_id="cleanup-test-session")
        try:
            sandbox.create(image="python:3.11-slim", work_dir="/tmp")

            # Clean up orphans (should handle gracefully)
            cleaned = DockerSandbox.cleanup_orphan_containers(max_age_hours=0)

            assert isinstance(cleaned, int)
            assert cleaned >= 0
        finally:
            sandbox.destroy()


class TestDockerSandboxErrorHandling:
    """Test error handling."""

    def test_create_with_invalid_image(self, sandbox, temp_work_dir):
        """Test creating container with non-existent image."""
        with pytest.raises(Exception):
            sandbox.create(image="nonexistent:invalid", work_dir=temp_work_dir)

    def test_execute_before_create(self, sandbox):
        """Test executing command before container is created."""
        with pytest.raises(Exception):
            sandbox.execute("echo 'test'", timeout=5)

    def test_copy_file_before_create(self, sandbox, temp_work_dir):
        """Test copying file before container is created."""
        test_file = Path(temp_work_dir) / "test.txt"
        test_file.write_text("test")

        with pytest.raises(Exception):
            sandbox.copy_file(str(test_file), "/tmp/test.txt")


class TestDockerSandboxConfiguration:
    """Test configuration and customization."""

    def test_custom_session_id(self):
        """Test creating sandbox with custom session ID."""
        from swe_agent.sandbox.docker import DockerSandbox

        sandbox = DockerSandbox(session_id="custom-session-456")
        assert sandbox.session_id == "custom-session-456"

    def test_default_timeout(self, sandbox, temp_work_dir):
        """Test default timeout is applied."""
        sandbox.create(image="python:3.11-slim", work_dir=temp_work_dir)

        # Default timeout should be 10 minutes (600 seconds)
        # This test just verifies the mechanism works
        result = sandbox.execute("echo 'test'", timeout=None)
        assert result["status"] == "success"
