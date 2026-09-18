"""
Snapshot and rollback mechanism for Docker containers.

Provides snapshot creation, restoration, and Git backup functionality.
"""

import subprocess
import time
import tempfile
import io
import tarfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import docker
from docker.errors import ImageNotFound, APIError
import structlog

logger = structlog.get_logger(__name__)


class SnapshotManager:
    """
    Manages container snapshots and Git backups for rollback capability.

    Features:
    - Docker container snapshots using docker commit
    - Git stash backups for host filesystem
    - Automatic snapshot limit enforcement (max 5 per session)
    - Storage space tracking and limits (max 5GB total)
    - Auto-rollback triggers
    """

    # Configuration
    MAX_SNAPSHOTS_PER_SESSION = 5
    MAX_TOTAL_SIZE_BYTES = 5 * 1024 * 1024 * 1024  # 5GB

    def __init__(self, sandbox):
        """
        Initialize SnapshotManager.

        Args:
            sandbox: DockerSandbox instance to manage snapshots for

        Raises:
            ValueError: If sandbox is None
        """
        if sandbox is None:
            raise ValueError("Sandbox cannot be None")

        self.sandbox = sandbox
        self.session_id = sandbox.session_id
        self.snapshots: List[Dict[str, Any]] = []
        self._archives = tempfile.TemporaryDirectory(prefix="swe-snapshots-")

        try:
            self.docker_client = sandbox.client
        except Exception as e:
            logger.error("docker_client_init_failed", error=str(e))
            raise

    def create_snapshot(self, tag: Optional[str] = None) -> str:
        """
        Create a snapshot of the current container state.

        Args:
            tag: Optional tag for the snapshot

        Returns:
            Snapshot ID (Docker image ID)

        Raises:
            RuntimeError: If container is not created
            Exception: If snapshot creation fails
        """
        if not self.sandbox.container_id:
            raise RuntimeError("Container not created. Cannot create snapshot.")

        try:
            # Generate snapshot name
            timestamp = int(time.time() * 1000)
            snapshot_name = f"swe-agent-snapshot-{self.session_id}-{timestamp}"

            # Get container
            container = self.docker_client.containers.get(self.sandbox.container_id)
            # docker commit excludes bind mounts and tmpfs. Archive writable data explicitly.
            archive_path = Path(self._archives.name) / f"{snapshot_name}.tar"
            archive = container.exec_run(["tar", "-C", "/", "-cf", "-", "tmp", "workspace"])
            if archive.exit_code:
                raise RuntimeError("Could not archive sandbox writable directories")
            with tarfile.open(fileobj=io.BytesIO(archive.output)) as source_tar:
                with tarfile.open(archive_path, "w") as target_tar:
                    for member in source_tar:
                        if member.name.rstrip("/") in {"tmp", "workspace"}:
                            continue
                        target_tar.addfile(
                            member, source_tar.extractfile(member) if member.isfile() else None
                        )

            # Commit container to create snapshot image
            image = container.commit(
                repository=snapshot_name, tag="latest", message=f"Snapshot: {tag or 'auto'}"
            )

            snapshot_id = image.id

            # Get image size
            image_obj = self.docker_client.images.get(snapshot_id)
            size = image_obj.attrs.get("Size", 0)

            # Record snapshot metadata
            snapshot_info = {
                "id": snapshot_id,
                "name": snapshot_name,
                "tag": tag or "auto",
                "created_at": datetime.utcnow().isoformat(),
                "container_id": self.sandbox.container_id,
                "size": size,
                "archive": str(archive_path),
            }

            self.snapshots.append(snapshot_info)

            logger.info(
                "snapshot_created",
                snapshot_id=snapshot_id,
                snapshot_name=snapshot_name,
                tag=tag,
                session_id=self.session_id,
            )

            # Enforce snapshot limit
            self._enforce_snapshot_limit()

            return snapshot_id

        except Exception as e:
            logger.error(
                "snapshot_creation_failed",
                error=str(e),
                session_id=self.session_id,
            )
            raise

    def restore_snapshot(self, snapshot_id: str) -> None:
        """
        Restore container to a previous snapshot state.

        Args:
            snapshot_id: ID of the snapshot to restore

        Raises:
            ValueError: If snapshot doesn't exist
            RuntimeError: If container is not created
        """
        if not self.sandbox.container_id:
            raise RuntimeError("Container not created. Cannot restore snapshot.")

        # Find snapshot
        snapshot_info = self.get_snapshot_info(snapshot_id)
        if not snapshot_info:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        try:
            # Get current container info
            old_container = self.docker_client.containers.get(self.sandbox.container_id)
            container_config = old_container.attrs

            # Extract configuration
            volumes = container_config["HostConfig"]["Binds"]
            network_name = list(container_config["NetworkSettings"]["Networks"].keys())[0]
            env = container_config["Config"]["Env"]
            working_dir = container_config["Config"]["WorkingDir"]

            # Stop and remove old container
            old_container.stop(timeout=5)
            old_container.remove(force=True)

            logger.info(
                "old_container_removed",
                container_id=self.sandbox.container_id,
                session_id=self.session_id,
            )

            # Create new container from snapshot image
            new_container = self.docker_client.containers.create(
                image=snapshot_id,
                name=f"swe-agent-{self.session_id}-restored-{int(time.time())}",
                command="tail -f /dev/null",
                detach=True,
                working_dir=working_dir,
                volumes=self._parse_volumes(volumes) if volumes else None,
                environment=env,
                network=network_name,
                # Restore resource limits
                nano_cpus=int(self.sandbox.CPU_LIMIT * 1_000_000_000),
                mem_limit=self.sandbox.MEMORY_LIMIT,
                mem_swappiness=0,
                memswap_limit=self.sandbox.MEMORY_SWAP_LIMIT,
                pids_limit=self.sandbox.PID_LIMIT,
                # Restore security settings
                read_only=True,
                tmpfs={"/tmp": f"rw,size={self.sandbox.TMPFS_SIZE}"},
                user="nobody",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                labels={
                    "swe-agent.session": self.session_id,
                    "swe-agent.created": datetime.utcnow().isoformat(),
                    "swe-agent.type": "sandbox",
                    "swe-agent.restored_from": snapshot_id,
                },
            )

            # Start new container
            new_container.start()

            # Update sandbox container_id
            self.sandbox.container_id = new_container.id
            # Reset mounted files too, including files introduced after the snapshot.
            cleanup = new_container.exec_run(
                [
                    "python",
                    "-c",
                    "import pathlib,shutil; [shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink() for d in ('/tmp','/workspace') for p in pathlib.Path(d).iterdir()]",
                ]
            )
            if cleanup.exit_code:
                raise RuntimeError("Could not clear sandbox before restoring snapshot")
            self.sandbox.copy_file(snapshot_info["archive"], "/tmp/.swe-restore.tar")
            restored = new_container.exec_run(
                [
                    "tar",
                    "--no-same-owner",
                    "--same-permissions",
                    "--no-overwrite-dir",
                    "-C",
                    "/",
                    "-xf",
                    "/tmp/.swe-restore.tar",
                ]
            )
            if restored.exit_code:
                raise RuntimeError(restored.output.decode("utf-8", errors="replace"))
            new_container.exec_run(["rm", "-f", "/tmp/.swe-restore.tar"])

            logger.info(
                "snapshot_restored",
                snapshot_id=snapshot_id,
                new_container_id=new_container.id,
                session_id=self.session_id,
            )

        except Exception as e:
            logger.error(
                "snapshot_restore_failed",
                snapshot_id=snapshot_id,
                error=str(e),
                session_id=self.session_id,
            )
            raise

    def create_git_backup(self, repo_path: str) -> Optional[str]:
        """
        Create Git stash backup of host filesystem.

        Args:
            repo_path: Path to Git repository

        Returns:
            Stash ID or None if no changes to backup
        """
        try:
            timestamp = int(time.time() * 1000)
            stash_message = f"swe-agent-backup-{timestamp}"

            # Check if there are changes to stash
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            if not result.stdout.strip():
                logger.info(
                    "git_backup_no_changes",
                    repo_path=repo_path,
                    session_id=self.session_id,
                )
                return None

            # Create stash
            result = subprocess.run(
                ["git", "stash", "save", stash_message],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            # Get stash ID (stash@{0})
            stash_id = "stash@{0}"

            logger.info(
                "git_backup_created",
                stash_id=stash_id,
                message=stash_message,
                repo_path=repo_path,
                session_id=self.session_id,
            )

            return stash_id

        except subprocess.CalledProcessError as e:
            logger.error(
                "git_backup_failed",
                error=str(e),
                stderr=e.stderr if hasattr(e, "stderr") else "",
                repo_path=repo_path,
            )
            raise
        except Exception as e:
            logger.error(
                "git_backup_error",
                error=str(e),
                repo_path=repo_path,
            )
            raise

    def restore_git_backup(self, stash_id: str, repo_path: str) -> None:
        """
        Restore Git stash backup.

        Args:
            stash_id: Stash ID to restore (e.g., "stash@{0}")
            repo_path: Path to Git repository
        """
        try:
            # Apply and remove stash
            result = subprocess.run(
                ["git", "stash", "pop", stash_id],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.info(
                "git_backup_restored",
                stash_id=stash_id,
                repo_path=repo_path,
                session_id=self.session_id,
            )

        except subprocess.CalledProcessError as e:
            logger.error(
                "git_restore_failed",
                error=str(e),
                stderr=e.stderr if hasattr(e, "stderr") else "",
                stash_id=stash_id,
            )
            raise

    def auto_rollback_trigger(self, snapshot_id: str, condition: str) -> bool:
        """
        Trigger automatic rollback based on condition.

        Args:
            snapshot_id: Snapshot to rollback to
            condition: Condition that triggered rollback (e.g., "error", "test_failure")

        Returns:
            True if rollback successful, False otherwise

        Raises:
            ValueError: If snapshot doesn't exist
        """
        logger.info(
            "auto_rollback_triggered",
            snapshot_id=snapshot_id,
            condition=condition,
            session_id=self.session_id,
        )

        try:
            if not self.get_snapshot_info(snapshot_id):
                raise ValueError(f"Snapshot not found: {snapshot_id}")
            self.restore_snapshot(snapshot_id)

            logger.info(
                "auto_rollback_success",
                snapshot_id=snapshot_id,
                condition=condition,
                session_id=self.session_id,
            )

            return True

        except Exception as e:
            logger.error(
                "auto_rollback_failed",
                snapshot_id=snapshot_id,
                condition=condition,
                error=str(e),
                session_id=self.session_id,
            )
            raise

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """
        List all snapshots for this session.

        Returns:
            List of snapshot information dictionaries
        """
        return self.snapshots.copy()

    def get_snapshot_info(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific snapshot.

        Args:
            snapshot_id: Snapshot ID

        Returns:
            Snapshot information dict or None if not found
        """
        for snapshot in self.snapshots:
            if snapshot["id"] == snapshot_id:
                return snapshot.copy()
        return None

    def find_snapshot_by_tag(self, tag: str) -> Optional[str]:
        """
        Find snapshot ID by tag.

        Args:
            tag: Tag to search for

        Returns:
            Snapshot ID or None if not found
        """
        for snapshot in self.snapshots:
            if snapshot["tag"] == tag:
                return snapshot["id"]
        return None

    def delete_snapshot(self, snapshot_id: str) -> None:
        """
        Delete a specific snapshot.

        Args:
            snapshot_id: Snapshot ID to delete
        """
        try:
            # Remove from Docker
            try:
                image = self.docker_client.images.get(snapshot_id)
                image.remove(force=True)
                logger.info("snapshot_image_removed", snapshot_id=snapshot_id)
            except ImageNotFound:
                logger.warning("snapshot_image_not_found", snapshot_id=snapshot_id)

            # Remove from tracking
            info = self.get_snapshot_info(snapshot_id)
            if info and info.get("archive"):
                Path(info["archive"]).unlink(missing_ok=True)
            self.snapshots = [s for s in self.snapshots if s["id"] != snapshot_id]

            logger.info(
                "snapshot_deleted",
                snapshot_id=snapshot_id,
                session_id=self.session_id,
            )

        except Exception as e:
            logger.error(
                "snapshot_deletion_failed",
                snapshot_id=snapshot_id,
                error=str(e),
            )

    def cleanup_all_snapshots(self) -> None:
        """
        Cleanup all snapshots for this session.
        """
        snapshot_ids = [s["id"] for s in self.snapshots]

        for snapshot_id in snapshot_ids:
            self.delete_snapshot(snapshot_id)

        logger.info(
            "all_snapshots_cleaned",
            count=len(snapshot_ids),
            session_id=self.session_id,
        )

    def get_total_snapshot_size(self) -> int:
        """
        Get total size of all snapshots in bytes.

        Returns:
            Total size in bytes
        """
        return sum(s.get("size", 0) for s in self.snapshots)

    def _enforce_snapshot_limit(self) -> None:
        """
        Enforce snapshot limits (max 5 per session, max 5GB total).

        Removes oldest snapshots if limits are exceeded.
        """
        # Enforce per-session limit (max 5)
        while len(self.snapshots) > self.MAX_SNAPSHOTS_PER_SESSION:
            oldest = self.snapshots[0]
            logger.info(
                "removing_oldest_snapshot",
                snapshot_id=oldest["id"],
                tag=oldest["tag"],
                session_id=self.session_id,
            )
            self.delete_snapshot(oldest["id"])

        # Enforce total size limit (max 5GB)
        while self.get_total_snapshot_size() > self.MAX_TOTAL_SIZE_BYTES and self.snapshots:
            oldest = self.snapshots[0]
            logger.warning(
                "removing_snapshot_size_limit",
                snapshot_id=oldest["id"],
                total_size=self.get_total_snapshot_size(),
                limit=self.MAX_TOTAL_SIZE_BYTES,
            )
            self.delete_snapshot(oldest["id"])

    def _parse_volumes(self, binds: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Parse Docker volume binds into volumes dict.

        Args:
            binds: List of bind strings (e.g., ["/host:/container:rw"])

        Returns:
            Volumes dict for Docker API
        """
        volumes = {}
        for bind in binds:
            parts = bind.rsplit(":", 2)
            if len(parts) >= 2:
                host_path = parts[0]
                container_path = parts[1]
                mode = parts[2] if len(parts) > 2 else "rw"
                volumes[host_path] = {"bind": container_path, "mode": mode}
        return volumes
