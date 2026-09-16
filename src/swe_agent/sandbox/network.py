"""
Network isolation and whitelist management for Docker containers.

Implements domain-based whitelist for package managers and dependency sources,
with network access logging and timeout configuration.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
import docker
from docker.errors import NotFound, APIError
import structlog
import json

logger = structlog.get_logger(__name__)


class NetworkManager:
    """
    Manages network isolation and whitelist for Docker containers.

    Features:
    - Domain whitelist for package managers (Python, Node.js, Java, Rust)
    - Network access logging
    - Timeout configuration
    - Docker network creation and management
    """

    # Domain whitelist (from SYSTEM_DESIGN.md 3.7)
    WHITELIST_DOMAINS = [
        # Python
        "pypi.org",
        "files.pythonhosted.org",
        # Node.js
        "npmjs.com",
        "registry.npmjs.org",
        # Java
        "maven.org",
        "repo.maven.apache.org",
        # Rust
        "crates.io",
        "static.crates.io",
        # GitHub (for git clone dependencies)
        "github.com",
    ]

    # Default timeout for network operations (seconds)
    DEFAULT_TIMEOUT = 30

    def __init__(self, session_id: str, timeout: Optional[int] = None):
        """
        Initialize NetworkManager.

        Args:
            session_id: Unique identifier for this session
            timeout: Network timeout in seconds (default: 30)
        """
        self.session_id = session_id
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self.network_id: Optional[str] = None
        self._log_dir: Optional[str] = None
        self._request_log: List[Dict[str, Any]] = []

        try:
            self.client = docker.from_env()
        except Exception as e:
            logger.error("docker_client_init_failed", error=str(e))
            raise

    def get_whitelist(self) -> List[str]:
        """
        Get the list of whitelisted domains.

        Returns:
            List of whitelisted domain names
        """
        return self.WHITELIST_DOMAINS.copy()

    def is_whitelisted(self, domain: str) -> bool:
        """
        Check if a domain is whitelisted.

        Args:
            domain: Domain name to check (e.g., "pypi.org" or "www.pypi.org")

        Returns:
            True if domain or its parent domain is whitelisted
        """
        domain_lower = domain.lower().strip()

        # Check exact match
        if domain_lower in self.WHITELIST_DOMAINS:
            return True

        # Check if it's a subdomain of a whitelisted domain
        for whitelisted in self.WHITELIST_DOMAINS:
            if domain_lower.endswith(f".{whitelisted}") or domain_lower == whitelisted:
                return True

        return False

    def is_url_whitelisted(self, url: str) -> bool:
        """
        Check if a URL's domain is whitelisted.

        Args:
            url: Full URL to check

        Returns:
            True if the URL's domain is whitelisted
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split("/")[0]
            # Remove port if present
            domain = domain.split(":")[0]
            return self.is_whitelisted(domain)
        except Exception as e:
            logger.warning("url_parse_failed", url=url, error=str(e))
            return False

    def get_timeout(self) -> int:
        """
        Get the configured network timeout.

        Returns:
            Timeout in seconds
        """
        return self._timeout

    def set_timeout(self, timeout: int) -> None:
        """
        Set the network timeout.

        Args:
            timeout: Timeout in seconds (must be positive)

        Raises:
            ValueError: If timeout is not positive
        """
        if timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {timeout}")

        self._timeout = timeout
        logger.debug("timeout_updated", session_id=self.session_id, timeout=timeout)

    def set_log_dir(self, log_dir: str) -> None:
        """
        Set the directory for network access logs.

        Args:
            log_dir: Path to log directory
        """
        self._log_dir = log_dir
        Path(log_dir).mkdir(parents=True, exist_ok=True)

    def log_request(
        self,
        domain: str,
        url: str,
        allowed: bool,
        timestamp: datetime,
    ) -> None:
        """
        Log a network request.

        Args:
            domain: Domain being accessed
            url: Full URL
            allowed: Whether the request was allowed
            timestamp: Request timestamp
        """
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "session_id": self.session_id,
            "domain": domain,
            "url": url,
            "allowed": allowed,
        }

        # Add to in-memory log
        self._request_log.append(log_entry)

        # Write to file if log directory is set
        if self._log_dir:
            log_file = Path(self._log_dir) / f"network_{self.session_id}.log"
            try:
                with open(log_file, "a") as f:
                    f.write(json.dumps(log_entry) + "\n")
            except Exception as e:
                logger.error("log_write_failed", error=str(e), session_id=self.session_id)

        logger.debug(
            "network_request_logged",
            session_id=self.session_id,
            domain=domain,
            allowed=allowed,
        )

    def create_docker_network(self) -> str:
        """
        Create an isolated Docker network for this session.

        Returns:
            Network ID

        Raises:
            APIError: If network creation fails
        """
        if self.network_id:
            logger.debug("network_already_exists", network_id=self.network_id)
            return self.network_id

        network_name = f"swe-agent-net-{self.session_id}"

        try:
            network = self.client.networks.create(
                name=network_name,
                driver="bridge",
                internal=False,  # Allow outbound, restrict via application-level filtering
                labels={
                    "swe-agent.session": self.session_id,
                    "swe-agent.created": datetime.utcnow().isoformat(),
                    "swe-agent.type": "isolated",
                },
            )
            self.network_id = network.id

            logger.info(
                "network_created",
                network_id=self.network_id,
                session_id=self.session_id,
                name=network_name,
            )

            return self.network_id

        except APIError as e:
            if "already exists" in str(e):
                # Network already exists, get it
                network = self.client.networks.get(network_name)
                self.network_id = network.id
                logger.debug("network_already_existed", network_id=self.network_id)
                return self.network_id
            else:
                logger.error("network_creation_failed", error=str(e), session_id=self.session_id)
                raise

    def cleanup(self) -> None:
        """
        Clean up the Docker network.

        This method is idempotent and safe to call multiple times.
        """
        if not self.network_id:
            return

        try:
            network = self.client.networks.get(self.network_id)
            network.remove()

            logger.info("network_removed", network_id=self.network_id, session_id=self.session_id)
        except NotFound:
            logger.debug("network_not_found", network_id=self.network_id)
        except Exception as e:
            logger.warning(
                "network_cleanup_failed",
                network_id=self.network_id,
                error=str(e),
            )
        finally:
            self.network_id = None

    def get_network_config(self) -> Dict[str, Any]:
        """
        Get the network configuration as a dictionary.

        Returns:
            Network configuration dictionary
        """
        return {
            "session_id": self.session_id,
            "timeout": self._timeout,
            "whitelist": self.WHITELIST_DOMAINS.copy(),
            "network_id": self.network_id,
        }

    def get_container_network_config(self) -> Dict[str, Any]:
        """
        Get Docker container network configuration.

        Returns:
            Dictionary suitable for Docker container creation
        """
        config = {}

        if self.network_id:
            config["network"] = self.network_id
        else:
            # Network will be attached later
            config["network_mode"] = "bridge"

        return config

    def get_env_vars(self) -> Dict[str, str]:
        """
        Get environment variables for network configuration.

        Returns:
            Dictionary of environment variables
        """
        env_vars = {
            "SWE_AGENT_NETWORK_TIMEOUT": str(self._timeout),
            "SWE_AGENT_WHITELIST": ",".join(self.WHITELIST_DOMAINS),
        }

        return env_vars

    def generate_hosts_file(self) -> str:
        """
        Generate /etc/hosts file content for network isolation.

        Returns:
            Contents for /etc/hosts file
        """
        hosts_content = "# Generated by SWE Agent NetworkManager\n"
        hosts_content += "127.0.0.1 localhost\n"
        hosts_content += "::1 localhost ip6-localhost ip6-loopback\n"
        hosts_content += "\n"
        hosts_content += "# Whitelisted domains (resolved normally)\n"
        for domain in self.WHITELIST_DOMAINS:
            hosts_content += f"# {domain} - allowed\n"

        return hosts_content

    def get_stats(self) -> Dict[str, int]:
        """
        Get network usage statistics.

        Returns:
            Dictionary with request statistics
        """
        total = len(self._request_log)
        allowed = sum(1 for entry in self._request_log if entry["allowed"])
        blocked = total - allowed

        return {
            "total_requests": total,
            "allowed_requests": allowed,
            "blocked_requests": blocked,
        }
