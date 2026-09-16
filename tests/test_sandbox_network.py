"""
Tests for Network Isolation and Whitelist implementation.
Following TDD: Write tests first, then implement.

Tests verify:
- NetworkManager configuration
- Whitelist domain access (allowed)
- Non-whitelist domain blocking
- Network logging of all requests
- Network timeout mechanisms
"""

import pytest
import time
from datetime import datetime
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
def network_manager():
    """Create a NetworkManager instance for testing."""
    from swe_agent.sandbox.network import NetworkManager

    manager = NetworkManager(session_id="test-network-session")
    yield manager

    # Cleanup: destroy network if it exists
    try:
        manager.cleanup()
    except Exception:
        pass


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create a temporary directory for network logs."""
    log_dir = tmp_path / "network_logs"
    log_dir.mkdir()
    return str(log_dir)


class TestNetworkManagerCreation:
    """Test NetworkManager initialization and configuration."""

    def test_create_network_manager(self, network_manager):
        """Test basic NetworkManager creation."""
        assert network_manager is not None
        assert network_manager.session_id == "test-network-session"

    def test_network_manager_has_whitelist(self, network_manager):
        """Test NetworkManager contains domain whitelist."""
        whitelist = network_manager.get_whitelist()

        assert isinstance(whitelist, list)
        assert len(whitelist) > 0

        # Verify all required domains are in whitelist
        assert "pypi.org" in whitelist
        assert "files.pythonhosted.org" in whitelist
        assert "npmjs.com" in whitelist
        assert "registry.npmjs.org" in whitelist
        assert "maven.org" in whitelist
        assert "repo.maven.apache.org" in whitelist
        assert "crates.io" in whitelist
        assert "static.crates.io" in whitelist
        assert "github.com" in whitelist

    def test_network_manager_default_timeout(self, network_manager):
        """Test NetworkManager has default timeout configuration."""
        timeout = network_manager.get_timeout()
        assert timeout > 0
        assert timeout <= 300  # Should be reasonable (e.g., 30-60 seconds)

    def test_network_manager_custom_timeout(self):
        """Test creating NetworkManager with custom timeout."""
        from swe_agent.sandbox.network import NetworkManager

        manager = NetworkManager(session_id="test-timeout", timeout=90)
        assert manager.get_timeout() == 90


class TestWhitelistValidation:
    """Test domain whitelist validation logic."""

    def test_is_domain_whitelisted_exact_match(self, network_manager):
        """Test exact domain match in whitelist."""
        assert network_manager.is_whitelisted("pypi.org") is True
        assert network_manager.is_whitelisted("github.com") is True
        assert network_manager.is_whitelisted("crates.io") is True

    def test_is_domain_whitelisted_subdomain(self, network_manager):
        """Test subdomain matching for whitelisted domains."""
        # Subdomains of whitelisted domains should be allowed
        assert network_manager.is_whitelisted("www.pypi.org") is True
        assert network_manager.is_whitelisted("api.github.com") is True

    def test_is_domain_not_whitelisted(self, network_manager):
        """Test non-whitelisted domains are rejected."""
        assert network_manager.is_whitelisted("example.com") is False
        assert network_manager.is_whitelisted("malicious.com") is False
        assert network_manager.is_whitelisted("google.com") is False

    def test_is_url_whitelisted(self, network_manager):
        """Test URL validation extracts domain correctly."""
        assert network_manager.is_url_whitelisted("https://pypi.org/simple/") is True
        assert network_manager.is_url_whitelisted("https://github.com/user/repo") is True
        assert network_manager.is_url_whitelisted("http://example.com") is False

    def test_whitelist_case_insensitive(self, network_manager):
        """Test domain matching is case-insensitive."""
        assert network_manager.is_whitelisted("PYPI.ORG") is True
        assert network_manager.is_whitelisted("GitHub.COM") is True


class TestNetworkLogging:
    """Test network access logging."""

    def test_log_network_request_allowed(self, network_manager, temp_log_dir):
        """Test logging of allowed network requests."""
        network_manager.set_log_dir(temp_log_dir)

        network_manager.log_request(
            domain="pypi.org",
            url="https://pypi.org/simple/",
            allowed=True,
            timestamp=datetime.utcnow()
        )

        # Check log file exists
        log_files = list(Path(temp_log_dir).glob("*.log"))
        assert len(log_files) > 0

        # Verify log content
        log_content = log_files[0].read_text()
        assert "pypi.org" in log_content
        assert "allowed" in log_content.lower() or "true" in log_content.lower()

    def test_log_network_request_blocked(self, network_manager, temp_log_dir):
        """Test logging of blocked network requests."""
        network_manager.set_log_dir(temp_log_dir)

        network_manager.log_request(
            domain="example.com",
            url="http://example.com",
            allowed=False,
            timestamp=datetime.utcnow()
        )

        # Check log file exists
        log_files = list(Path(temp_log_dir).glob("*.log"))
        assert len(log_files) > 0

        # Verify log content
        log_content = log_files[0].read_text()
        assert "example.com" in log_content
        assert "blocked" in log_content.lower() or "false" in log_content.lower()

    def test_log_includes_timestamp(self, network_manager, temp_log_dir):
        """Test network logs include timestamp."""
        network_manager.set_log_dir(temp_log_dir)

        timestamp = datetime.utcnow()
        network_manager.log_request(
            domain="pypi.org",
            url="https://pypi.org",
            allowed=True,
            timestamp=timestamp
        )

        log_files = list(Path(temp_log_dir).glob("*.log"))
        log_content = log_files[0].read_text()

        # Should contain timestamp information
        assert str(timestamp.year) in log_content

    def test_log_includes_session_id(self, network_manager, temp_log_dir):
        """Test network logs include session ID."""
        network_manager.set_log_dir(temp_log_dir)

        network_manager.log_request(
            domain="pypi.org",
            url="https://pypi.org",
            allowed=True,
            timestamp=datetime.utcnow()
        )

        log_files = list(Path(temp_log_dir).glob("*.log"))
        log_content = log_files[0].read_text()

        assert "test-network-session" in log_content

    def test_multiple_log_entries(self, network_manager, temp_log_dir):
        """Test multiple network requests are logged."""
        network_manager.set_log_dir(temp_log_dir)

        # Log multiple requests
        domains = ["pypi.org", "github.com", "example.com"]
        for domain in domains:
            network_manager.log_request(
                domain=domain,
                url=f"https://{domain}",
                allowed=network_manager.is_whitelisted(domain),
                timestamp=datetime.utcnow()
            )

        log_files = list(Path(temp_log_dir).glob("*.log"))
        log_content = log_files[0].read_text()

        # All domains should be logged
        for domain in domains:
            assert domain in log_content


class TestDockerNetworkIntegration:
    """Test NetworkManager integration with Docker."""

    def test_create_docker_network_with_isolation(self, network_manager, docker_client):
        """Test creating isolated Docker network."""
        network_id = network_manager.create_docker_network()

        assert network_id is not None
        assert len(network_id) > 0

        # Verify network exists
        network = docker_client.networks.get(network_id)
        assert network is not None

        # Cleanup
        network_manager.cleanup()

    def test_docker_network_naming(self, network_manager, docker_client):
        """Test Docker network follows naming convention."""
        network_id = network_manager.create_docker_network()

        network = docker_client.networks.get(network_id)
        network_name = network.name

        assert "swe-agent" in network_name
        assert "test-network-session" in network_name

        # Cleanup
        network_manager.cleanup()

    def test_docker_network_labels(self, network_manager, docker_client):
        """Test Docker network has proper labels."""
        network_id = network_manager.create_docker_network()

        network = docker_client.networks.get(network_id)
        labels = network.attrs.get("Labels", {})

        assert "swe-agent.session" in labels
        assert labels["swe-agent.session"] == "test-network-session"

        # Cleanup
        network_manager.cleanup()

    def test_cleanup_docker_network(self, network_manager, docker_client):
        """Test cleaning up Docker network."""
        network_id = network_manager.create_docker_network()

        # Verify network exists
        network = docker_client.networks.get(network_id)
        assert network is not None

        # Cleanup
        network_manager.cleanup()

        # Verify network is removed
        with pytest.raises(NotFound):
            docker_client.networks.get(network_id)


class TestNetworkTimeout:
    """Test network timeout mechanisms."""

    def test_timeout_configuration(self, network_manager):
        """Test timeout can be configured."""
        network_manager.set_timeout(45)
        assert network_manager.get_timeout() == 45

    def test_timeout_validation(self, network_manager):
        """Test timeout validation (must be positive)."""
        with pytest.raises(ValueError):
            network_manager.set_timeout(-10)

        with pytest.raises(ValueError):
            network_manager.set_timeout(0)

    def test_get_network_config_includes_timeout(self, network_manager):
        """Test network configuration includes timeout setting."""
        config = network_manager.get_network_config()

        assert "timeout" in config
        assert config["timeout"] > 0


class TestNetworkPolicyEnforcement:
    """Test network policy enforcement in containers."""

    def test_generate_hosts_file_content(self, network_manager):
        """Test generating /etc/hosts content for whitelist."""
        hosts_content = network_manager.generate_hosts_file()

        assert hosts_content is not None
        assert isinstance(hosts_content, str)
        assert "127.0.0.1" in hosts_content or "localhost" in hosts_content

    def test_generate_network_config_for_container(self, network_manager):
        """Test generating network configuration for container."""
        config = network_manager.get_container_network_config()

        assert isinstance(config, dict)
        assert "network_mode" in config or "network" in config

    def test_get_whitelist_env_vars(self, network_manager):
        """Test getting environment variables for proxy/whitelist."""
        env_vars = network_manager.get_env_vars()

        assert isinstance(env_vars, dict)
        # May include proxy settings or whitelist info


class TestNetworkManagerErrorHandling:
    """Test error handling in NetworkManager."""

    def test_create_network_idempotent(self, network_manager):
        """Test creating network multiple times is safe."""
        network_id1 = network_manager.create_docker_network()
        network_id2 = network_manager.create_docker_network()

        # Should return same network or handle gracefully
        assert network_id1 is not None
        assert network_id2 is not None

        # Cleanup
        network_manager.cleanup()

    def test_cleanup_nonexistent_network(self, network_manager):
        """Test cleaning up non-existent network doesn't raise error."""
        # Should not raise exception
        network_manager.cleanup()

    def test_log_request_without_log_dir(self, network_manager):
        """Test logging request without setting log directory."""
        # Should handle gracefully (use default or skip)
        try:
            network_manager.log_request(
                domain="pypi.org",
                url="https://pypi.org",
                allowed=True,
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            pytest.fail(f"Should handle missing log_dir gracefully: {e}")


class TestNetworkStatistics:
    """Test network usage statistics."""

    def test_get_network_stats(self, network_manager, temp_log_dir):
        """Test getting network usage statistics."""
        network_manager.set_log_dir(temp_log_dir)

        # Log some requests
        network_manager.log_request("pypi.org", "https://pypi.org", True, datetime.utcnow())
        network_manager.log_request("example.com", "http://example.com", False, datetime.utcnow())
        network_manager.log_request("github.com", "https://github.com", True, datetime.utcnow())

        stats = network_manager.get_stats()

        assert isinstance(stats, dict)
        assert "total_requests" in stats
        assert "allowed_requests" in stats
        assert "blocked_requests" in stats
        assert stats["total_requests"] == 3
        assert stats["allowed_requests"] == 2
        assert stats["blocked_requests"] == 1
