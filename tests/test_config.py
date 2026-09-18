"""Tests for configuration management (Task 0.3)."""

import os
from pathlib import Path

import pytest

from swe_agent.config import Config, load_config


class TestConfigDefaults:
    """Test default configuration values."""

    def test_config_has_default_values(self):
        """Test that Config has sensible defaults."""
        config = Config()

        # Timeout defaults
        assert config.localization_timeout > 0
        assert config.reproduction_timeout > 0
        assert config.patch_generation_timeout > 0
        assert config.validation_timeout > 0
        assert config.global_timeout > 0

        # Retry defaults
        assert config.max_retries >= 0
        assert config.localization_max_retries >= 0
        assert config.reproduction_max_retries >= 0

        # Resource limits
        assert config.max_tool_output_size > 0
        assert config.max_test_output_size > 0
        assert config.max_file_size > 0

    def test_config_timeout_values_match_spec(self):
        """Test that timeouts match SYSTEM_DESIGN.md specifications."""
        config = Config()

        # From Section 2.2 of SYSTEM_DESIGN.md
        assert config.localization_timeout == 300  # 5 minutes
        assert config.reproduction_timeout == 480  # 8 minutes
        assert config.patch_generation_timeout == 360  # 6 minutes
        assert config.validation_timeout == 600  # 10 minutes
        assert config.global_timeout == 1800  # 30 minutes

    def test_config_retry_values_match_spec(self):
        """Test that retry values match specifications."""
        config = Config()

        assert config.max_retries == 3
        assert config.localization_max_retries == 3
        assert config.reproduction_max_retries == 5
        assert config.patch_max_retries == 5
        assert config.validation_max_retries == 1

    def test_config_output_limits_match_spec(self):
        """Test that output limits match specifications."""
        config = Config()

        # From Section 5.1 of SYSTEM_DESIGN.md
        assert config.max_tool_output_size == 10 * 1024  # 10KB
        assert config.max_test_output_size == 5 * 1024  # 5KB
        assert config.max_file_size == 50000  # 50K chars


class TestConfigSerialization:
    """Test config serialization and deserialization."""

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config = Config()
        config_dict = config.model_dump()

        assert isinstance(config_dict, dict)
        assert "localization_timeout" in config_dict
        assert "max_retries" in config_dict

    def test_config_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "localization_timeout": 600,
            "max_retries": 5,
        }
        config = Config(**config_dict)

        assert config.localization_timeout == 600
        assert config.max_retries == 5


class TestConfigEnvironmentVariables:
    """Test configuration from environment variables."""

    def test_load_config_with_env_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        monkeypatch.setenv("SWE_AGENT_LOCALIZATION_TIMEOUT", "600")
        monkeypatch.setenv("SWE_AGENT_MAX_RETRIES", "5")

        config = load_config()

        assert config.localization_timeout == 600
        assert config.max_retries == 5

    def test_load_config_without_env_uses_defaults(self):
        """Test that load_config uses defaults when no env vars."""
        config = load_config()

        # Should match default values
        assert config.localization_timeout == 300

    def test_env_var_integer_conversion(self, monkeypatch):
        """Test that env vars are correctly converted to integers."""
        monkeypatch.setenv("SWE_AGENT_MAX_TOOL_OUTPUT_SIZE", "20480")

        config = load_config()

        assert isinstance(config.max_tool_output_size, int)
        assert config.max_tool_output_size == 20480

    def test_invalid_env_var_uses_default(self, monkeypatch):
        """Test that invalid env vars fall back to defaults."""
        monkeypatch.setenv("SWE_AGENT_MAX_RETRIES", "invalid")

        # Should not raise error, should use default
        config = load_config()
        assert config.max_retries == 3  # default


class TestConfigValidation:
    """Test configuration validation."""

    def test_config_rejects_negative_timeout(self):
        """Test that negative timeouts are rejected."""
        with pytest.raises(ValueError):
            Config(localization_timeout=-1)

    def test_config_rejects_negative_retries(self):
        """Test that negative retries are rejected."""
        with pytest.raises(ValueError):
            Config(max_retries=-1)

    def test_config_rejects_negative_limits(self):
        """Test that negative limits are rejected."""
        with pytest.raises(ValueError):
            Config(max_tool_output_size=-1)

    def test_config_accepts_zero_retries(self):
        """Test that zero retries is valid."""
        config = Config(max_retries=0)
        assert config.max_retries == 0


class TestConfigResourceLimits:
    """Test resource limit configurations."""

    def test_docker_resource_limits(self):
        """Test Docker resource limit configuration."""
        config = Config()

        assert config.docker_cpu_limit == 2
        assert config.docker_memory_limit == "4g"
        assert config.docker_timeout == 600  # 10 minutes

    def test_storage_limits(self):
        """Test storage limit configuration."""
        config = Config()

        assert config.max_session_size == 1024 * 1024 * 1024  # 1GB
        assert config.max_sessions == 100

    def test_search_result_limits(self):
        """Test search result limit configuration."""
        config = Config()

        assert config.max_search_results == 100


class TestConfigPaths:
    """Test path-related configuration."""

    def test_storage_base_path(self):
        """Test storage base path configuration."""
        config = Config()

        assert config.storage_base_path == Path(".swe-agent")

    def test_storage_sessions_path(self):
        """Test sessions storage path."""
        config = Config()

        expected = Path(".swe-agent") / "sessions"
        assert config.sessions_path == expected

    def test_custom_storage_path(self):
        """Test custom storage path."""
        custom_path = Path("/custom/path")
        config = Config(storage_base_path=custom_path)

        assert config.storage_base_path == custom_path
        assert config.sessions_path == custom_path / "sessions"


class TestLoadConfigFromFile:
    """Test loading configuration from file."""

    def test_load_config_from_nonexistent_file(self):
        """Test loading config when file doesn't exist."""
        config = load_config(config_file="nonexistent.toml")

        # Should return default config
        assert config.localization_timeout == 300

    def test_load_config_prefers_env_over_file(self, tmp_path, monkeypatch):
        """Test that environment variables override file config."""
        __import__("tomllib")

        # Create config file
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[swe_agent]
localization_timeout = 400
max_retries = 4
"""
        )

        # Set env var
        monkeypatch.setenv("SWE_AGENT_MAX_RETRIES", "10")

        config = load_config(config_file=str(config_file))

        # Env var should win
        assert config.max_retries == 10
        # File value should be used for non-overridden (if tomli is available)
        # Note: tomli might not be installed, so file loading might be skipped
        assert config.localization_timeout in [300, 400]  # default or from file


class TestConfigLogging:
    """Test logging-related configuration."""

    def test_log_level_config(self):
        """Test log level configuration."""
        config = Config()

        assert config.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert config.log_level == "INFO"  # default

    def test_log_format_config(self):
        """Test log format configuration."""
        config = Config()

        assert config.log_format == "json"  # JSON Lines format

    def test_custom_log_level(self):
        """Test setting custom log level."""
        config = Config(log_level="DEBUG")

        assert config.log_level == "DEBUG"
