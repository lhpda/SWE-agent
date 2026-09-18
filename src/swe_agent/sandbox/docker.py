"""
Docker-based sandbox for isolated code execution.

Provides secure, resource-limited containers for running tests and commands.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Any
import docker
from docker.errors import DockerException, NotFound, APIError, ImageNotFound
import structlog

logger = structlog.get_logger(__name__)


class DockerSandbox:
    """
    Docker-based sandbox for isolated code execution.

    Features:
    - Resource limits (CPU, memory, PIDs)
    - Network isolation
    - Read-only root filesystem with tmpfs /tmp
    - Non-root user execution
    - Automatic cleanup and orphan detection
    """

    # Default configuration
    DEFAULT_TIMEOUT = 600  # 10 minutes in seconds
    MAX_LIFETIME_HOURS = 2  # Maximum container lifetime

    # Resource limits (from SYSTEM_DESIGN.md 3.7)
    CPU_LIMIT = 2.0  # 2 cores
    MEMORY_LIMIT = 4 * 1024 * 1024 * 1024  # 4GB in bytes
    MEMORY_SWAP_LIMIT = 4 * 1024 * 1024 * 1024  # Same as memory (no additional swap)
    PID_LIMIT = 1000
    TMPFS_SIZE = "1g"

    def __init__(self, session_id: str):
        """
        Initialize DockerSandbox.

        Args:
            session_id: Unique identifier for this session
        """
        self.session_id = session_id
        self.container_id: Optional[str] = None
        self.network_id: Optional[str] = None
        self.created_at: Optional[datetime] = None

        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            logger.error("docker_client_init_failed", error=str(e))
            raise DockerException(f"Failed to connect to Docker daemon: {e}")

    def create(self, image: str, work_dir: str, env: Optional[Dict[str, str]] = None) -> str:
        """
        Create a new Docker container with resource limits and security settings.

        Args:
            image: Docker image to use (e.g., "python:3.11-slim")
            work_dir: Host directory to mount as working directory
            env: Optional environment variables

        Returns:
            Container ID

        Raises:
            DockerException: If container creation fails
        """
        if self.container_id:
            logger.warning("container_already_exists", session_id=self.session_id)
            return self.container_id

        try:
            # Pull image if not present
            try:
                self.client.images.get(image)
            except ImageNotFound:
                logger.info("pulling_image", image=image)
                self.client.images.pull(image)

            # Create custom isolated network
            network_name = f"swe-agent-net-{self.session_id}"
            try:
                network = self.client.networks.create(
                    name=network_name,
                    driver="bridge",
                    internal=True,
                    labels={
                        "swe-agent.session": self.session_id,
                        "swe-agent.created": datetime.utcnow().isoformat(),
                    },
                )
                self.network_id = network.id
                logger.info("network_created", network_id=self.network_id, name=network_name)
            except APIError as e:
                if "already exists" in str(e):
                    network = self.client.networks.get(network_name)
                    self.network_id = network.id
                else:
                    raise

            # Container name
            container_name = f"swe-agent-{self.session_id}"

            # Prepare volumes
            volumes = {work_dir: {"bind": "/workspace", "mode": "rw"}}

            # Prepare environment variables
            container_env = dict(env or {})
            container_env.setdefault("HOME", "/tmp")
            container_env.setdefault("PYTHONUSERBASE", "/tmp/python-user")
            container_env.setdefault("PIP_USER", "1")
            container_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
            container_env["SWE_AGENT_SESSION"] = self.session_id

            # Create container with resource limits and security settings
            container = self.client.containers.create(
                image=image,
                name=container_name,
                command="tail -f /dev/null",  # Keep container running
                detach=True,
                working_dir="/workspace",
                volumes=volumes,
                environment=container_env,
                network=network_name,
                # Resource limits
                nano_cpus=int(self.CPU_LIMIT * 1_000_000_000),  # Convert to nanocpus
                mem_limit=self.MEMORY_LIMIT,
                mem_swappiness=0,
                memswap_limit=self.MEMORY_SWAP_LIMIT,
                pids_limit=self.PID_LIMIT,
                # Security settings
                read_only=True,  # Read-only root filesystem
                tmpfs={
                    "/tmp": f"rw,size={self.TMPFS_SIZE}",  # Writable /tmp with size limit
                },
                user="nobody",  # Run as non-root user
                cap_drop=["ALL"],  # Drop all capabilities
                security_opt=["no-new-privileges"],  # Prevent privilege escalation
                # Labels for identification and cleanup
                labels={
                    "swe-agent.session": self.session_id,
                    "swe-agent.created": datetime.utcnow().isoformat(),
                    "swe-agent.type": "sandbox",
                },
            )

            # Start the container
            self.container_id = container.id
            container.start()
            self.created_at = datetime.utcnow()

            logger.info(
                "container_created",
                container_id=self.container_id,
                session_id=self.session_id,
                image=image,
            )

            return self.container_id

        except Exception as e:
            logger.error("container_creation_failed", error=str(e), session_id=self.session_id)
            # Cleanup on failure
            self.destroy()
            self._cleanup_network()
            raise

    def execute(self, command: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute a command in the container.

        Args:
            command: Command to execute
            timeout: Timeout in seconds (default: 600)

        Returns:
            Dictionary with keys:
                - status: "success", "error", or "timeout"
                - stdout: Command output
                - stderr: Error output
                - exit_code: Exit code
                - execution_time: Time taken in seconds

        Raises:
            RuntimeError: If container is not created
        """
        if not self.container_id:
            raise RuntimeError("Container not created. Call create() first.")

        timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT

        start_time = time.time()

        try:
            container = self.client.containers.get(self.container_id)

            # Execute command with timeout
            import shlex

            exec_result = container.exec_run(
                cmd=[
                    "sh",
                    "-c",
                    f"timeout --signal=TERM --kill-after=2s {timeout}s sh -c {shlex.quote(command)}",
                ],
                demux=True,
                environment=None,
            )

            execution_time = time.time() - start_time

            # Check if execution exceeded timeout (approximate check)
            if exec_result.exit_code in (124, 137) or execution_time > timeout:
                logger.warning(
                    "command_timeout",
                    session_id=self.session_id,
                    command=command[:100],
                    timeout=timeout,
                )
                return {
                    "status": "timeout",
                    "stdout": "",
                    "stderr": f"Command exceeded timeout of {timeout}s",
                    "exit_code": -1,
                    "execution_time": execution_time,
                }

            exit_code = exec_result.exit_code

            # Parse stdout and stderr
            stdout_bytes, stderr_bytes = exec_result.output
            stdout = stdout_bytes.decode("utf-8") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8") if stderr_bytes else ""

            status = "success" if exit_code == 0 else "error"

            logger.debug(
                "command_executed",
                session_id=self.session_id,
                status=status,
                exit_code=exit_code,
                execution_time=execution_time,
            )

            return {
                "status": status,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": execution_time,
            }

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "command_execution_failed",
                session_id=self.session_id,
                error=str(e),
                command=command[:100],
            )
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "execution_time": execution_time,
            }

    def copy_file(self, src: str, dst: str) -> None:
        """
        Copy file between host and container.

        Args:
            src: Source path (host or container path)
            dst: Destination path (container or host path)

        The method automatically detects direction based on path format:
        - If src starts with "/", assumes container -> host
        - Otherwise, assumes host -> container

        Raises:
            RuntimeError: If container is not created
        """
        if not self.container_id:
            raise RuntimeError("Container not created. Call create() first.")

        try:
            container = self.client.containers.get(self.container_id)

            src_path = Path(src)

            # Determine copy direction
            if src.startswith("/") and not src_path.exists():
                # Container -> Host
                self._copy_from_container(container, src, dst)
            else:
                # Host -> Container
                self._copy_to_container(container, src, dst)

        except Exception as e:
            logger.error(
                "file_copy_failed", session_id=self.session_id, src=src, dst=dst, error=str(e)
            )
            raise

    def _copy_to_container(self, container, src: str, dst: str) -> None:
        """Copy file from host to container."""
        import base64

        src_path = Path(src)
        if not src_path.exists():
            raise FileNotFoundError(f"Source file not found: {src}")

        # exec sees mounted tmpfs; Docker archive APIs may only see the underlying rootfs.
        result = container.exec_run(
            [
                "python",
                "-c",
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b'')",
                dst,
            ]
        )
        if result.exit_code:
            raise RuntimeError(result.output.decode("utf-8", errors="replace"))
        with src_path.open("rb") as stream:
            while chunk := stream.read(32768):
                result = container.exec_run(
                    [
                        "python",
                        "-c",
                        "import base64,sys; open(sys.argv[1],'ab').write(base64.b64decode(sys.argv[2]))",
                        dst,
                        base64.b64encode(chunk).decode("ascii"),
                    ]
                )
                if result.exit_code:
                    raise RuntimeError(result.output.decode("utf-8", errors="replace"))

        logger.debug("file_copied_to_container", src=src, dst=dst)

    def _copy_from_container(self, container, src: str, dst: str) -> None:
        """Copy file from container to host."""
        result = container.exec_run(
            [
                "python",
                "-c",
                "import pathlib,sys; sys.stdout.buffer.write(pathlib.Path(sys.argv[1]).read_bytes())",
                src,
            ]
        )
        if result.exit_code:
            raise RuntimeError(result.output.decode("utf-8", errors="replace"))
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_bytes(result.output)

        logger.debug("file_copied_from_container", src=src, dst=dst)

    def destroy(self) -> None:
        """
        Destroy the container and cleanup resources.

        This method is idempotent and safe to call multiple times.
        """
        if not self.container_id:
            return

        try:
            container = self.client.containers.get(self.container_id)
            container.stop(timeout=5)
            container.remove(force=True)

            logger.info(
                "container_destroyed", container_id=self.container_id, session_id=self.session_id
            )
        except NotFound:
            logger.debug("container_not_found", container_id=self.container_id)
        except Exception as e:
            logger.error(
                "container_destruction_failed", container_id=self.container_id, error=str(e)
            )
        finally:
            self.container_id = None
            self._cleanup_network()

    def _cleanup_network(self) -> None:
        """Cleanup the custom network."""
        if not self.network_id:
            return

        try:
            network = self.client.networks.get(self.network_id)
            network.remove()
            logger.debug("network_removed", network_id=self.network_id)
        except NotFound:
            pass
        except Exception as e:
            logger.warning("network_cleanup_failed", network_id=self.network_id, error=str(e))
        finally:
            self.network_id = None

    @classmethod
    def find_orphan_containers(cls, max_age_hours: float = 2.0) -> List[str]:
        """
        Find orphaned swe-agent containers older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            List of orphan container IDs
        """
        try:
            client = docker.from_env()
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)

            orphans = []

            # Find all swe-agent containers
            containers = client.containers.list(
                all=True, filters={"label": "swe-agent.type=sandbox"}
            )

            for container in containers:
                try:
                    created_str = container.labels.get("swe-agent.created")
                    if created_str:
                        created_time = datetime.fromisoformat(created_str)
                        if created_time < cutoff_time:
                            orphans.append(container.id)
                except Exception as e:
                    logger.warning("orphan_check_failed", container_id=container.id, error=str(e))

            return orphans

        except Exception as e:
            logger.error("orphan_detection_failed", error=str(e))
            return []

    @classmethod
    def cleanup_orphan_containers(cls, max_age_hours: float = 2.0) -> int:
        """
        Cleanup orphaned containers older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of containers cleaned up
        """
        orphans = cls.find_orphan_containers(max_age_hours)

        if not orphans:
            return 0

        client = docker.from_env()
        cleaned = 0

        for container_id in orphans:
            try:
                container = client.containers.get(container_id)
                session_id = container.labels.get("swe-agent.session", "unknown")

                container.stop(timeout=5)
                container.remove(force=True)

                cleaned += 1
                logger.info(
                    "orphan_container_cleaned", container_id=container_id, session_id=session_id
                )

            except Exception as e:
                logger.error("orphan_cleanup_failed", container_id=container_id, error=str(e))

        return cleaned
